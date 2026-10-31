"""Заход лобби → проверки → файл турнира (план D40, Задача 4; спека лобби §4–§7).

Кадры — записанные выходы OCR (фикстуры Задачи 2) через `read_shot`, без RapidOCR; отказные
случаи — те же кадры, где одно поле заменено руками (`dataclasses.replace`). Числа ожиданий сняты
со скриншотов: «Fifty Stack $5.50» 2026-10-30, заход 1 на уровнях 13–14, заход 2 на 17-м. Файлы
пишутся только в `tmp_path`; отказ оставляет папку байт в байт прежней.
"""

import dataclasses
import json
import os
import pathlib
import re
from datetime import date

import pytest

from poker_engine import lobby
from poker_engine.lobby_read import Line, read_shot

FIXTURES = pathlib.Path(__file__).parent / "data" / "lobby"
TITLE = "Fifty Stack $5.50"
FILE_NAME = "Fifty Stack $5.50 2026-10-30.json"
PASS1 = date(2026, 10, 30)
PASS2 = date(2026, 10, 31)
SKIPPED = "кадр pass1-structure-level16.png пропущен: это не «Инфо» и не «Призовой фонд»"
PROVISIONAL = "выплаты предварительные: сумма $9,234.50 против фонда $9,224.38"


def _shot(name, file=None):
    """Кадр фикстуры как его отдаёт `read_shot` и имя файла кадра для текстов отказов."""
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    shot = read_shot([Line(**line) for line in data["lines"]], data["width"], data["height"])
    return (file or f"{name}.png"), shot


def _info1():
    return _shot("pass1-info-level13")


def _prizes1():
    return _shot("pass1-prizes-level14")


def _info2():
    return _shot("pass2-info-level17")


def _prizes2():
    return _shot("pass2-prizes-level17")


def _with(pair, file=None, **changes):
    """Тот же кадр с заменёнными полями (`Shot`); `file` — новое имя кадра."""
    name, shot = pair
    return (file or name), dataclasses.replace(shot, **changes)


def _header(pair, file=None, **changes):
    return _with(pair, file, header=dataclasses.replace(pair[1].header, **changes))


def _info(pair, **changes):
    return _with(pair, info=dataclasses.replace(pair[1].info, **changes))


def _rows(pair, keep, file=None, **changes):
    """Тот же кадр «Призового фонда» с другими строками выплат."""
    return _with(pair, file, payouts=keep, **changes)


def _snapshot(directory):
    """Имена и байты всех файлов папки: отказ не меняет ни одного."""
    return {name: (directory / name).read_bytes() for name in sorted(os.listdir(directory))}


def _read(out):
    return json.loads(pathlib.Path(out["tournament"]).read_text(encoding="utf-8"))


def _final_record(tmp_path):
    """Файл турнира после захода 2 с «Инфо»: окончательные выплаты."""
    out = lobby.save([_info2(), _prizes2()], str(tmp_path), PASS2)
    return out, _read(out)


def _total(record):
    return sum((p["to"] - p["from"] + 1) * p["amount"] for p in record["payouts"])


# --- два захода ------------------------------------------------------------------------------


def test_two_passes_end_to_end(tmp_path):
    tmp = str(tmp_path)
    first = lobby.save([_shot("pass1-info-level13"), _shot("pass1-prizes-level14")], tmp, PASS1)
    record = json.load(open(first["tournament"], encoding="utf-8"))
    assert first["tournament"].endswith("Fifty Stack $5.50 2026-10-30.json")
    assert record["payoutsFinal"] is False and record["placesPaid"] == 270
    assert first["payoutsFinal"] is False
    assert any(
        w.startswith("выплаты предварительные: сумма $9,234.50 против фонда $9,224.38")
        for w in first["warnings"]
    )
    second = lobby.save([_shot("pass2-prizes-level17")], tmp, PASS2)
    record = json.load(open(second["tournament"], encoding="utf-8"))
    assert second["tournament"] == first["tournament"] and second["warnings"] == []
    assert second["payoutsFinal"] is True
    assert record["payoutsFinal"] is True and record["lateRegOpen"] is False
    assert record["placesPaid"] == 330 and record["entrants"] == 2351
    assert record["startingStackChips"] == 50000 and record["seatsPerTable"] == 8
    assert _total(record) == pytest.approx(11896.06)
    assert os.listdir(tmp) == [FILE_NAME]


