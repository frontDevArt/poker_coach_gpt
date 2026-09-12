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

import math

# Сравнения записаны как `not value > 0`, а не `value <= 0`: NaN проваливает
# любое сравнение, и прямая форма молча пропускала бы его дальше — в сумму
# лесенки, в эквити, в пот-оддсы. `float("nan")` не бросает, а
# `handstate._as_float` и `argparse` принимают строку `"nan"`, так что путь
# с пользовательского ввода есть. NaN и `-inf` уходят в прежний текст
# нарушенного ограничения; `+inf` ограничение `> 0` честно выполняет, и
# отвергается отдельным текстом `_check_finite`.


def check_positive(value: float, name: str) -> None:
    if not value > 0:
        raise ValueError(f"{name} должен быть > 0, получено {value}")
    _check_finite(value, name)


def check_non_negative(value: float, name: str) -> None:
    if not value >= 0:
        raise ValueError(f"{name} не может быть отрицательным: {value}")
    _check_finite(value, name)


def _check_finite(value: float, name: str) -> None:
    """Бесконечный приз, стек или банк — не число, с которым можно считать:
    дальше он даёт `inf` или `inf * 0 = nan` без единого отказа.

    Сравнение с `math.inf`, а не `math.isfinite`: целые сюда тоже приходят
    (`places_paid`, `trials`), и `isfinite(10**400)` бросил бы
    `OverflowError`. Шаблон «не может быть …», как у `check_non_negative`,
    потому что имена здесь бывают и среднего рода (`число раздач`).
    """
    if value == math.inf:
        raise ValueError(f"{name} не может быть бесконечным: {value}")


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
