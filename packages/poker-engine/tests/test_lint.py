"""Линтер чисел ответа тренера и `coach lint` (план 6, Задача 8).

Спека тренера §9, инвариант 9 §12; Review Focus 7. След — числа печати фактов всех шагов файла и
номера шагов; число текста без следа линтер называет. Ожидания — правила §9 на бумаге: текст и
печать фактов в тестах написаны руками, кроме сквозных случаев через `coach`.
"""

import json
import re
import sys

import pytest

from conftest import (
    _context,
    console_stdin,
    flop_frame,
    preflop_frame,
    preflop_vs_3bet,
    preflop_vs_4bet,
)
from poker_engine import coach
from poker_engine.cli import main
from poker_engine.explain import fact, line_text
from poker_engine.lint import numbers, untraced


def _facts(*displays):
    return [{"key": f"k{at}", "value": text, "display": text} for at, text in enumerate(displays)]


# --- lint.untraced ---------------------------------------------------------------------------


def test_a_number_from_a_display_is_traced():
    facts = [fact("sizeBb", 2.5, "bb"), fact("vsSecondUsd", 0.14, "usd"), fact("share", 0.15, "pct")]
    assert [item["display"] for item in facts] == ["2.5 BB", "+$0.14", "15.0%"]
    assert untraced("Рейз до 2.5 BB: лучше колла на +$0.14, это 15.0% диапазона.", facts, 0) == []


def test_a_written_in_number_is_named():
    facts = [fact("sizeBb", 2.5, "bb")]
    assert untraced("Рейз до 3.5 BB, а не до 2.5 BB.", facts, 0) == ["3.5"]


def test_2_0_and_2_are_different_numbers():
    # Тренер переписывает печать, а не округляет: `2.0` из печати не даёт следа `2`, и наоборот.
    assert untraced("рейз до 2 BB", [fact("sizeBb", 2.0, "bb")], 0) == ["2"]
    assert untraced("рейз до 2.0 BB", [fact("sizeBb", 2.0, "bb")], 0) == []
    assert untraced("2.0 раза", _facts("в 2 раза"), 0) == ["2.0"]
    assert untraced("15%", [fact("share", 0.15, "pct")], 0) == ["15"]


def test_a_comma_reads_as_a_dot():
    facts = [fact("sizeBb", 2.5, "bb")]
    assert untraced("рейз до 2,5 BB", facts, 0) == []
    assert untraced("рейз до 3,5 BB", facts, 0) == ["3.5"]
    # Запятая с пробелом — перечисление, а не дробь.
    assert untraced("2, 5", _facts("2 и 5"), 0) == []


def test_the_sign_is_dropped():
    facts = [fact("vsBaseBb", 0.35, "ev_bb"), fact("vsBaseUsd", -0.14, "usd")]
    assert [item["display"] for item in facts] == ["+0.35 BB", "-$0.14"]
    text = "+0.35 BB, -0.35 BB, −0.35 BB; -$0.14, +$0.14, −$0.14, 0.14"
    assert untraced(text, facts, 0) == []
    # Минуса нуля в печати нет: `-0.004` — `+0.00 BB`; след — `0.00`, а не `0.0` и не `0`.
    zero = [fact("vsBaseBb", -0.004, "ev_bb")]
    assert zero[0]["display"] == "+0.00 BB"
    assert untraced("разница -0.00 BB", zero, 0) == []
    assert untraced("разница 0.0 BB, то есть 0", zero, 0) == ["0.0", "0"]


def test_step_numbers_are_traced_up_to_n():
    assert untraced("На шаге 1 и на шаге 3.", [], 3) == []
    assert untraced("На шаге 4.", [], 3) == ["4"]
    assert untraced("Шаг 1.", [], 0) == ["1"]


def test_untraced_numbers_are_named_once_in_order():
    assert untraced("9 и 4, снова 9, затем 4,0 и 4.0", [], 0) == ["9", "4", "4.0"]


def test_the_exceptions_are_not_numbers():
    text = (
        "`3.5 BB` и `77%`; UTG1 и UTG+1 открыли; 3-бет, 4-bet, 5-бета, 3-Бет; 8-max и 6-MAX; "
        "руки 77, 22+, A5s, T9o, 98s, A5, K9, AhKd, 7h6h, Ts9s, A2s-A5s и 55-77. Рука — 77."
    )
    assert untraced(text, [], 0) == []


