from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Generator, List, Optional, Tuple, Union
import time

from ollama import Client


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class GenerateChunk:
    """Результат одного чанка генерации."""

    chunk: Any
    attempt: int
    is_loop_end: bool = False

    @property
    def is_success(self) -> bool:
        return not self.is_loop_end

# ============================================================================
# Loop Detection
# ============================================================================


def find_repeats_optimized(
    text: str,
    min_chars: Optional[int] = None,
    max_chars: Optional[int] = None,
    skip_more: int = 1,
) -> Tuple[List[int], List[int]]:
    """
    Ищет повторяющиеся подстроки в конце текста.

    Args:
        text: Текст для анализа.
        min_chars: Минимальная длина подстроки.
        max_chars: Максимальная длина подстроки.
        skip_more: Прекратить поиск, если найдено больше повторов.

    Returns:
        Кортеж из двух списков: (длины подстрок, количество повторов).
    """
    text_length = len(text)
    if text_length == 0:
        return [], []

    min_val = max(1, min_chars) if min_chars is not None else 1
    max_val = min(text_length, max_chars) if max_chars is not None else text_length

    if min_val > max_val:
        return [], []

    lengths: List[int] = []
    counts: List[int] = []

    for n in range(min_val, max_val + 1):
        substring = text[-n:]
        count = 0
        pos = 0

        while pos <= text_length - n:
            pos = text.find(substring, pos)

            if pos == -1:
                break

            count += 1
            pos += 1

        lengths.append(n)
        counts.append(count)

        if skip_more > 1 and count > skip_more:
            break

    return lengths, counts


# ============================================================================
# Main Client
# ============================================================================