def test_old_partial_list_names_missing_places(tmp_path):
    # 2026-09-10: «Призовой фонд» до места 15 из 165 — дыра не достраивается, файла нет
    tmp = str(tmp_path)
    with pytest.raises(ValueError, match="нет мест 16–165: снимите кадр"):
        lobby.save(
            [_shot("win_2026-09-10_00-29-09"), _shot("win_2026-09-10_00-31-04")],
            tmp,
            date(2026, 9, 10),
        )
    assert os.listdir(tmp) == []


def test_first_pass_record(tmp_path):
    record = _read(lobby.save([_info1(), _prizes1()], str(tmp_path), PASS1))
    payouts = record.pop("payouts")
    assert record == {
        "format": "poker-coach-tournament",
        "version": 1,
        "title": TITLE,
        "start": "2026-10-30T23:05",
        "prizeShareUsd": 5.06,
        "feeUsd": 0.44,
        "buyInUsd": 5.5,
        "pko": False,
        "blindIntervalMin": 8,
        "lateRegCloseLevel": 17,
        "earlyBird": True,
        "seatsPerTable": 8,
        "startingStackChips": 50000,
        "placesPaid": 270,
        "payoutsFinal": False,
        "entrants": 1823,
        "playersLeft": 951,
        "lateRegOpen": True,
        "prizePoolUsd": 9224.38,
    }
    # строки как прочитаны: первая с места 1, последняя — до 270
    assert payouts[0] == {"from": 1, "to": 1, "amount": 1154.30}
    assert payouts[-1] == {"from": 170, "to": 270, "amount": 11.15}
    assert len(payouts) == 19
    assert "bubbleRefundUsd" not in record and "averageStackChips" not in record


def test_pko_is_bounty_in_title():
    title = "Bounty Hunters $5.50"
    shots = [_with(_info2(), title=title), _with(_prizes2(), title=title)]
    record, _ = lobby.merge(shots, None, PASS2)
    assert record["pko"] is True and record["title"] == title


def test_start_year_steps_back_over_new_year():
    # «дек 30» на кадре, снятом 2027-01-02, — турнир 2026 года
    shots = [_info(_info2(), start=(12, 30, 23, 5)), _prizes2()]
    record, _ = lobby.merge(shots, None, date(2027, 1, 2))
    assert record["start"] == "2026-12-30T23:05"


def test_impossible_start_date():
    shots = [_info(_info2(), start=(2, 30, 23, 5)), _prizes2()]
    with pytest.raises(
        ValueError, match="^на кадре pass2-info-level17.png невозможная дата начала: 30.02$"
    ):
        lobby.merge(shots, None, PASS2)


def test_scrolled_prizes_are_joined():
    # окончательный список на двух кадрах: второй — продолжение без строки «N призовых мест»,
    # строка 11–12 видна на обоих
    prizes = _prizes2()
    payouts = prizes[1].payouts
    top = _rows(prizes, payouts[:11])
    bottom = _rows(prizes, payouts[10:], file="scroll.png", places_paid=None)
    record, warnings = lobby.merge([_info2(), top, bottom], None, PASS2)
    assert [(p["from"], p["to"], p["amount"]) for p in record["payouts"]] == payouts
    assert record["placesPaid"] == 330 and warnings == []


def test_record_header_is_the_latest_prizes_shot():
    # прокрутка шла, пока выбывали игроки: в запись — кадр с меньшим остатком
    later = _header(_prizes2(), "later.png", players_left=800, average_stack_chips=146938)
    record, _ = lobby.merge([_info2(), _prizes2(), later], None, PASS2)
    assert record["playersLeft"] == 800


# --- таблица проверок, по строке на тест -----------------------------------------------------


def test_1_no_prizes_shot():
    with pytest.raises(ValueError, match="^нет кадра «Призового фонда»$"):
        lobby.merge([_info1()], None, PASS1)


def test_2_no_info_and_no_file():
    with pytest.raises(
        ValueError,
        match="^нет кадра «Инфо»: без него не узнать стартовый стек и размер стола$",
    ):
        lobby.merge([_prizes1()], None, PASS1)


