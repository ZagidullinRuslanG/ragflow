import argparse
import shlex
from dataclasses import dataclass, asdict
from typing import Literal, Union, List
import re

def regex_type(s: str) -> str:
    """Возвращает строку, если s — валидный regex, иначе бросает ошибку argparse."""
    try:
        re.compile(s)
    except re.error as e:
        raise argparse.ArgumentTypeError(f'Неверный regex {s!r}: {e}')
    return s

@dataclass
class ParserConfig:
    lower_boundary: float = 6.7
    upper_boundary: float = 4.0

    cut_colonne: List[str] = ""

def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='mytool',
        add_help=False,
        allow_abbrev=False
    )
    p.add_argument('--lower_boundary', type=float, default=ParserConfig.lower_boundary)
    p.add_argument('--upper_boundary', type=float, default=ParserConfig.upper_boundary)

    p.add_argument(
        '--cut_colonne',
        nargs='+',
        type=regex_type,
        default=[],
        metavar='REGEX'
    )

    return p

def parse_config(raw: str) -> dict:
    tokens = shlex.split(raw)
    parser = make_parser()
    args = parser.parse_args(tokens)
    cfg = ParserConfig(**vars(args))

    return asdict(cfg)


def parse_cut_colonne(raw: str) -> List[str]:
    """
    Разбивает raw-команду на токены (уважая кавычки) и возвращает список regex из --cut_colonne.
    """
    tokens = shlex.split(raw)
    parser = make_parser()
    args, _unknown = parser.parse_known_args(tokens)
    return args.cut_colonne