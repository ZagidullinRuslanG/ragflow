from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Generator, List, Optional, Tuple

from openai import OpenAI


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


class OpenAILooplessClient:
    """
    Обёртка над openai.OpenAI с автоматическим обнаружением зацикливания.

    Особенности:
      - Поддерживает streaming-режим chat()
      - Во время стрима проверяет накопленный текст на зацикливание
      - При детекте зацикливания прерывает генерацию и делает retry
      - Возвращает GenerateChunk с информацией о попытке и статусе
    """

    def __init__(
        self,
        client: Optional[OpenAI] = None,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        log_level: int = logging.INFO,
        **client_kwargs: Any,
    ) -> None:
        """
        Инициализация клиента.

        Args:
            client: Готовый экземпляр openai.OpenAI (опционально).
            api_key: API ключ для OpenAI.
            base_url: Базовый URL для API.
            default_model: Модель по умолчанию.
            log_level: Уровень логирования (logging.DEBUG, logging.INFO, etc.).
            **client_kwargs: Аргументы для создания OpenAI клиента.
        """
        if client:
            self._client = client
        else:
            self._client = OpenAI(api_key=api_key, base_url=base_url, **client_kwargs)

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

    def chat(
        self,
        *,
        model: Optional[str] = None,
        messages: List[dict],
        stream: bool = False,
        retries: int = 0,
        temperature_shift: Optional[List[float]] = None,
        retry_delays: Optional[List[float]] = None,
        prompt_suffix_on_retry: Optional[str] = None,
        check_every_n: int = 8,
        loop_min_chars: int = 50,
        loop_thresh: int = 3,
        **kwargs: Any,
    ) -> Generator[GenerateChunk, None, None] | Any:
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
            **kwargs: Аргументы для openai.chat.completions.create().

        Returns:
            При stream=False: response от OpenAI.
            При stream=True: Generator[GenerateChunk].
        """
        mdl = self._resolve_model(model)

        if not stream:
            return self._client.chat.completions.create(
                model=mdl, messages=messages, stream=False, **kwargs
            )

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

    def chat_completions_create(self, **kwargs):
        """Прямой вызов client.chat.completions.create для совместимости."""
        return self._client.chat.completions.create(**kwargs)

    # ------------------------------------------------------------------------
    # Private: Chat Stream
    # ------------------------------------------------------------------------

    def _chat_stream(
        self,
        *,
        model: str,
        messages: List[dict],
        retries: int = 0,
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
        original_temperature = kwargs.get("temperature")

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
                current_kwargs["temperature"] = new_temperature
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
            stream = self._client.chat.completions.create(
                model=model, messages=messages, stream=True, **kwargs
            )

            for chunk in stream:
                yield GenerateChunk(chunk=chunk, attempt=attempt)

                # Извлекаем контент из OpenAI chat-ответа
                content = self.extract_delta(chunk)

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

    # ------------------------------------------------------------------------
    # Chunk Parsing
    # ------------------------------------------------------------------------

    @staticmethod
    def extract_delta(chunk: Any) -> str:
        """
        Извлекает текстовый дельта-токен из чанка OpenAI.

        Args:
            chunk: Объект чанка от OpenAI.

        Returns:
            Строка с текстом токена.
        """
        if not chunk:
            return ""

        try:
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    return delta.content
                # Для reasoning моделей
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    return delta.reasoning_content
        except (AttributeError, IndexError):
            pass

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
            temperature = kwargs.get("temperature")
            if temperature is not None and temperature == 0.0:
                self._logger.warning(
                    "Temperature is 0.0 with retries=%d. "
                    "Retries will likely produce the same result. "
                    "Consider using temperature_shift or increasing temperature.",
                    retries,
                )

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

    def _log_retry_delay(self, attempt: int, max_attempts: int, delay: float) -> None:
        """Логирует задержку перед retry."""
        self._logger.info(
            "Waiting %.2f sec before retry attempt %d/%d...",
            delay, attempt + 1, max_attempts
        )
