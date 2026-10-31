"""Файл раздачи и команды `coach start/step/undo` (план 6, Задача 6).

Спека тренера §5, инварианты 3–4 §12. Шаг — тот же `advise` на кадрах файла с ответами прошлых
шагов в `history`; файл меняется только целиком и только удачным шагом.
"""

import json
import re

import pytest

from conftest import _context, preflop_frame, preflop_vs_3bet, pushfold_first_in_node
from poker_engine import coach
from poker_engine.advice import advise, why
from poker_engine.handstate import node_from_dict


@pytest.fixture
def hand(tmp_path):
    path = tmp_path / "hand.json"
    coach.start(str(path), _context())
    return path


def _step(path, frame):
    return coach.step(str(path), frame)


# --- start -----------------------------------------------------------------------------------


def test_start_creates_an_empty_hand(hand):
    assert json.loads(hand.read_text(encoding="utf-8")) == {
        "format": "poker-coach-hand",
        "version": 1,
        "context": _context(),
        "frames": [],
        "steps": [],
        "streets": {},
    }


def test_start_does_not_overwrite(hand):
    before = hand.read_bytes()
    with pytest.raises(ValueError, match=f"^файл раздачи уже есть: {re.escape(str(hand))}$"):
        coach.start(str(hand), {**_context(), "entrants": 2000})
    assert hand.read_bytes() == before


def test_start_checks_the_context_at_once(tmp_path):
    path = tmp_path / "hand.json"
    with pytest.raises(ValueError, match=re.escape("осталось игроков (782) больше, чем входов (5)")):
        coach.start(str(path), {**_context(), "entrants": 5})
    assert not path.exists()


@pytest.mark.parametrize("context", [None, [1]])
def test_start_refuses_a_context_that_is_not_an_object(tmp_path, context):
    # CLI требует объект сам (`_read_json`), через API отказ даёт только гард `frames`.
    path = tmp_path / "hand.json"
    with pytest.raises(
        ValueError,
        match=f"^поле 'context' должно быть объектом, получено {re.escape(repr(context))}$",
    ):
        coach.start(str(path), context)
    assert not path.exists()


def test_start_takes_the_average_stack_in_chips(tmp_path):
    # Большой блайнд придёт с кадром: на старте проверяется только само число.
    raw = {**_context(), "averageStackChips": 70700}
    del raw["averageStackBb"]
    path = tmp_path / "hand.json"
    coach.start(str(path), raw)
    assert json.loads(path.read_text(encoding="utf-8"))["context"] == raw
    with pytest.raises(ValueError, match=re.escape("средний стек должен быть > 0, получено -1.0")):
        coach.start(str(tmp_path / "other.json"), {**raw, "averageStackChips": -1})


def test_start_late_reg_overrides_context(tmp_path):
    closed = {**_context(), "lateRegOpen": False}
    path = tmp_path / "hand.json"
    coach.start(str(path), closed, late_reg_open=True)
    assert json.loads(path.read_text(encoding="utf-8"))["context"]["lateRegOpen"] is True
    assert closed["lateRegOpen"] is False  # вход не меняется
    other = tmp_path / "other.json"
    coach.start(str(other), closed)
    assert json.loads(other.read_text(encoding="utf-8"))["context"]["lateRegOpen"] is False
    third = tmp_path / "third.json"
    coach.start(str(third), _context(), late_reg_open=False)
    assert json.loads(third.read_text(encoding="utf-8"))["context"]["lateRegOpen"] is False


def test_start_checks_the_starting_stack(tmp_path):
    path = tmp_path / "hand.json"
    with pytest.raises(ValueError, match="стартовый стек должен быть > 0"):
        coach.start(str(path), {**_context(), "startingStackChips": 0})
    assert not path.exists()


def test_step_derives_the_average_stack_from_the_starting_stack(tmp_path):
    raw = {**_context(), "startingStackChips": 50000, "lateRegOpen": False}
    del raw["averageStackBb"]
    path = tmp_path / "hand.json"
    coach.start(str(path), raw)
    frame = {**preflop_frame(3, folded={7, 2}), "blinds": {"sb": 700, "bb": 1400, "ante": 175}}
    answer = _step(path, frame)["answer"]
    average = 50000 * raw["entrants"] / frame["playersLeft"] / 1400
    expected = {**raw, "averageStackBb": average, "averageStackSource": "lobby"}
    assert answer == advise(expected, [frame], [])


# --- step ------------------------------------------------------------------------------------