def test_3_low_confidence():
    shots = [_info1(), _with(_prizes1(), low_confidence=["призовой фонд"])]
    with pytest.raises(
        ValueError,
        match="^поле «призовой фонд» прочитано неуверенно на кадре pass1-prizes-level14.png: "
        "снимите его заново$",
    ):
        lobby.merge(shots, None, PASS1)


def test_4_overlapping_row_reads_differently():
    prizes = _prizes2()
    other = list(prizes[1].payouts)
    other[10] = (11, 12, 94.24)
    shots = [_info2(), prizes, _rows(prizes, other, file="scroll.png")]
    with pytest.raises(
        ValueError, match=re.escape("строка мест 11–12 читается по-разному: $94.42 и $94.24")
    ):
        lobby.merge(shots, None, PASS2)


def test_overlapping_ranges_on_two_shots():
    # R15: строка «11–12» на одном кадре и «11–13» на другом — одна строка, прочитанная
    # по-разному; отказ с обоими прочтениями и кадрами до проверки стыка
    prizes = _prizes2()
    other = list(prizes[1].payouts)
    other[10] = (11, 13, 94.42)
    shots = [_info2(), prizes, _rows(prizes, other[10:], file="scroll.png", places_paid=None)]
    with pytest.raises(
        ValueError,
        match="^строка мест читается по-разному: 11–12 на кадре pass2-prizes-level17.png "
        "и 11–13 на кадре scroll.png$",
    ):
        lobby.merge(shots, None, PASS2)


def test_overlap_further_down_names_both_rows():
    # «13–15» с одного кадра и «14–19» с другого: пересечение не на первом месте строки
    prizes = _prizes2()
    other = list(prizes[1].payouts)
    other[12] = (14, 19, 59.43)
    shots = [_info2(), prizes, _rows(prizes, other[12:], file="scroll.png", places_paid=None)]
    with pytest.raises(
        ValueError,
        match="^строка мест читается по-разному: 13–15 на кадре pass2-prizes-level17.png "
        "и 14–19 на кадре scroll.png$",
    ):
        lobby.merge(shots, None, PASS2)


@pytest.mark.parametrize(
    "drop, hole",
    [(0, "1–1"), (11, "13–15"), (19, "208–330")],
    ids=["first-row", "inner-row", "last-row"],
)
def test_5_6_missing_row_is_named(drop, hole):
    # строка, которую OCR не прочитал, просто отсутствует; проверка стыка называет её места
    prizes = _prizes2()
    rows = [row for i, row in enumerate(prizes[1].payouts) if i != drop]
    with pytest.raises(
        ValueError,
        match=f"^нет мест {hole}: снимите кадр «Призового фонда», где они видны$",
    ):
        lobby.merge([_info2(), _rows(prizes, rows)], None, PASS2)


def test_6_list_ends_before_places_paid():
    prizes = _prizes2()
    with pytest.raises(ValueError, match="^нет мест 11–330: снимите кадр"):
        lobby.merge([_info2(), _rows(prizes, prizes[1].payouts[:10])], None, PASS2)


def test_7_header_unique_and_reentries():
    with pytest.raises(
        ValueError,
        match=re.escape(
            "в шапке pass2-prizes-level17.png уникальных и ре-энтри 1807 + 543, а входов 2351"
        ),
    ):
        lobby.merge([_info2(), _header(_prizes2(), unique=1807)], None, PASS2)


def test_7_runs_on_every_shot_before_8():
    # кадр «Инфо» ломает 8, кадр выплат — 7: сначала 7 на всех кадрах, потом 8 на всех
    shots = [_header(_info2(), average_stack_chips=140000), _header(_prizes2(), unique=1807)]
    with pytest.raises(ValueError, match="^в шапке pass2-prizes-level17.png уникальных и ре-энтри"):
        lobby.merge(shots, None, PASS2)


def test_7_checks_the_info_header_too():
    shots = [_header(_info2(), reentries=544), _prizes2()]
    with pytest.raises(ValueError, match="^в шапке pass2-info-level17.png уникальных и ре-энтри"):
        lobby.merge(shots, None, PASS2)


