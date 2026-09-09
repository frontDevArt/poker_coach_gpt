"""Общие скалярные проверки ввода, разделяемые модулями пакета.

Модуль package-private (подчёркивание в имени файла), но функции внутри —
намеренно легитимное intra-package API: несколько модулей принимают
параметры с одинаковым смыслом (`call_amount`, `pot_before_call`,
вероятности) и обязаны выдавать на одно и то же нарушение одно и то же
сообщение об ошибке — это часть пользовательского контракта CLI.
"""

from __future__ import annotations


def check_amount(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} должен быть > 0, получено {value}")


def check_pot(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} не может быть отрицательным: {value}")


def check_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} должен быть в [0, 1], получено {value}")
