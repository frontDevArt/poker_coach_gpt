"""Общие скалярные проверки ввода, разделяемые модулями пакета.

Модуль package-private (подчёркивание в имени файла), но функции внутри —
намеренно легитимное intra-package API: несколько модулей принимают
параметры с одинаковым смыслом (`call_amount`, `pot_before_call`,
вероятности) и обязаны выдавать на одно и то же нарушение одно и то же
сообщение об ошибке — это часть пользовательского контракта CLI.

Имя гарда — всегда имя ограничения, а не предметной области: один и тот
же `check_non_negative` обслуживает и размер банка, и число наблюдённых
раздач соперника. Тексты сообщений собираются из параметра `name`,
поэтому переименование гарда пользователю не видно.
"""

from __future__ import annotations


def check_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} должен быть > 0, получено {value}")


def check_non_negative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} не может быть отрицательным: {value}")


def check_integer(value: object, name: str) -> None:
    if not isinstance(value, int):
        raise ValueError(f"{name} должен быть целым, получено {value!r}")


def check_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} должен быть в [0, 1], получено {value}")
