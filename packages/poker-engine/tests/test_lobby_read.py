"""Разбор кадра лобби в поля (план D40, Задача 3; спека лобби §3, §8).

Тесты идут на записанных выходах OCR (фикстуры Задачи 2), без RapidOCR. Ожидаемые числа сняты
со скриншотов пользователя. Локальный тест в конце гоняет настоящее распознавание на пяти кадрах
10-30 (~1–1.5 мин на i5-4460); без группы `[lobby]` или без файлов он пропускается.
"""

import dataclasses
import json
import pathlib
import re

import pytest
from conftest import LOBBY_SHOTS

from poker_engine.lobby_read import Header, Info, Line, read_shot

FIXTURES = pathlib.Path(__file__).parent / "data" / "lobby"

FINAL_PAYOUTS = [
    (1, 1, 1450.17), (2, 2, 1116.80), (3, 3, 861.17), (4, 4, 664.05), (5, 5, 512.05),
    (6, 6, 394.84), (7, 7, 304.47), (8, 8, 234.77), (9, 9, 181.03), (10, 10, 119.02),
    (11, 12, 94.42), (13, 15, 74.91), (16, 19, 59.43), (20, 26, 47.14), (27, 37, 37.40),
    (38, 55, 29.67), (56, 84, 23.54), (85, 131, 18.67), (132, 207, 14.81), (208, 330, 11.75),
]  # fmt: skip


def _fixture(name):
    """Строки, ширина и высота записанного кадра."""
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    lines = [Line(**line) for line in data["lines"]]
    return lines, data["width"], data["height"]


def _replace(lines, old, **changes):
    """Те же строки, у единственной строки с текстом `old` заменены поля."""
    assert [line.text for line in lines].count(old) == 1, old
    return [dataclasses.replace(line, **changes) if line.text == old else line for line in lines]


def _without(lines, text):
    assert [line.text for line in lines].count(text) == 1, text
    return [line for line in lines if line.text != text]


def _torn(lines, text, head, tail, gap=None):
    """Строка `text` разорвана на две рамки вплотную: `head` слева, `tail` справа; зазор — 1 px
    или `gap` высот строки."""
    line = next(line for line in lines if line.text == text)
    cut = line.w * len(head) / len(text)
    return _without(lines, text) + [
        dataclasses.replace(line, text=head, w=cut - (1.0 if gap is None else gap * line.h)),
        dataclasses.replace(line, text=tail, x=line.x + cut, w=line.w - cut),
    ]


def test_final_prizes_shot():  # pass2-prizes-level17
    shot = read_shot(*_fixture("pass2-prizes-level17"))
    assert shot.kind == "prizes" and shot.title == "Fifty Stack $5.50"
    assert shot.places_paid == 330
    assert shot.payouts == FINAL_PAYOUTS
    assert shot.header == Header(
        level=17, players_left=802, entrants=2351, unique=1808, reentries=543,
        prize_pool_usd=11896.06, buy_in_usd=5.50, average_stack_chips=146571,
    )  # fmt: skip
    assert shot.info is None and shot.low_confidence == []


def test_provisional_prizes_shot():  # pass1-prizes-level14
    shot = read_shot(*_fixture("pass1-prizes-level14"))
    assert shot.places_paid == 270 and len(shot.payouts) == 19
    assert shot.payouts[0] == (1, 1, 1154.30) and shot.payouts[-1] == (170, 270, 11.15)
    assert (shot.header.players_left, shot.header.entrants) == (951, 1823)
    assert (shot.header.unique, shot.header.reentries) == (1474, 349)
    assert shot.header.prize_pool_usd == 9224.38 and shot.header.average_stack_chips == 95951
    assert shot.low_confidence == []


def test_provisional_payouts_are_joined_ranges():
    # места — диапазоны как прочитаны: каждая строка начинается с «прошлый конец + 1»
    payouts = read_shot(*_fixture("pass1-prizes-level14")).payouts
    assert all(lo <= hi for lo, hi, _ in payouts)
    assert all(nxt[0] == cur[1] + 1 for cur, nxt in zip(payouts, payouts[1:]))
    assert [prize for *_, prize in payouts] == sorted((p for *_, p in payouts), reverse=True)


