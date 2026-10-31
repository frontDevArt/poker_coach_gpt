"""Распознавание лобби GG (план D40, Задача 2; спека лобби §8).

Тест на настоящем кадре читает скриншот пользователя (в репозитории его нет) и гоняет RapidOCR:
около 30 с на i5-4460; без группы `[lobby]` или без файла он пропускается. Правило маски ников
рекордера и отказ без зависимостей проверяются без распознавания.
"""

import importlib.util
import json
import pathlib
import re
import sys

import pytest

from poker_engine.lobby_read import Line

LOBBY_SHOTS = pathlib.Path(r"C:\Users\Admin\Documents\Screenshots\lobby\fifty-stack-2026-10-30")
FIXTURES = pathlib.Path(__file__).parent / "data" / "lobby"
RECORDER = pathlib.Path(__file__).parent.parent / "scripts" / "record_lobby_fixtures.py"


def _recorder():
    spec = importlib.util.spec_from_file_location("record_lobby_fixtures", RECORDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_prizes_are_read():
    pytest.importorskip("rapidocr_onnxruntime")
    shot = LOBBY_SHOTS / "pass2-prizes-level17.png"
    if not shot.is_file():
        pytest.skip(f"нет скриншота {shot}")
    from poker_engine.lobby_ocr import ocr_image

    lines, width, height = ocr_image(str(shot))
    assert width > 1000 and height > 1000  # размер PNG, не масштаб просмотра
    texts = [re.sub(r"\s*~\s*", "~", line.text) for line in lines]
    for wanted in ("$11,896.06", "$1,450.17", "208~330", "802/2,351"):
        assert any(wanted in text for text in texts), wanted


def test_place_column_is_read_in_order():
    # Классификатор угла RapidOCR читал «6» как «9» (и наоборот) с уверенностью 1.0
    pytest.importorskip("rapidocr_onnxruntime")
    shot = LOBBY_SHOTS / "pass1-prizes-level14.png"
    if not shot.is_file():
        pytest.skip(f"нет скриншота {shot}")
    from poker_engine.lobby_ocr import ocr_image

    lines, width, _ = ocr_image(str(shot))
    places = [
        line
        for line in lines
        if line.text.isdigit() and line.x < 0.40 * width and line.y > 450
    ]
    assert [line.text for line in sorted(places, key=lambda line: line.y)] == [
        str(place) for place in range(1, 11)
    ]
    assert any(line.text == "1474|349" for line in lines)


def test_ocr_without_dependencies_refuses(monkeypatch):
    import poker_engine.lobby_ocr as lobby_ocr

    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", None)
    monkeypatch.setattr(lobby_ocr, "_engine", None)
    with pytest.raises(ValueError, match=r"для разбора лобби нужны зависимости: pip install"):
        lobby_ocr.ocr_image("нет-такого-кадра.png")


@pytest.mark.parametrize(
    ("x", "y", "masked"),
    [
        (60, 250, True),  # панель «Бэкинг»
        (900, 300, True),  # панель «Игроки»
        (60, 157, True),  # строка лидеров шапки
        (60, 50, False),  # заголовок турнира
        (500, 157, False),  # «Призовой фонд» шапки
        (830, 120, False),  # счётчики шапки справа
        (500, 400, False),  # средняя колонка
    ],
)
def test_nick_mask_zones(x, y, masked):
    recorder = _recorder()
    line = Line(text="ник", x=x, y=y, w=40, h=20, score=0.9)
    data = recorder.fixture_dict([line], 1200, 740, "2026-10-30")
    assert data["lines"][0]["text"] == (recorder.MASK if masked else "ник")
    assert data["lines"][0]["score"] == 0.9


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.stem)
def test_fixture_format(fixture):
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert set(data) == {"width", "height", "captured", "lines"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["captured"])
    assert data["lines"]
    for line in data["lines"]:
        assert set(line) == {"text", "x", "y", "w", "h", "score"}
        assert 0 <= line["score"] <= 1


def _fixture(name):
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return [
        (re.sub(r"\s*([~|/])\s*", lambda m: m.group(1), line["text"]), line["y"] + line["h"] / 2)
        for line in data["lines"]
    ]


def _row_pairs(rows, place_pattern):
    """Пары (место, приз) средней колонки: ячейка места и ячейка `$` на одной строке."""
    places = [(t, y) for t, y in rows if re.fullmatch(place_pattern, t)]
    prizes = [(t, y) for t, y in rows if re.fullmatch(r"\$[\d,]+\.\d\d", t)]
    pairs = []
    for text, y in places:
        near = [t for t, py in prizes if abs(py - y) < 6]
        if near:
            pairs.append((text, near[0]))
    return pairs


def test_fixture_final_payouts_are_exact():
    rows = _fixture("pass2-prizes-level17")
    pairs = _row_pairs(rows, r"\d+(~\d+)?")
    assert pairs == [
        ("1", "$1,450.17"), ("2", "$1,116.80"), ("3", "$861.17"), ("4", "$664.05"),
        ("5", "$512.05"), ("6", "$394.84"), ("7", "$304.47"), ("8", "$234.77"),
        ("9", "$181.03"), ("10", "$119.02"), ("11~12", "$94.42"), ("13~15", "$74.91"),
        ("16~19", "$59.43"), ("20~26", "$47.14"), ("27~37", "$37.40"), ("38~55", "$29.67"),
        ("56~84", "$23.54"), ("85~131", "$18.67"), ("132~207", "$14.81"),
        ("208~330", "$11.75"),
    ]  # fmt: skip
    texts = [t for t, _ in rows]
    for wanted in ("$11,896.06", "802/2,351", "1808|543", "146,571"):
        assert any(wanted in t for t in texts), wanted
    assert any(t.startswith("330") for t in texts)


def test_fixture_provisional_payouts_are_exact():
    rows = _fixture("pass1-prizes-level14")
    pairs = _row_pairs(rows, r"\d+(~\d+)?")
    assert len(pairs) == 19
    assert pairs[0] == ("1", "$1,154.30") and pairs[-1] == ("170~270", "$11.15")
    assert [p for p, _ in pairs[:10]] == [str(n) for n in range(1, 11)]
    assert dict(pairs)["6"] == "$314.40" and dict(pairs)["9"] == "$144.15"
    texts = [t for t, _ in rows]
    for wanted in ("951/1,823", "1474|349", "$9,224.38", "95,951"):
        assert any(wanted in t for t in texts), wanted


def test_fixture_info_and_old_shots_values():
    info = [t for t, _ in _fixture("pass1-info-level13")]
    for wanted in ("$5.06+$0.44", "50,000", "30, 23:05", "17)", "1455|335", "$9,057.40"):
        assert any(wanted in t for t in info), wanted
    assert any(t.endswith("8MNH") for t in info)  # интервал блайндов «8 Мин»
    assert any(t.startswith("8MrpoKOB") for t in info)  # «8 игроков на стол»
    old = _fixture("win_2026-09-10_00-31-04")
    assert ("13~15", "$58.94") in _row_pairs(old, r"\d+(~\d+)?")
    texts = [t for t, _ in old]
    assert any(t.startswith("165") for t in texts)
    assert any("783/1,134" in t for t in texts)
    small = [t for t, _ in _fixture("win_2026-09-10_00-29-09")]
    assert any("09, 23:05" in t for t in small) and any("$8,000" in t for t in small)
