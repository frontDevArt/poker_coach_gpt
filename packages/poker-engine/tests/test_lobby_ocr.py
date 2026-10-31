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