def test_final_payouts_sum_to_prize_pool():
    # §3: после закрытия регистрации Σ приз × число мест = «Призовой фонд» до цента
    shot = read_shot(*_fixture("pass2-prizes-level17"))
    total = sum((hi - lo + 1) * prize for lo, hi, prize in shot.payouts)
    assert total == pytest.approx(shot.header.prize_pool_usd, abs=0.005)
    assert shot.payouts[-1][1] == shot.places_paid


def test_header_is_consistent_with_itself():
    # §3: уникальные + ре-энтри = входы; средний стек = 50,000 × входы / осталось (заход 2)
    header = read_shot(*_fixture("pass2-prizes-level17")).header
    assert header.unique + header.reentries == header.entrants
    assert header.average_stack_chips == round(50_000 * header.entrants / header.players_left)


def test_info_shot():  # pass1-info-level13
    shot = read_shot(*_fixture("pass1-info-level13"))
    assert shot.kind == "info" and shot.header.level == 13
    assert shot.info == Info(
        prize_share_usd=5.06, fee_usd=0.44, starting_stack_chips=50000, start=(10, 30, 23, 5),
        late_reg_close_level=17, blind_interval_min=8, seats_per_table=8, early_bird=True,
    )  # fmt: skip
    assert shot.payouts == [] and shot.places_paid is None and shot.low_confidence == []


def test_info_shot_after_late_registration():  # pass2-info-level17: «Мин. стек» вместо стартового
    shot = read_shot(*_fixture("pass2-info-level17"))
    assert shot.kind == "info" and shot.info.starting_stack_chips == 50000
    assert shot.header.average_stack_chips == 146206  # не «Мин. стек» 6,800 и не макс. 961,373
    assert (shot.header.players_left, shot.header.entrants) == (805, 2351)
    assert shot.low_confidence == []


def test_old_small_window_shots():  # 1200×740, 2026-09-10
    prizes = read_shot(*_fixture("win_2026-09-10_00-31-04"))
    assert prizes.places_paid == 165 and prizes.payouts[-1] == (13, 15, 58.94)
    assert (prizes.header.players_left, prizes.header.entrants) == (783, 1134)
    info = read_shot(*_fixture("win_2026-09-10_00-29-09"))
    assert info.info.start == (9, 9, 23, 5) and info.info.seats_per_table == 8
    assert info.info.early_bird  # «Ранняя пташка» двойником, не «Early Bird»
    assert info.header.prize_pool_usd == 8000.0  # оверлей: строка «Оверлей» в шапке есть
    assert info.header.buy_in_usd == 5.50  # не гарантия $8,000 и не оверлей $2,398.58
    assert prizes.low_confidence == [] and info.low_confidence == []


@pytest.mark.parametrize("name", ["pass1-structure-level16", "win_2026-09-10_00-29-48"])
def test_structure_shot_is_other(name):
    # таблица блайндов и «входов → призовых мест» вкладки «Структура» — не выплаты
    shot = read_shot(*_fixture(name))
    assert shot.kind == "other"
    assert shot.payouts == [] and shot.places_paid is None and shot.info is None


def test_noisy_numbers_normalize():  # Review Focus 1, синтетические Line
    lines, width, height = _fixture("pass2-prizes-level17")
    lines = _replace(lines, "146,571(29.3 BB)", text="（146,571(29.3 BB)")
    lines = _replace(lines, "16~19", text="16 ~19")
    lines = _replace(lines, "11~12", text="11-12")
    title = next(line for line in lines if line.text == "Fifty Stack $5.50")
    lines = _without(lines, "Fifty Stack $5.50") + [
        dataclasses.replace(title, text="Fifty", w=48.0),
        dataclasses.replace(title, text="Stack $5.50", x=title.x + 56.0, w=title.w - 56.0),
    ]
    shot = read_shot(lines, width, height)
    assert shot.header.average_stack_chips == 146571
    assert (16, 19, 59.43) in shot.payouts and (11, 12, 94.42) in shot.payouts
    assert shot.title == "Fifty Stack $5.50"
    assert shot.payouts == FINAL_PAYOUTS


def test_unpaired_payout_cell_is_skipped_not_guessed():
    # нет ячейки места — строка выпадает, место по порядку строк не достраивается
    lines, width, height = _fixture("pass2-prizes-level17")
    shot = read_shot(_without(lines, "20 ~26"), width, height)
    assert (20, 26, 47.14) not in shot.payouts and len(shot.payouts) == 19
    assert shot.payouts == [row for row in FINAL_PAYOUTS if row[0] != 20]