def test_8_header_average_stack():
    # 50,000 × 2,351 / 802 = 146,571.07; 140,000 дальше 0.5%
    shots = [_info2(), _header(_prizes2(), average_stack_chips=140000)]
    with pytest.raises(
        ValueError,
        match="^средний стек шапки 140,000 не сходится с расчётом 146,571 на кадре "
        "pass2-prizes-level17.png$",
    ):
        lobby.merge(shots, None, PASS2)


def test_8_average_within_half_percent_passes():
    # 146,571.07 × 1.0049 = 147,289.3: ближе 0.5% — не отказ
    lobby.merge([_info2(), _header(_prizes2(), average_stack_chips=147289)], None, PASS2)


def test_8_uses_starting_stack_from_the_file(tmp_path):
    _, record = _final_record(tmp_path)
    shot = _header(_prizes2(), average_stack_chips=140000)
    with pytest.raises(ValueError, match="^средний стек шапки 140,000 не сходится"):
        lobby.merge([shot], record, PASS2)


def test_8_no_players_left():
    with pytest.raises(ValueError, match="^остаток игроков должен быть > 0, получено 0$"):
        lobby.merge([_info2(), _header(_prizes2(), players_left=0)], None, PASS2)


def test_9_final_sum_differs_from_pool():
    # 208–330: $11.57 вместо $11.75 — Σ меньше на 0.18 × 123 = $22.14
    prizes = _prizes2()
    rows = prizes[1].payouts[:-1] + [(208, 330, 11.57)]
    with pytest.raises(
        ValueError,
        match=re.escape(
            "сумма выплат $11,873.92 не равна призовому фонду $11,896.06: перечитайте строки "
            "или снимите кадр заново"
        ),
    ):
        lobby.merge([_info2(), _rows(prizes, rows)], None, PASS2)


def test_9_rounding_within_half_cent_per_place_passes():
    # место 1 на цент больше: |Σ − фонд| = 0.01 < 0.005 × 330 + 0.005
    prizes = _prizes2()
    rows = [(1, 1, 1450.18)] + prizes[1].payouts[1:]
    record, warnings = lobby.merge([_info2(), _rows(prizes, rows)], None, PASS2)
    assert record["payoutsFinal"] is True and warnings == []


def test_10_provisional_sum_is_a_warning():
    record, warnings = lobby.merge([_info1(), _prizes1()], None, PASS1)
    assert warnings == [PROVISIONAL]
    assert record["payoutsFinal"] is False


def test_11_other_starting_stack(tmp_path):
    # в файле — турнир того же названия со стартом 30,000; шапка кадров сходится с 50,000
    _, record = _final_record(tmp_path)
    record = {**record, "startingStackChips": 30000}
    with pytest.raises(
        ValueError, match="^кадры от другого турнира: стартовый стек 30,000 против 50,000$"
    ):
        lobby.merge([_info2(), _prizes2()], record, PASS2)


def test_11_fewer_entrants(tmp_path):
    # заход 1 после захода 2: входов 1,823 против 2,351 в файле
    _final_record(tmp_path)
    before = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="^кадры от другого турнира: входы 2351 против 1823$"):
        lobby.save([_info1(), _prizes1()], str(tmp_path), PASS1)
    assert _snapshot(tmp_path) == before


def test_11_other_title(tmp_path):
    _, record = _final_record(tmp_path)
    with pytest.raises(
        ValueError,
        match=re.escape(
            "кадры от другого турнира: название «Fifty Stack $5.50» против «Fifty Stack $11»"
        ),
    ):
        lobby.merge([_with(_prizes2(), title="Fifty Stack $11")], record, PASS2)


def test_12_provisional_over_final(tmp_path):
    # предварительный кадр с теми же входами (уровень 16 < 17): входов не меньше, но выплаты
    # во время поздней регистрации окончательные не заменяют
    _, record = _final_record(tmp_path)
    with pytest.raises(
        ValueError,
        match="^в файле турнира уже окончательные выплаты, а кадры сняты во время поздней "
        "регистрации$",
    ):
        lobby.merge([_header(_prizes2(), level=16)], record, PASS2)


# проверка 13 — `test_second_pass_ambiguous_without_info` ниже (Review Focus 3)


def test_14_other_shot_is_a_warning():
    shots = [_info2(), _prizes2(), _shot("pass1-structure-level16")]
    record, warnings = lobby.merge(shots, None, PASS2)
    assert warnings == [SKIPPED]


