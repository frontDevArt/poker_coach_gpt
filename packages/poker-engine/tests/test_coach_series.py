"""Сквозные серии тренера: раздача кадр за кадром через `coach` (план 6, Задача 9).

Спека тренера §11.1, инвариант 10 §12. Серия — `tests/data/coach/<имя>.json`: контекст, кадры и
аналитические ожидания на каждый шаг — советник и спот, пометки, итог улицы или причина его
отсутствия, `line_deviates` связью с ответом прошлого шага. Чисел ответа советника в ожиданиях
нет: это регресс смысла конвейера, а не покерных ответов (эталоны — golden-set этапа 8).

На каждом шаге ответ, собранный шаблоном §2 спеки из печати фактов (`display`), проходит
`coach lint`, а тот же ответ с вписанным числом — нет.
"""

import json
from pathlib import Path

import pytest

from poker_engine import coach
from poker_engine.preflop_tree import OPEN_BB, SIZE_STEP_BB

SERIES = Path(__file__).parent / "data" / "coach"
NAMES = sorted(path.stem for path in SERIES.glob("*.json"))
# Число, которого нет ни в одной печати фактов: BB печатаются с одним знаком и не больше
# суммы стеков стола серий (240 BB), EV в BB и доллары — с двумя знаками, доли — не больше
# 100.0%, номера шагов серий — не больше 3.
WRITTEN_IN = "1234.5"


def _series(name):
    return json.loads((SERIES / f"{name}.json").read_text(encoding="utf-8"))


def _answer(number, result):
    """Ответ шага шаблоном §2 спеки тренера: действие с размером и «почему» из печати фактов."""
    if result["advisor"] is None:
        head = "Совета нет"
    else:
        action = next(item["display"] for item in result["why"] if item["key"] == "action")
        head = action[0].upper() + action[1:]
    reasons = "\n".join(f"- {item['display']}" for item in result["why"])
    return f"Шаг {number}. {head}.\n\nПочему:\n{reasons}\n"


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    """Серия, сыгранная через `coach` один раз на модуль: выводы шагов и линтер после каждого.

    Линтер идёт по файлу сразу после шага: след — факты шагов `1..N` и номера `1..N`.
    """
    cache = {}

    def play(name):
        if name not in cache:
            data = _series(name)
            path = str(tmp_path_factory.mktemp(name) / "hand.json")
            coach.start(path, data["context"])
            steps = []
            for number, frame in enumerate(data["frames"], 1):
                result = coach.step(path, frame)
                text = _answer(number, result)
                written = f"{text}- Рейз до {WRITTEN_IN} BB.\n"
                steps.append((result, (coach.lint(path, text), coach.lint(path, written))))
            cache[name] = steps
        return cache[name]

    return play


def test_the_series_of_the_plan_are_all_here():
    assert NAMES == sorted(
        [
            "bb_vs_sb_limp_flop",
            "chips",
            "deviation",
            "multiway",
            "open_3bet_flop",
            "sb_limp_iso",
            "undo",
        ]
    )


@pytest.mark.parametrize("name", [name for name in NAMES if "expect" in _series(name)])
def test_each_step_meets_its_analytic_expectations(played, name):
    data = _series(name)
    steps = played(name)
    assert len(data["expect"]) == len(data["frames"]) == len(steps)
    results = [result for result, _ in steps]
    for number, (expect, result) in enumerate(zip(data["expect"], results, strict=True), 1):
        where = f"{name}, шаг {number}"
        answer = result["answer"]
        assert result["step"] == number, where
        assert result["advisor"] == expect["advisor"] == answer["advisor"], where
        if expect["advisor"] is None:
            # Отказ — причины всех советников реестра, тексты — как в ответе.
            reasons = {entry["advisor"]: entry["reason"] for entry in answer["notApplicable"]}
            assert reasons == expect["reasons"], where
        else:
            assert answer["spot"] == expect["spot"], where
            flags = set(answer["flags"])
            assert set(expect["flagsHas"]) <= flags, where
            assert not set(expect["flagsNot"]) & flags, where
        if "lineDeviates" in expect:
            deviates = _deviates(expect["lineDeviates"], results)
            assert ("line_deviates" in answer["flags"]) == deviates, where
        _check_streets(result["streets"], expect["streets"], where)


def _deviates(rule, results):
    """Отклонение героя — ход в кадре не тот, что советовал шаг `unlessStep`: другое действие
    или размер дальше шага `SIZE_STEP_BB`."""
    advised = results[rule["unlessStep"] - 1]["answer"]
    if advised["action"] != rule["action"]:
        return True
    return "sizeBb" in rule and abs(advised["sizeBb"] - rule["sizeBb"]) > SIZE_STEP_BB + 1e-9


def _check_streets(streets, expected, where):
    """Итоги улиц шага: линия и участники — как в ожидании, доли диапазонов — внутри (0, 1)."""
    assert set(streets) == set(expected), where
    for street, summary in expected.items():
        got = streets[street]
        if "reason" in summary:
            assert got == {"street": street, "reason": summary["reason"]}, where
            continue
        assert got["line"] == summary["line"], where
        keys = ("seatIndex", "position", "role", "isHero", "stackBb")
        assert [{key: entry[key] for key in keys} for entry in got["ranges"]] == summary["ranges"]
        assert all(0 < entry["reachPct"] < 1 and entry["reach"] for entry in got["ranges"]), where


def test_the_deviation_series_deviates(played):
    # Размер открытия в ответе — правило `OPEN_BB` (пометка `fixed_sizing` шага 1), а герой
    # открыл до 2.5: ни рейз по правилу, ни фолд, ни олл-ин не «рейз до 2.5».
    assert abs(OPEN_BB - 2.5) > SIZE_STEP_BB
    second, _ = played("deviation")[1]
    assert "line_deviates" in second["answer"]["flags"]


@pytest.mark.parametrize("name", [name for name in NAMES if "sameAs" in _series(name)])
def test_a_series_like_another_gives_the_same_steps(played, name):
    # `chips`: кадр в фишках с банком «середина» и средний стек в фишках дают те же узлы
    # (инвариант 1, 2 §12) — и те же ответы, факты и итоги улиц.
    same = _series(name)["sameAs"]
    assert [result for result, _ in played(name)] == [result for result, _ in played(same)]


@pytest.mark.parametrize("name", NAMES)
def test_the_answer_from_the_facts_passes_the_linter(played, name):
    for number, (_, (clean, written)) in enumerate(played(name), 1):
        assert clean == {"ok": True}, f"{name}, шаг {number}"
        assert written == {"ok": False, "untraced": [WRITTEN_IN]}, f"{name}, шаг {number}"


@pytest.mark.parametrize("name", [name for name in NAMES if _series(name).get("undo")])
def test_undo_after_each_step_restores_the_file(tmp_path, name):
    # Инвариант 3 и Review Focus 6: шаг, `undo` — файл байт в байт прежний, в том числе после
    # кадра, закрывшего улицу; тот же шаг снова — тот же вывод и тот же файл.
    data = _series(name)
    path = tmp_path / "hand.json"
    coach.start(str(path), data["context"])
    for frame in data["frames"]:
        before = path.read_bytes()
        first = coach.step(str(path), frame)
        after = path.read_bytes()
        coach.undo(str(path))
        assert path.read_bytes() == before
        assert coach.step(str(path), frame) == first
        assert path.read_bytes() == after