def test_scrolled_prizes_without_places_count():
    # продолжение после прокрутки (§5): «N призовых мест» уехало вверх, таблица — выплаты
    lines, width, height = _fixture("pass2-prizes-level17")
    shot = read_shot(_without(lines, "330 npM30BbIX MeCT"), width, height)
    assert shot.kind == "prizes" and shot.places_paid is None and shot.payouts == FINAL_PAYOUTS


@pytest.mark.parametrize(
    ("missing", "field"),
    [
        ("802/2,351", "счётчик игроков"),
        ("1808|543", "уникальные и ре-энтри"),
        ("$11,896.06", "призовой фонд"),
        ("$5.50", "бай-ин"),
        ("146,571(29.3 BB)", "средний стек"),
        ("ypOBeHb17", "уровень"),
        ("Fifty Stack $5.50", "название"),
    ],
)
def test_missing_header_field_refuses(missing, field):
    lines, width, height = _fixture("pass2-prizes-level17")
    with pytest.raises(ValueError, match=f"^на кадре не найдено: {field}$"):
        read_shot(_without(lines, missing), width, height)


def test_header_without_money_refuses():
    lines, width, height = _fixture("pass2-prizes-level17")
    for text in ("$11,896.06", "$5.50", "$9,000"):
        lines = _without(lines, text)
    with pytest.raises(ValueError, match="^на кадре не найдено: призовой фонд$"):
        read_shot(lines, width, height)


@pytest.mark.parametrize(
    "edit",
    [
        lambda lines: _without(lines, "$5.50"),
        lambda lines: _replace(lines, "$5.50", text="Dav-UH $5.50"),  # склеен с подписью
    ],
    ids=["removed", "glued-to-label"],
)
def test_old_frame_without_buy_in_refuses(edit):
    # гарантия $8,000 стоит в столбце бай-ина, но в ряду «A|B», а не счётчика: бай-ином не станет
    lines, width, height = _fixture("win_2026-09-10_00-29-09")
    with pytest.raises(ValueError, match="^на кадре не найдено: бай-ин$"):
        read_shot(edit(lines), width, height)


def test_overlay_label_is_not_the_title():
    # «Оверлей $2,398.58» правее левой четверти шапки: без настоящего названия — отказ
    lines, width, height = _fixture("win_2026-09-10_00-29-09")
    lines = _replace(_without(lines, "Fifty Stack $5.50"), "$2,398.58", text="OBepnen $2,398.58")
    with pytest.raises(ValueError, match="^на кадре не найдено: название$"):
        read_shot(lines, width, height)


@pytest.mark.parametrize(
    ("text", "head", "tail", "field"),
    [
        ("$11,896.06", "$11,896", ".06", "призовой фонд"),
        ("$1,450.17", "$1,450", ".17", "выплата места 1"),
        ("1808|543", "1808|5", "43", "уникальные и ре-энтри"),
        ("1808|543", "18", "08|543", "уникальные и ре-энтри"),  # хвост читается сам по себе
        ("802/2,351", "802/2", ",351", "счётчик игроков"),
        # диапазон мест по разделителю: иначе (11, 11, …) или (12, 12, …) молча
        ("11~12", "11", "~12", "выплата места 11"),
        ("11~12", "11~", "12", "выплата места 12"),
        ("16~19", "16", "-19", "выплата места 16"),  # `-` вне рамки `_norm` в `~` не меняет
        ("16~19", "16-", "19", "выплата места 19"),
        ("Fifty Stack $5.50", "Fifty Stack $5", ".50", "название"),  # цена названия — число
    ],
)
@pytest.mark.parametrize("gap", [None, 0.45], ids=["1px", "0.45h"])
def test_number_torn_across_boxes_refuses(text, head, tail, field, gap):
    # R10: число в двух рамках вплотную не склеивается и не обрезается — отказ с именем поля
    lines, width, height = _fixture("pass2-prizes-level17")
    pieces = f"«{re.escape(head)}» \\+ «{re.escape(tail)}»"
    with pytest.raises(ValueError, match=f"^на кадре поле «{field}» разорвано на части: {pieces}$"):
        read_shot(_torn(lines, text, head, tail, gap), width, height)