def test_15_record_passes_the_context_validator():
    # 2-е и 3-е места переставлены: Σ та же, предупреждение то же, но приз за 3-е больше,
    # чем за 2-е, — отказ `_validate_context`, как у `coach start`
    prizes = _prizes1()
    rows = list(prizes[1].payouts)
    rows[1], rows[2] = (2, 2, rows[2][2]), (3, 3, rows[1][2])
    with pytest.raises(ValueError, match="^выплата за более низкое место больше, чем за высокое$"):
        lobby.merge([_info1(), _rows(prizes, rows)], None, PASS1)


# --- Review Focus 2–4 ------------------------------------------------------------------------


def test_structure_shot_is_skipped_with_warning(tmp_path):
    # «Структура» в заходе: предупреждение, не отказ; её шапка (уровень 16, 2,116 входов) в
    # запись не идёт
    plain, _ = lobby.merge([_info1(), _prizes1()], None, PASS1)
    out = lobby.save([_shot("pass1-structure-level16"), _info1(), _prizes1()], str(tmp_path), PASS1)
    assert out["warnings"] == [PROVISIONAL, SKIPPED]  # 10 раньше 14, по порядку таблицы
    record = _read(out)
    assert record == plain and record["entrants"] == 1823


def test_second_pass_ambiguous_without_info(tmp_path):
    # проверка 13: тот же турнир днём раньше — два файла с одним названием, кадра «Инфо» нет;
    # какой из них, не угадывается
    tmp = str(tmp_path)
    first = lobby.save([_info1(), _prizes1()], tmp, PASS1)
    earlier = lobby.save([_info(_info1(), start=(10, 29, 23, 5)), _prizes1()], tmp, PASS1)
    before = _snapshot(tmp_path)
    paths = f"{earlier['tournament']}, {first['tournament']}"
    text = f"турниров «{TITLE}» несколько: {paths} — добавьте кадр «Инфо»"
    with pytest.raises(ValueError, match=f"^{re.escape(text)}$"):
        lobby.save([_prizes2()], tmp, PASS2)
    assert _snapshot(tmp_path) == before


def test_provisional_never_overwrites_final(tmp_path):
    out, _ = _final_record(tmp_path)
    before = _snapshot(tmp_path)
    # повторный заход 1 (те же кадры уровней 13–14): входов меньше
    with pytest.raises(ValueError, match="^кадры от другого турнира: входы"):
        lobby.save([_info1(), _prizes1()], str(tmp_path), PASS1)
    # предварительный кадр с теми же входами
    with pytest.raises(ValueError, match="^в файле турнира уже окончательные выплаты"):
        lobby.save([_header(_prizes2(), level=16)], str(tmp_path), PASS2)
    assert _snapshot(tmp_path) == before
    assert _read(out)["payoutsFinal"] is True


def test_save_checks_confidence_before_the_lookup(tmp_path):
    # R14: без «Инфо» и без файла, поле неуверенно — отказ 3, а не 2: файл ищется по названию,
    # и до поиска кадры должны быть прочитаны уверенно
    with pytest.raises(
        ValueError,
        match="^поле «название» прочитано неуверенно на кадре pass2-prizes-level17.png: "
        "снимите его заново$",
    ):
        lobby.save([_with(_prizes2(), low_confidence=["название"])], str(tmp_path), PASS2)
    assert os.listdir(tmp_path) == []


def test_info_read_as_other_without_file_is_check_2():
    # R12: кадр «Инфо», прочитанный как "other", пропускается — и без файла это отказ 2
    with pytest.raises(ValueError, match="^нет кадра «Инфо»: без него не узнать"):
        lobby.merge([_prizes1(), _shot("pass1-structure-level16")], None, PASS1)


def test_info_read_as_other_with_file_is_skipped(tmp_path):
    # тот же пропуск при файле турнира: поля «Инфо» из файла, кадр — в предупреждениях
    tmp = str(tmp_path)
    first = lobby.save([_info1(), _prizes1()], tmp, PASS1)
    out = lobby.save([_prizes1(), _shot("pass1-structure-level16")], tmp, PASS1)
    assert out["tournament"] == first["tournament"]
    assert out["warnings"] == [PROVISIONAL, SKIPPED]
    assert _read(out)["startingStackChips"] == 50000 and os.listdir(tmp) == [FILE_NAME]