def test_a_step_is_advise_on_the_frames_with_the_past_answers(hand):
    first, second = preflop_vs_3bet()
    one = _step(hand, first)
    expected_one = advise(_context(), [first], [])
    why_one = why(expected_one, node_from_dict(first))
    assert one == {
        "step": 1, "advisor": "preflop", "answer": expected_one, "why": why_one, "streets": {}
    }
    two = _step(hand, second)
    assert two["step"] == 2
    assert two["answer"] == advise(_context(), [first, second], [expected_one])
    assert two["why"] == why(two["answer"], node_from_dict(second))
    stored = json.loads(hand.read_text(encoding="utf-8"))
    assert stored["frames"] == [first, second]
    assert stored["steps"] == [
        {"frame": 1, "advisor": "preflop", "answer": expected_one, "why": why_one},
        {"frame": 2, "advisor": two["advisor"], "answer": two["answer"], "why": two["why"]},
    ]


def test_the_history_of_step_n_is_the_answers_of_steps_before_it(hand, monkeypatch):
    # Инвариант 4: ответы шагов 1..N−1 по порядку, отказ советников — тоже ответ шага. Подмена
    # отвечает отказами: факты шага (`why`) ищут советника ответа в реестре.
    seen = []

    def fake(context, nodes, history):
        seen.append(list(history))
        if len(nodes) == 2:
            return {"advisor": None, "notApplicable": []}
        return {"advisor": None, "notApplicable": [{"advisor": "fake", "reason": str(len(nodes))}]}

    monkeypatch.setattr(coach, "advise", fake)
    frames = [
        preflop_frame(3, folded={7, 2}),
        preflop_frame(3, {3: 2.0, 4: 7.0}, folded={7, 2, 5, 6}),
        preflop_frame(3, {3: 16.0, 4: 40.0}, folded={7, 2, 5, 6}),
    ]
    answers = [_step(hand, frame)["answer"] for frame in frames]
    assert seen == [[], answers[:1], answers[:2]]
    assert answers[1] == {"advisor": None, "notApplicable": []}


def test_a_refusal_of_the_advisors_is_a_stored_step(hand):
    # Герой `CO` открыл до 2.0, `BTN` заколлировал, блайнды сфолдили — флоп. Советников флопа
    # нет: отказ — нормальный шаг, он хранится с `advisor: null`.
    first = preflop_frame(3, folded={7, 2})
    flop = preflop_frame(3, {3: 2.0, 4: 2.0}, folded={7, 2, 5, 6})
    for seat in flop["seats"]:
        seat["investedBb"] = 0.0
    flop.update(street="flop", board=["8c", "2s", "9d"], toCallBb=0.0)
    _step(hand, first)
    result = _step(hand, flop)
    assert result["advisor"] is None and result["answer"]["advisor"] is None
    assert json.loads(hand.read_text(encoding="utf-8"))["steps"][-1]["advisor"] is None


def test_a_deviation_of_the_hero_is_flagged(hand):
    # Инвариант 4: у всех 8 BB, `CO` первым в банк — совет `pushfold` (олл-ин или фолд). Герой
    # открыл до 2.0, `BTN` пошёл олл-ин — следующий шаг помечен `line_deviates`.
    starting = dict.fromkeys(range(2, 8), 8.0)
    first = _step(hand, preflop_frame(3, folded={7, 2}, starting=starting))
    assert first["advisor"] == "pushfold"
    second = _step(
        hand, preflop_frame(3, {3: 2.0, 4: 8.0}, folded={7, 2, 5, 6}, starting=starting)
    )
    assert second["answer"]["spot"] == "vs_allin_after_raise"
    assert "line_deviates" in second["answer"]["flags"]


def test_a_frame_in_chips_is_advised_like_the_frame_in_big_blinds(hand):
    # Фишки — целые, как на экране; кадр в BB — те же фишки, поделённые на 1400.
    raw = pushfold_first_in_node()
    chips = {key: value for key, value in raw.items() if not key.endswith("Bb")}
    chips.update(unit="chips", potChips=3150, toCallChips=1400)
    chips["seats"] = [
        {
            **{key: value for key, value in seat.items() if not key.endswith("Bb")},
            "stackChips": round(seat["stackBb"] * 1400),
            "investedChips": round(seat["investedBb"] * 1400),
        }
        for seat in raw["seats"]
    ]
    big_blinds = {**raw, "potBb": 3150 / 1400, "toCallBb": 1400 / 1400}
    big_blinds["seats"] = [
        {
            **seat,
            "stackBb": round(seat["stackBb"] * 1400) / 1400,
            "investedBb": round(seat["investedBb"] * 1400) / 1400,
        }
        for seat in raw["seats"]
    ]
    assert _step(hand, chips)["answer"] == advise(_context(), [big_blinds], [])