@pytest.mark.parametrize(
    "name",
    ["pass1-prizes-level14", "pass2-prizes-level17", "win_2026-09-10_00-31-04"],
)
def test_every_torn_range_row_refuses(name):
    # каждая строка-диапазон всех трёх кадров выплат, разорванная по `~` с обеих сторон
    lines, width, height = _fixture(name)
    ranges = [line.text for line in lines if re.fullmatch(r"\d+\s*~\s*\d+", line.text)]
    assert ranges
    for text in ranges:
        lo, hi = re.split(r"\s*~\s*", text)
        for head, tail, place in ((lo, f"~{hi}", lo), (f"{lo}~", hi, hi)):
            with pytest.raises(ValueError, match=f"^на кадре поле «выплата места {place}»"):
                read_shot(_torn(lines, text, head, tail), width, height)


def test_next_prize_in_three_boxes_is_not_a_payout():
    # «208 ~ 330th - $11.75» над таблицей тремя рамками: пара «208~330» — «$11.75» правее
    # столбцов таблицы и в выплаты не попадает
    lines, width, height = _fixture("pass2-prizes-level17")
    line = next(line for line in lines if line.text == "208 ~ 330th - $11.75")
    lines = _without(lines, line.text) + [
        dataclasses.replace(line, text="208 ~ 330", w=60.0),
        dataclasses.replace(line, text="th -", x=line.x + 64.0, w=24.0),
        dataclasses.replace(line, text="$11.75", x=line.x + 96.0, w=line.w - 96.0),
    ]
    shot = read_shot(lines, width, height)
    assert shot.payouts == FINAL_PAYOUTS and shot.places_paid == 330


def test_info_frame_without_share_line_is_other():
    lines, width, height = _fixture("pass1-info-level13")
    shot = read_shot(_without(lines, "$5.06+$0.44"), width, height)
    assert shot.kind == "other" and shot.info is None


@pytest.mark.parametrize(
    ("missing", "field"),
    [
        ("50,000 (20 BB)", "стартовый стек"),
        ("OKT 30, 23:05", "время начала"),
        ("OKT 31, 01:30 (YpoBeHb 17)", "конец поздней регистрации"),
        ("WHTepBan 6naMHAOB 8MNH", "интервал блайндов"),
        ("8MrpoKOBHa CTOn", "размер стола"),
    ],
)
def test_missing_info_field_refuses(missing, field):
    lines, width, height = _fixture("pass1-info-level13")
    with pytest.raises(ValueError, match=f"^на кадре не найдено: {field}$"):
        read_shot(_without(lines, missing), width, height)


def test_places_count_without_table_refuses():
    lines, width, height = _fixture("pass2-prizes-level17")
    lines = [line for line in lines if not line.text.startswith("$") or line.y < 200]
    with pytest.raises(ValueError, match="^на кадре не найдено: таблица выплат$"):
        read_shot(lines, width, height)


_RUSSIAN_MONTHS = [
    ("янв", 1), ("фев", 2), ("мар", 3), ("апр", 4), ("мая", 5), ("май", 5), ("июн", 6),
    ("июл", 7), ("авг", 8), ("сен", 9), ("окт", 10), ("ноя", 11), ("дек", 12),
]  # fmt: skip


@pytest.mark.parametrize(
    ("month", "number"),
    _RUSSIAN_MONTHS + [("OKT", 10), ("ceH", 9)],  # двойники — как на кадрах 10-30 и 09-10
)
def test_start_month_is_read(month, number):
    lines, width, height = _fixture("pass1-info-level13")
    lines = _replace(lines, "OKT 30, 23:05", text=f"{month} 30, 23:05")
    assert read_shot(lines, width, height).info.start == (number, 30, 23, 5)


def test_unknown_month_refuses():
    lines, width, height = _fixture("pass1-info-level13")
    lines = _replace(lines, "OKT 30, 23:05", text="XYZ 30, 23:05")
    with pytest.raises(ValueError, match="^на кадре не найдено: время начала$"):
        read_shot(lines, width, height)


def test_no_early_bird_row():
    lines, width, height = _fixture("pass1-info-level13")
    assert read_shot(_without(lines, "Early Bird"), width, height).info.early_bird is False