def test_provisional_may_replace_provisional(tmp_path):
    # заход 1 дважды: выплаты заменяются, файл тот же
    tmp = str(tmp_path)
    lobby.save([_info1(), _prizes1()], tmp, PASS1)
    out = lobby.save([_header(_prizes1(), level=16)], tmp, PASS1)
    assert _read(out)["payoutsFinal"] is False and os.listdir(tmp) == [FILE_NAME]


# --- R12, R13: что `read_shot` оставил проверкам ---------------------------------------------


def test_no_places_paid_on_any_prizes_shot():
    with pytest.raises(
        ValueError,
        match="^не найдено число призовых мест: снимите кадр «Призового фонда» со строкой "
        "«N призовых мест»$",
    ):
        lobby.merge([_info2(), _with(_prizes2(), places_paid=None)], None, PASS2)


def test_places_paid_disagrees_between_shots():
    shots = [_info2(), _prizes2(), _with(_prizes2(), file="scroll.png", places_paid=331)]
    with pytest.raises(
        ValueError,
        match="^число призовых мест читается по-разному: 330 на кадре pass2-prizes-level17.png "
        "и 331 на кадре scroll.png$",
    ):
        lobby.merge(shots, None, PASS2)


def test_prizes_shots_from_two_passes():
    with pytest.raises(
        ValueError,
        match="^кадры «Призового фонда» сняты в разных заходах: pass1-prizes-level14.png, "
        "pass2-prizes-level17.png$",
    ):
        lobby.merge([_info1(), _prizes1(), _prizes2()], None, PASS1)


def test_shots_of_two_tournaments_in_one_call():
    shots = [_info2(), _with(_prizes2(), title="Fifty Stack $11")]
    with pytest.raises(
        ValueError,
        match=re.escape(
            "кадры от другого турнира: название «Fifty Stack $5.50» против «Fifty Stack $11»"
        ),
    ):
        lobby.merge(shots, None, PASS2)


def test_two_info_shots_read_differently():
    shots = [_info1(), _info(_info2(), seats_per_table=9), _prizes2()]
    with pytest.raises(
        ValueError,
        match="^кадры «Инфо» читаются по-разному: pass1-info-level13.png и pass2-info-level17.png$",
    ):
        lobby.merge(shots, None, PASS2)


# --- файл турнира -----------------------------------------------------------------------------


def test_tournament_path_replaces_windows_reserved_characters(tmp_path):
    path = lobby.tournament_path(str(tmp_path), 'A<B>C:D"E/F\\G|H?I*J', date(2026, 10, 30))
    assert path == os.path.join(str(tmp_path), "A_B_C_D_E_F_G_H_I_J 2026-10-30.json")


def test_find_lists_files_of_the_title(tmp_path):
    tmp = str(tmp_path)
    first = lobby.save([_info1(), _prizes1()], tmp, PASS1)
    (tmp_path / "notes.json").write_text("[1, 2]", encoding="utf-8")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert lobby.find(tmp, TITLE) == [
        {"path": first["tournament"], "start": "2026-10-30T23:05", "payoutsFinal": False}
    ]
    assert lobby.find(tmp, "Bounty Hunters $5.50") == []
    assert lobby.find(str(tmp_path / "missing"), TITLE) == []


def test_damaged_tournament_file_is_not_overwritten(tmp_path):
    path = lobby.tournament_path(str(tmp_path), TITLE, date(2026, 10, 30))
    pathlib.Path(path).write_text("{", encoding="utf-8")
    before = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="^файл турнира повреждён: "):
        lobby.save([_info1(), _prizes1()], str(tmp_path), PASS1)
    assert _snapshot(tmp_path) == before


def test_save_creates_the_directory(tmp_path):
    directory = tmp_path / "tournaments"
    out = lobby.save([_info1(), _prizes1()], str(directory), PASS1)
    assert os.listdir(directory) == [FILE_NAME]
    assert out["tournament"] == os.path.join(str(directory), FILE_NAME)


def test_tournament_file_without_a_field_is_damaged(tmp_path):
    _, record = _final_record(tmp_path)
    del record["entrants"]
    with pytest.raises(ValueError, match="^файл турнира повреждён: нет поля entrants$"):
        lobby.merge([_prizes2()], record, PASS2)