@pytest.mark.parametrize(
    ("broken", "text"),
    [
        # Битый кадр: смешение единиц.
        (lambda f: f.update(potChips=4.0), "поле potChips не для кадра в bb"),
        # Валидатор всей раздачи: стек `HJ` вырос.
        (
            lambda f: f["seats"][0].update(stackBb=45.0),
            "стек на месте 2 вырос внутри раздачи: было 40.0 BB, стало 45.0 BB",
        ),
    ],
    ids=["frame", "hand"],
)
def test_a_failed_step_leaves_the_file_byte_for_byte(hand, broken, text):
    # Инвариант 3.
    first, second = preflop_vs_3bet()
    _step(hand, first)
    before = hand.read_bytes()
    broken(second)
    with pytest.raises(ValueError, match=f"^{re.escape(text)}$"):
        _step(hand, second)
    assert hand.read_bytes() == before
    assert [p.name for p in hand.parent.iterdir()] == [hand.name]


def test_a_write_that_fails_on_disk_leaves_the_file_byte_for_byte(hand, monkeypatch):
    # Запись атомарна: новое содержимое ложится во временный файл рядом, на место встаёт
    # `os.replace`. Сбой на этом шаге — отказ с текстом, файл прежний, временного не осталось.
    before = hand.read_bytes()

    def broken(source, target):
        raise OSError("диск полон")

    monkeypatch.setattr(coach.os, "replace", broken)
    with pytest.raises(ValueError, match=f"^не удалось записать {re.escape(repr(str(hand)))}: "):
        _step(hand, pushfold_first_in_node())
    assert hand.read_bytes() == before
    assert [p.name for p in hand.parent.iterdir()] == [hand.name]


def test_a_frame_must_be_an_object(hand):
    before = hand.read_bytes()
    with pytest.raises(ValueError, match=re.escape("кадр должен быть объектом, получено 5")):
        _step(hand, 5)
    assert hand.read_bytes() == before


# --- undo ------------------------------------------------------------------------------------


def test_step_and_undo_leave_the_file_byte_for_byte(hand):
    # Инвариант 3; Review Focus 6 — итог улицы снимается вместе с кадром (Задача 7).
    first, second = preflop_vs_3bet()
    empty = hand.read_bytes()
    _step(hand, first)
    one = hand.read_bytes()
    _step(hand, second)
    assert coach.undo(str(hand)) == {"undone": 2, "steps": 1}
    assert hand.read_bytes() == one
    assert coach.undo(str(hand)) == {"undone": 1, "steps": 0}
    assert hand.read_bytes() == empty


def test_undo_with_no_frames_is_refused(hand):
    before = hand.read_bytes()
    with pytest.raises(ValueError, match="^в раздаче нет кадров: отменять нечего$"):
        coach.undo(str(hand))
    assert hand.read_bytes() == before


# --- файл ------------------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["step", "undo"])
def test_a_missing_file_is_named(tmp_path, command):
    path = str(tmp_path / "nope.json")
    call = (lambda: coach.step(path, pushfold_first_in_node())) if command == "step" else (
        lambda: coach.undo(path)
    )
    with pytest.raises(ValueError, match=f"^файла раздачи нет: {re.escape(path)}$"):
        call()


@pytest.mark.parametrize(
    ("damage", "what"),
    [
        (lambda d: d.update(format="poker-hand"), "format"),
        (lambda d: d.pop("format"), "format"),
        (lambda d: d.update(version=2), "version"),
        (lambda d: d.update(version=True), "version"),
        (lambda d: d.update(context=[]), "context"),
        (lambda d: d.update(frames={}), "frames"),
        (lambda d: d.update(frames=[1]), "frames"),
        (lambda d: d.update(steps=None), "steps"),
        (lambda d: d.update(steps=[{"frame": 1}]), "steps"),
        # Длины сходятся, у шага нет ответа: без проверки — `KeyError` мимо `cli.main`.
        (
            lambda d: d.update(frames=[pushfold_first_in_node()], steps=[{"frame": 1}]),
            "steps",
        ),
        (lambda d: d.update(streets=[]), "streets"),
    ],
)
def test_a_damaged_file_is_named_by_its_field(hand, damage, what):
    data = json.loads(hand.read_text(encoding="utf-8"))
    damage(data)
    hand.write_text(json.dumps(data), encoding="utf-8")
    for call in (lambda: coach.step(str(hand), pushfold_first_in_node()), lambda: coach.undo(str(hand))):
        with pytest.raises(ValueError, match=f"^файл раздачи повреждён: {what}$"):
            call()


def test_a_file_that_cannot_be_read_is_named(tmp_path):
    # Путь раздачи — папка: `open` бросает `OSError` на обеих ОС, наружу — текст с путём.
    path = str(tmp_path)
    with pytest.raises(ValueError, match=f"^не удалось прочитать {re.escape(repr(path))}: "):
        coach.undo(path)


def test_a_file_that_is_not_json_is_damaged(hand):
    hand.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="^файл раздачи повреждён: не JSON$"):
        coach.undo(str(hand))


def test_steps_must_match_frames(hand):
    data = json.loads(hand.read_text(encoding="utf-8"))
    data["frames"] = [pushfold_first_in_node()]
    hand.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="^файл раздачи повреждён: steps$"):
        coach.undo(str(hand))