def test_low_confidence_prize_pool():
    lines, width, height = _fixture("pass2-prizes-level17")
    shot = read_shot(_replace(lines, "$11,896.06", score=0.5), width, height)
    assert "призовой фонд" in shot.low_confidence
    assert shot.header.prize_pool_usd == 11896.06  # число не трогается, только пометка


def test_low_confidence_names_payout_row_and_places():
    lines, width, height = _fixture("pass2-prizes-level17")
    lines = _replace(lines, "$59.43", score=0.79)
    lines = _replace(lines, "330 npM30BbIX MeCT", score=0.5)
    assert read_shot(lines, width, height).low_confidence == [
        "число призовых мест",
        "выплата мест 16–19",
    ]


def test_low_confidence_info_fields_but_not_reference_ones():
    lines, width, height = _fixture("pass1-info-level13")
    lines = _replace(lines, "8MrpoKOBHa CTOn", score=0.5)
    lines = _replace(lines, "OKT 30, 23:05", score=0.5)
    # интервал блайндов (0.774 на кадре) и Early Bird — справочные, не помечаются
    lines = _replace(lines, "Early Bird", score=0.5)
    assert read_shot(lines, width, height).low_confidence == ["время начала", "размер стола"]


def test_low_confidence_threshold_is_inclusive_at_0_8():
    lines, width, height = _fixture("pass2-prizes-level17")
    assert read_shot(_replace(lines, "$11,896.06", score=0.8), width, height).low_confidence == []


def test_no_pixel_anchors_scaled_frame():
    # интерфейс масштабируется по ширине окна: те же строки в полтора раза крупнее читаются так же
    lines, width, height = _fixture("pass2-prizes-level17")
    scale = 1.5
    big = [
        dataclasses.replace(line, x=line.x * scale, y=line.y * scale, w=line.w * scale,
                            h=line.h * scale)
        for line in lines
    ]  # fmt: skip
    assert read_shot(big, round(width * scale), round(height * scale)) == read_shot(
        lines, width, height
    )


# --- локальный тест: скриншот → ocr_image → read_shot ---

_LOCAL = {
    "pass1-info-level13": "info",
    "pass1-prizes-level14": "prizes",
    "pass1-structure-level16": "other",
    "pass2-info-level17": "info",
    "pass2-prizes-level17": "prizes",
}


@pytest.fixture(scope="module")
def local_shots():
    pytest.importorskip("rapidocr_onnxruntime")
    missing = [name for name in _LOCAL if not (LOBBY_SHOTS / f"{name}.png").is_file()]
    if missing:
        pytest.skip(f"нет скриншотов {missing} в {LOBBY_SHOTS}")
    from poker_engine.lobby_ocr import ocr_image

    return {name: read_shot(*ocr_image(str(LOBBY_SHOTS / f"{name}.png"))) for name in _LOCAL}


def test_local_screenshots_read(local_shots):
    assert {name: shot.kind for name, shot in local_shots.items()} == _LOCAL
    assert all(shot.title == "Fifty Stack $5.50" for shot in local_shots.values())
    assert all(shot.low_confidence == [] for shot in local_shots.values())

    final = local_shots["pass2-prizes-level17"]
    assert final.places_paid == 330 and final.payouts == FINAL_PAYOUTS
    assert final.header == Header(
        level=17, players_left=802, entrants=2351, unique=1808, reentries=543,
        prize_pool_usd=11896.06, buy_in_usd=5.50, average_stack_chips=146571,
    )  # fmt: skip

    provisional = local_shots["pass1-prizes-level14"]
    assert provisional.places_paid == 270 and len(provisional.payouts) == 19
    assert provisional.payouts[0] == (1, 1, 1154.30)
    assert provisional.payouts[-1] == (170, 270, 11.15)
    assert (provisional.header.unique, provisional.header.reentries) == (1474, 349)
    assert provisional.header.prize_pool_usd == 9224.38
    assert provisional.header.average_stack_chips == 95951

    info = local_shots["pass1-info-level13"]
    assert info.header.level == 13
    assert info.info == Info(
        prize_share_usd=5.06, fee_usd=0.44, starting_stack_chips=50000, start=(10, 30, 23, 5),
        late_reg_close_level=17, blind_interval_min=8, seats_per_table=8, early_bird=True,
    )  # fmt: skip
    assert local_shots["pass2-info-level17"].info == info.info
    assert local_shots["pass2-info-level17"].header.average_stack_chips == 146206