class OllamaLooplessClient:
    """
    Обёртка над ollama.Client с автоматическим обнаружением зацикливания.

    Особенности:
      - Поддерживает только streaming-режим generate()
      - Во время стрима проверяет накопленный текст на зацикливание
      - При детекте зацикливания прерывает генерацию и делает retry
      - Возвращает GenerateChunk с информацией о попытке и статусе
    """

    def __init__(
        self,
        client: Optional[Client] = None,
        *,
        default_model: Optional[str] = None,
        log_level: int = logging.INFO,
        **client_kwargs: Any,
    ) -> None:
        """
        Инициализация клиента.

        Args:
            client: Готовый экземпляр ollama.Client (опционально).
            default_model: Модель по умолчанию.
            log_level: Уровень логирования (logging.DEBUG, logging.INFO, etc.).
            **client_kwargs: Аргументы для создания Client (host, timeout, etc.).
        """
        self._client = client or Client(**client_kwargs)
        self.default_model = default_model

        # Настройка логирования
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._logger.setLevel(log_level)

        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(log_level)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    # ------------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------------

    def model_preload(self, **kwargs: Any) -> None:
        """
        Предзагрузка модели в память для ускорения первого запроса.

        Выполняет два пустых запроса:
        1. Загрузка модели в память
        2. Стабилизация (известная особенность Ollama — первый ответ может отличаться)
        """
        kwargs.pop("prompt", None)

        # Preload
        self._client.generate(prompt="", **kwargs)

        # First-run answer diff mitigation
        self._client.generate(prompt="", **kwargs)

        self._logger.debug("Model preloaded: %s", kwargs.get("model", "unknown"))

    def generate(
        self,
        *,
        model: Optional[str] = None,
        retries: int = 1,
        temperature_shift: Optional[List[float]] = None,
        retry_delays: Optional[List[float]] = None,
        prompt_suffix_on_retry: Optional[str] = None,
        check_every_n: int = 8,
        loop_min_chars: int = 50,
        loop_thresh: int = 3,
        **kwargs: Any,
    ) -> Generator[GenerateChunk, None, None]:
        """
        Streaming генерация с автоматическим обнаружением циклов.

        Args:
            model: Название модели (или используется default_model).
            retries: Количество дополнительных попыток после первой.
            temperature_shift: Список температур для последовательных retry.
            retry_delays: Список задержек (в секундах) перед каждым retry.
            prompt_suffix_on_retry: Суффикс, добавляемый к промпту при retry.
            check_every_n: Проверять на циклы каждые N токенов.
            loop_min_chars: Минимальная длина подстроки для поиска повторов.
            loop_thresh: Порог количества повторов для детекции цикла.
            **kwargs: Аргументы для ollama.Client.generate().

        Yields:
            GenerateChunk с информацией о чанке, номере попытки и статусе.
        """
        mdl = self._resolve_model(model)
        self._warn_if_zero_temperature(kwargs, retries)

        # Фиксируем streaming
        kwargs.pop("stream", None)

        max_attempts = 1 + max(0, int(retries))
        original_prompt = kwargs.get("prompt", "")
        original_temperature = self._get_temperature(kwargs)

        for attempt in range(max_attempts):
            # Задержка перед retry (не перед первой попыткой)
            if attempt > 0:
                delay = self._get_retry_delay(attempt, retry_delays)
                if delay > 0:
                    self._log_retry_delay(attempt, max_attempts, delay)
                    time.sleep(delay)

            # Подготовка параметров для текущей попытки
            current_kwargs = self._prepare_attempt_kwargs(
                kwargs=kwargs,
                attempt=attempt,
                original_prompt=original_prompt,
                original_temperature=original_temperature,
                temperature_shift=temperature_shift,
                prompt_suffix_on_retry=prompt_suffix_on_retry,
            )

            self._log_attempt_start(attempt, max_attempts)

            # Выполнение генерации
            loop_detected, error_occurred = yield from self._execute_generation(
                model=mdl,
                attempt=attempt,
                kwargs=current_kwargs,
                check_every_n=check_every_n,
                loop_min_chars=loop_min_chars,
                loop_thresh=loop_thresh,
            )

            # Обработка результата
            if error_occurred:
                if attempt < max_attempts - 1:
                    continue
                raise RuntimeError("All generation attempts failed due to errors")

            if not loop_detected:
                self._logger.debug("Generation completed successfully on attempt %d", attempt + 1)
                return

            # Цикл обнаружен
            self._log_loop_detected(attempt, max_attempts)

            if attempt >= max_attempts - 1:
                self._logger.warning(
                    "All %d attempts exhausted, generation ended with loop", max_attempts
                )
                yield GenerateChunk(chunk=None, attempt=attempt, is_loop_end=True)
                return

    def stop_all_running_models(self) -> None:
        """Выгружает все текущие запущенные модели из памяти."""
        ps_result = self._client.ps()
        models = getattr(ps_result, "models", None) or ps_result.get("models", [])

        for m in models:
            name = self._extract_model_name(m)
            if not name:
                continue

            self._client.generate(
                model=name,
                prompt="",
                keep_alive="0m",
                stream=False,
            )
            self._logger.debug("Unloaded model: %s", name)

    def get_vram(self) -> str:
        """Возвращает информацию о загруженных моделях и использовании VRAM."""
        models_info: List[str] = []

        for model in self._client.ps()["models"]:
            model_info = f'"{model.name}"'
            model_info += f": {model.size / 1024 ** 3:.0f} GB"

            if model.size > model.size_vram:
                offload_percent = 100 - model.size_vram / model.size * 100
                model_info += f" ⚠️ !!!OFFLOAD!!! ⚠️ {offload_percent:.0f} % on CPU"
            else:
                model_info += " ✅"

            model_info += f" {model.context_length} ctx"
            models_info.append(model_info)

        return "\n\n".join(models_info)

    # ------------------------------------------------------------------------
    # Chunk Parsing
    # ------------------------------------------------------------------------

    @staticmethod
    def extract_delta(chunk: Any) -> str:
        """
        Извлекает текстовый дельта-токен из чанка.

        Args:
            chunk: Объект чанка от Ollama.

        Returns:
            Строка с текстом токена.
        """
        if not chunk:
            return ""

        delta = getattr(chunk, "thinking", None) or getattr(chunk, "response", None)

        if isinstance(delta, str):
            return delta

        return ""

    # ------------------------------------------------------------------------
    # Loop Detection
    # ------------------------------------------------------------------------

    def check_loops(self, text: str, loop_min_chars: int, loop_thresh: int) -> bool:
        """
        Проверяет текст на наличие зацикливания.

        Args:
            text: Накопленный текст генерации.
            loop_min_chars: Минимальная длина подстроки для поиска.
            loop_thresh: Порог количества повторов.

        Returns:
            True если обнаружено зацикливание.
        """
        lengths, counts = find_repeats_optimized(
            text,
            min_chars=loop_min_chars,
            skip_more=loop_thresh,
        )

        for count in counts:
            if count >= loop_thresh:
                return True

        return False

    # ------------------------------------------------------------------------
    # Private: Generation Logic
    # ------------------------------------------------------------------------

    def _execute_generation(
        self,
        model: str,
        attempt: int,
        kwargs: dict[str, Any],
        check_every_n: int,
        loop_min_chars: int,
        loop_thresh: int,
    ) -> Generator[GenerateChunk, None, Tuple[bool, bool]]:
        """
        Выполняет одну попытку генерации.

        Yields:
            GenerateChunk для каждого токена.

        Returns:
            Кортеж (loop_detected, error_occurred).
        """
        accumulated_text = ""
        loop_detected = False
        error_occurred = False
        token_count = 0
        stream = None

        try:
            stream = self._client.generate(model=model, stream=True, **kwargs)

            for chunk in stream:
                yield GenerateChunk(chunk=chunk, attempt=attempt)

                accumulated_text += self.extract_delta(chunk)
                token_count += 1

                # Проверяем циклы каждые N токенов
                if token_count % check_every_n == 0:
                    if self.check_loops(accumulated_text, loop_min_chars, loop_thresh):
                        loop_detected = True
                        break

        except Exception as e:
            self._logger.error("Generation error on attempt %d: %s", attempt + 1, e)
            error_occurred = True

        finally:
            self._close_stream(stream)

        return loop_detected, error_occurred

    def _prepare_attempt_kwargs(
        self,
        kwargs: dict[str, Any],
        attempt: int,
        original_prompt: str,
        original_temperature: Optional[float],
        temperature_shift: Optional[List[float]],
        prompt_suffix_on_retry: Optional[str],
    ) -> dict[str, Any]:
        """Подготавливает kwargs для конкретной попытки."""
        current_kwargs = kwargs.copy()

        # Модификация промпта при retry
        if attempt > 0 and prompt_suffix_on_retry:
            current_kwargs["prompt"] = original_prompt + prompt_suffix_on_retry

        # Модификация температуры при retry
        if attempt > 0 and temperature_shift:
            shift_index = min(attempt - 1, len(temperature_shift) - 1)
            new_temperature = temperature_shift[shift_index]
            current_kwargs = self._set_temperature(current_kwargs, new_temperature)
            self._logger.debug(
                "Attempt %d: temperature shifted to %.2f", attempt + 1, new_temperature
            )

        return current_kwargs

    # ------------------------------------------------------------------------
    # Private: Helpers
    # ------------------------------------------------------------------------

    def _resolve_model(self, model: Optional[str]) -> str:
        """Определяет модель для использования."""
        mdl = model or self.default_model
        if not mdl:
            raise ValueError(
                "Model name is required (pass model=... or set default_model in __init__)."
            )
        return mdl

    def _warn_if_zero_temperature(self, kwargs: dict[str, Any], retries: int) -> None:
        """Предупреждает о нулевой температуре при включенных retry."""
        if retries > 0:
            temperature = self._get_temperature(kwargs)
            if temperature is not None and temperature == 0.0:
                self._logger.warning(
                    "Temperature is 0.0 with retries=%d. "
                    "Retries will likely produce the same result. "
                    "Consider using temperature_shift or increasing temperature.",
                    retries,
                )

    @staticmethod
    def _get_temperature(kwargs: dict[str, Any]) -> Optional[float]:
        """Извлекает температуру из kwargs."""
        options = kwargs.get("options", {})
        temp = options.get("temperature")
        if temp is None:
            return None
        return float(temp)

    @staticmethod
    def _set_temperature(kwargs: dict[str, Any], temperature: float) -> dict[str, Any]:
        """Устанавливает температуру в kwargs."""
        kwargs = kwargs.copy()
        if "options" not in kwargs:
            kwargs["options"] = {}
        else:
            kwargs["options"] = kwargs["options"].copy()
        kwargs["options"]["temperature"] = float(temperature)
        return kwargs

    @staticmethod
    def _extract_model_name(model_info: Any) -> Optional[str]:
        """Извлекает имя модели из информации о модели."""
        return (
            getattr(model_info, "model", None)
            or getattr(model_info, "name", None)
            or (model_info.get("model") if isinstance(model_info, dict) else None)
            or (model_info.get("name") if isinstance(model_info, dict) else None)
        )

    @staticmethod
    def _close_stream(stream: Any) -> None:
        """Безопасно закрывает стрим."""
        if stream is not None:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    # ------------------------------------------------------------------------
    # Private: Logging
    # ------------------------------------------------------------------------

    def _log_attempt_start(self, attempt: int, max_attempts: int) -> None:
        """Логирует начало попытки."""
        self._logger.info("Starting generation attempt %d/%d", attempt + 1, max_attempts)

    def _log_loop_detected(self, attempt: int, max_attempts: int) -> None:
        """Логирует обнаружение цикла."""
        self._logger.warning(
            "Loop detected on attempt %d/%d, retrying...", attempt + 1, max_attempts
        )


    def chat(
        self,
        *,
        model: Optional[str] = None,
        messages: List[dict],
        stream: bool = False,
        retries: int = 1,
        temperature_shift: Optional[List[float]] = None,
        retry_delays: Optional[List[float]] = None,
        prompt_suffix_on_retry: Optional[str] = None,
        check_every_n: int = 8,
        loop_min_chars: int = 50,
        loop_thresh: int = 3,
        **kwargs: Any,
    ) -> Generator[GenerateChunk, None, None] | dict:
        """
        Chat API с автоматическим обнаружением циклов (только для stream=True).

        Args:
            model: Название модели.
            messages: История сообщений.
            stream: Если True — streaming с loop detection, иначе — обычный вызов.
            retries: Количество дополнительных попыток (только для stream=True).
            temperature_shift: Список температур для retry (только для stream=True).
            retry_delays: Список задержек (в секундах) перед каждым retry.
            prompt_suffix_on_retry: Суффикс для последнего user-сообщения при retry.
            check_every_n: Проверять на циклы каждые N токенов.
            loop_min_chars: Минимальная длина подстроки для поиска повторов.
            loop_thresh: Порог количества повторов для детекции цикла.
            **kwargs: Аргументы для ollama.Client.chat().

        Returns:
            При stream=False: dict с ответом.
            При stream=True: Generator[GenerateChunk].
        """
        mdl = self._resolve_model(model)

        if not stream:
            return self._client.chat(model=mdl, messages=messages, stream=False, **kwargs)

        return self._chat_stream(
            model=mdl,
            messages=messages,
            retries=retries,
            temperature_shift=temperature_shift,
            retry_delays=retry_delays, 
            prompt_suffix_on_retry=prompt_suffix_on_retry,
            check_every_n=check_every_n,
            loop_min_chars=loop_min_chars,
            loop_thresh=loop_thresh,
            **kwargs,
        )

    def _chat_stream(
        self,
        *,
        model: str,
        messages: List[dict],
        retries: int = 1,
        temperature_shift: Optional[List[float]] = None,
        retry_delays: Optional[List[float]] = None,
        prompt_suffix_on_retry: Optional[str] = None,
        check_every_n: int = 8,
        loop_min_chars: int = 50,
        loop_thresh: int = 3,
        **kwargs: Any,
    ) -> Generator[GenerateChunk, None, None]:
        """
        Внутренний метод streaming chat с loop detection.
        """
        self._warn_if_zero_temperature(kwargs, retries)

        max_attempts = 1 + max(0, int(retries))
        original_messages = [msg.copy() for msg in messages]
        original_temperature = self._get_temperature(kwargs)

        for attempt in range(max_attempts):
            # Задержка перед retry (не перед первой попыткой)
            if attempt > 0:
                delay = self._get_retry_delay(attempt, retry_delays)
                if delay > 0:
                    self._log_retry_delay(attempt, max_attempts, delay)
                    time.sleep(delay)

            current_kwargs = kwargs.copy()
            current_messages = [msg.copy() for msg in original_messages]

            # Модификация последнего user-сообщения при retry
            if attempt > 0 and prompt_suffix_on_retry and current_messages:
                for msg in reversed(current_messages):
                    if msg.get("role") == "user":
                        msg["content"] = msg["content"] + prompt_suffix_on_retry
                        break

            # Модификация температуры при retry
            if attempt > 0 and temperature_shift:
                shift_index = min(attempt - 1, len(temperature_shift) - 1)
                new_temperature = temperature_shift[shift_index]
                current_kwargs = self._set_temperature(current_kwargs, new_temperature)
                self._logger.debug(
                    "Chat attempt %d: temperature shifted to %.2f", attempt + 1, new_temperature
                )

            self._log_attempt_start(attempt, max_attempts)

            loop_detected, error_occurred = yield from self._execute_chat_stream(
                model=model,
                messages=current_messages,
                attempt=attempt,
                kwargs=current_kwargs,
                check_every_n=check_every_n,
                loop_min_chars=loop_min_chars,
                loop_thresh=loop_thresh,
            )

            if error_occurred:
                if attempt < max_attempts - 1:
                    continue
                raise RuntimeError("All chat attempts failed due to errors")

            if not loop_detected:
                self._logger.debug("Chat completed successfully on attempt %d", attempt + 1)
                return

            self._log_loop_detected(attempt, max_attempts)

            if attempt >= max_attempts - 1:
                self._logger.warning(
                    "All %d chat attempts exhausted, ended with loop", max_attempts
                )
                yield GenerateChunk(chunk=None, attempt=attempt, is_loop_end=True)
                return


    def _execute_chat_stream(
        self,
        model: str,
        messages: List[dict],
        attempt: int,
        kwargs: dict[str, Any],
        check_every_n: int,
        loop_min_chars: int,
        loop_thresh: int,
    ) -> Generator[GenerateChunk, None, Tuple[bool, bool]]:
        """
        Выполняет одну попытку streaming chat.

        Yields:
            GenerateChunk для каждого токена.

        Returns:
            Кортеж (loop_detected, error_occurred).
        """
        accumulated_text = ""
        loop_detected = False
        error_occurred = False
        token_count = 0
        stream = None

        try:
            stream = self._client.chat(model=model, messages=messages, stream=True, **kwargs)

            for chunk in stream:
                yield GenerateChunk(chunk=chunk, attempt=attempt)

                # Извлекаем контент из chat-ответа
                content = ""
                if isinstance(chunk, dict):
                    content = chunk.get("message", {}).get("content", "")
                else:
                    message = getattr(chunk, "message", None)
                    if message:
                        content = getattr(message, "content", "") or ""

                accumulated_text += content
                token_count += 1

                if token_count % check_every_n == 0:
                    if self.check_loops(accumulated_text, loop_min_chars, loop_thresh):
                        loop_detected = True
                        break

        except Exception as e:
            self._logger.error("Chat stream error on attempt %d: %s", attempt + 1, e)
            error_occurred = True

        finally:
            self._close_stream(stream)

        return loop_detected, error_occurred
    
    @staticmethod
    def _get_retry_delay(attempt: int, retry_delays: Optional[List[float]]) -> float:
        """
        Получает задержку для текущей попытки retry.
        
        Args:
            attempt: Номер попытки (1-based для retry, т.к. attempt=0 — первая попытка).
            retry_delays: Список задержек в секундах.
            
        Returns:
            Задержка в секундах (0 если не задана).
        """
        if not retry_delays:
            return 0.0
        
        # attempt=1 → retry_delays[0], attempt=2 → retry_delays[1], etc.
        delay_index = min(attempt - 1, len(retry_delays) - 1)
        delay = retry_delays[delay_index]
        
        return max(0.0, float(delay))

    def _log_retry_delay(self, attempt: int, max_attempts: int, delay: float) -> None:
        """Логирует задержку перед retry."""
        self._logger.info(
            "Waiting %.2f sec before retry attempt %d/%d...",
            delay, attempt + 1, max_attempts
        )