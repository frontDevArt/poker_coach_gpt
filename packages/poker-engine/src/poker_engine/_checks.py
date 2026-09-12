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
    """В отличие от остальных гардов модуля стоит не на пользовательском
    вводе, а на программной конструкции: с пользовательского пути значения
    приходят уже приведёнными (`handstate._as_int`), и своё сообщение об
    отказе тот путь выдаёт раньше. Текст поэтому не часть контракта CLI —
    он адресован вызывающему коду внутри пакета.

    `bool` отвергается наравне с нечислом: `isinstance(True, int)` истинно,
    а `places_paid=True` или `players_left=True` — не размер призовой зоны
    и не число живых игроков, а проскочившая мимо типа ошибка вызова.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} должен быть целым, получено {value!r}")


def check_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} должен быть в [0, 1], получено {value}")