def test_a_number_with_a_unit_is_a_number():
    # Пара — запись из одних цифр: со знаком `%`, `BB` или `$` рядом она число.
    assert untraced("77%", [], 0) == ["77"]
    assert untraced("77 %", [], 0) == ["77"]
    assert untraced("77\u00a0%", [], 0) == ["77"]
    assert untraced("77 BB", [], 0) == ["77"]
    assert untraced("+$77", [], 0) == ["77"]
    assert untraced("77.5", [], 0) == ["77.5"]
    # «Рядом» — с любой стороны и через любой пробел: перенос строки в Markdown — тоже пробел.
    for text in ("22\nBB", "77 \nBB", "77\t%", "77 %", "77 %", "77 bb", "77 $", "77$"):
        assert untraced(text, [], 0) == [text[:2]], repr(text)
    for text in ("$ 77", "$\xa077", "$\n77", "$\t77"):
        assert untraced(text, [], 0) == ["77"], repr(text)
    # Не пара — рука и рядом с `BB`-позицией: числа в ней нет.
    assert untraced("A5s BB коллирует", [], 0) == []


def test_digits_inside_other_words_are_numbers():
    # Исключения — только §9: число, приклеенное к слову, всё равно число.
    assert untraced("UTG2x, 3bet, x3, 8max, D30, 77x, x55", [], 0) == [
        "2", "3", "8", "30", "77", "55"
    ]
    # `N-бет` и `N-max` — с начала слова: цифра, приклеенная слева, остаётся числом.
    assert untraced("x3-бет, D4-bet, ф8-max", [], 0) == ["3", "4", "8"]
    # Хвост дроби — часть числа, а не рука.
    assert untraced("0.77 и 1,55", [], 0) == ["0.77", "1.55"]


def test_a_hand_is_written_high_card_first():
    # Класс — старшей картой вперёд, как его печатает движок: `5K` — тысячи фишек, а не рука.
    assert untraced("5K фишек, стек 8K, 9T, 25s, 89s, 77s", [], 0) == [
        "5", "8", "9", "25", "89", "77"
    ]
    assert untraced("98s, 32o, T9o, K9, A5, KQs", [], 0) == []


def test_a_display_is_read_by_the_same_rule():
    # `1` из `UTG+1` в печати линии следом не становится, `2.5` — становится.
    line = line_text([{"seatIndex": 3, "position": "UTG+1", "action": "raise", "toBb": 2.5}])
    assert line == "UTG+1 рейз до 2.5 BB"
    facts = [fact("line", line, "text")]
    assert numbers(line) == ["2.5"]
    assert untraced("UTG+1 рейз до 2.5 BB", facts, 0) == []
    assert untraced("в 1 раз", facts, 0) == ["1"]
    assert untraced("рука 77", _facts("герой 3-бетит с 77"), 0) == []
    assert untraced("77 BB", _facts("пара 77"), 0) == ["77"]


# --- coach.lint ------------------------------------------------------------------------------


@pytest.fixture
def hand(tmp_path):
    path = tmp_path / "hand.json"
    coach.start(str(path), _context())
    return path


def _displays(result):
    return [item["display"] for item in result["why"]]


def _numbers(displays):
    return {number for text in displays for number in numbers(text)}


def test_lint_answers_ok_or_the_untraced_numbers(hand):
    one = coach.step(str(hand), preflop_vs_3bet()[0])
    text = "Шаг 1. " + "; ".join(_displays(one))
    before = hand.read_bytes()
    assert coach.lint(str(hand), text) == {"ok": True}
    assert coach.lint(str(hand), text + " Рейз до 123.45 BB, шаг 2.") == {
        "ok": False,
        "untraced": ["123.45", "2"],
    }
    # Печать фактов — с одним или двумя знаками после точки: целых `2` и `123.45` в ней нет.
    assert not {"2", "123.45"} & _numbers(_displays(one))
    assert hand.read_bytes() == before


def test_lint_traces_the_numbers_of_every_step(hand):
    first, second = preflop_vs_3bet()
    one = coach.step(str(hand), first)
    two = coach.step(str(hand), second)
    past = sorted(_numbers(_displays(one)) - _numbers(_displays(two)) - {"1", "2"})
    assert past, "у шага 1 есть числа, которых нет у шага 2"
    assert coach.lint(str(hand), f"На шаге 2 — {'; '.join(_displays(two))}; раньше {past}") == {
        "ok": True
    }


def test_lint_traces_the_street_summary_of_the_closing_step(hand):
    # Итог префлопа — факты шага, что закрыл улицу; их числа — след.
    coach.step(str(hand), preflop_frame(3, folded={7, 2}))
    closing = coach.step(str(hand), flop_frame(3, {3: 2.0, 6: 2.0}, {7, 2, 4, 5}))
    summary = [item for item in closing["why"] if item["key"].startswith("preflop.")]
    others = [item for item in closing["why"] if not item["key"].startswith("preflop.")]
    only = sorted(_numbers(i["display"] for i in summary) - _numbers(i["display"] for i in others))
    assert only, "у итога есть числа, которых нет у остальных фактов шага"
    data = json.loads(hand.read_text(encoding="utf-8"))
    first = _numbers(i["display"] for i in data["steps"][0]["why"])
    assert set(only) - first
    assert coach.lint(str(hand), " ".join(only)) == {"ok": True}


def test_a_number_inside_a_refusal_reason_is_traced(hand):
    # Review Focus 7: число в тексте причины уже в `display` факта `reason.<советник>`.
    refused = coach.step(str(hand), preflop_frame(3, folded={7, 2}, starting={6: 1.0}))
    assert refused["advisor"] is None
    reason = "место 6 уже в олл-ине с блайнда: вне модели"
    assert {"key": "reason.preflop", "value": reason, "display": reason} in refused["why"]
    assert coach.lint(str(hand), f"Совета нет: {reason}.") == {"ok": True}
    assert coach.lint(str(hand), "Совета нет: место 7 уже в олл-ине.") == {
        "ok": False,
        "untraced": ["7"],
    }


@pytest.mark.parametrize(
    ("frames", "position", "role", "digit"),
    [(preflop_vs_3bet, "BTN", "3bettor", "3"), (preflop_vs_4bet, "UTG", "4bettor", "4")],
)
def test_a_role_leaves_no_trace_of_its_digit(hand, frames, position, role, digit):
    # D35: роль печатается словом — цифра кода `3bettor`/`4bettor` следом не становится, и
    # вписанное `3 BB` в раздаче из двух шагов линтер называет.
    for frame in frames():
        last = coach.step(str(hand), frame)
    facts = {item["key"]: item for item in last["why"]}
    assert facts[f"opponent.{position}.role"]["value"] == role
    assert coach.lint(str(hand), f"Рейз до {digit} BB.") == {"ok": False, "untraced": [digit]}


def test_lint_needs_the_hand_file(tmp_path):
    path = tmp_path / "hand.json"
    with pytest.raises(ValueError, match=f"^файла раздачи нет: {re.escape(str(path))}$"):
        coach.lint(str(path), "текст")


@pytest.mark.parametrize(
    "why",
    [None, "факты", [{"key": "a", "value": 1}], [{"key": "a", "value": 1, "display": 1}], ["1"]],
)
def test_a_damaged_why_is_named(hand, why):
    coach.step(str(hand), preflop_vs_3bet()[0])
    data = json.loads(hand.read_text(encoding="utf-8"))
    if why is None:
        del data["steps"][0]["why"]
    else:
        data["steps"][0]["why"] = why
    hand.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="^файл раздачи повреждён: steps$"):
        coach.lint(str(hand), "текст")


# --- CLI -------------------------------------------------------------------------------------


def run(argv, capsys):
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_coach_lint_cli(hand, tmp_path, monkeypatch, capsys):
    one = coach.step(str(hand), preflop_vs_3bet()[0])
    good = tmp_path / "answer.md"
    good.write_text("; ".join(_displays(one)), encoding="utf-8")
    assert run(["coach", "lint", "--hand", str(hand), "--text", str(good)], capsys) == (
        0,
        {"ok": True},
    )
    bad = tmp_path / "bad.md"
    bad.write_text("Рейз до 123.45 BB.", encoding="utf-8")
    assert run(["coach", "lint", "--hand", str(hand), "--text", str(bad)], capsys) == (
        0,
        {"ok": False, "untraced": ["123.45"]},
    )
    monkeypatch.setattr(sys, "stdin", console_stdin("Шаг 1, шаг 9."))
    assert run(["coach", "lint", "--hand", str(hand), "--text", "-"], capsys) == (
        0,
        {"ok": False, "untraced": ["9"]},
    )


def test_coach_lint_cli_reads_stdin_in_utf8(hand, tmp_path, monkeypatch, capsys):
    # Кириллица из пайпа консоли Windows: без UTF-8 `3-бет` не узнаётся и `3` — ложно без следа.
    coach.step(str(hand), preflop_vs_3bet()[0])
    text = "Твой 3-бет до 123.45 BB."
    path = tmp_path / "answer.md"
    path.write_text(text, encoding="utf-8")
    expected = (0, {"ok": False, "untraced": ["123.45"]})
    assert run(["coach", "lint", "--hand", str(hand), "--text", str(path)], capsys) == expected
    monkeypatch.setattr(sys, "stdin", console_stdin(text))
    assert run(["coach", "lint", "--hand", str(hand), "--text", "-"], capsys) == expected


def test_coach_lint_cli_errors(hand, tmp_path, capsys):
    missing = str(tmp_path / "nope.md")
    code, data = run(["coach", "lint", "--hand", str(hand), "--text", missing], capsys)
    assert code == 1
    assert data["error"].startswith(f"не удалось прочитать {missing!r}")
    other = str(tmp_path / "other.json")
    good = tmp_path / "answer.md"
    good.write_text("текст", encoding="utf-8")
    code, data = run(["coach", "lint", "--hand", other, "--text", str(good)], capsys)
    assert (code, data) == (1, {"error": f"файла раздачи нет: {other}"})
