"""Файл турнира из кадров лобби (план D40, Задача 4; спека лобби §4–§7).

Один вызов — один заход (спека §5): кадры «Инфо» и «Призового фонда», уже прочитанные
`lobby_read.read_shot`. Проверки спеки §7 идут по порядку таблицы плана; первая не прошедшая —
`ValueError` с именем строки, поля и кадра, и файл турнира не трогается (спека §4): пропущенная
строка выплат не достраивается, число под сумму не двигается.

Запись турнира — контекст `coach start` плюс справка (название, дата начала, бай-ин, PKO,
интервал блайндов, призовой фонд). Файл лежит в папке турниров под именем «<название>
<YYYY-MM-DD>.json» по дате начала из «Инфо»: заход 1 его создаёт, заход 2 заменяет в нём выплаты
и входы. Кадра «Инфо» во втором заходе может не быть — тогда файл ищется по названию.

`read` (Задача 5) — заход из файлов кадров: распознавание `lobby_ocr`, разбор, `save`.

Модуль импортируется без группы `[lobby]`: `lobby_ocr` подключает RapidOCR и Pillow только при
вызове, и без них отказывает `read`, а не импорт.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date

from . import lobby_ocr
from ._checks import check_positive
from ._files import write_json
from .frames import context_payload
from .handstate import _validate_context, context_from_dict
from .lobby_read import Info, Shot, read_shot

FORMAT = "poker-coach-tournament"
VERSION = 1
_AVERAGE_TOLERANCE = 0.005  # средний стек шапки против расчёта: 0.5% (спека §7.5, замер 0.11%)
_CENT = 0.005  # округление выплат: полцента на место и полцента на фонд (спека §7.4)
_RESERVED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')  # запрещены в именах файлов Windows
# поля «Инфо» в записи: без кадра «Инфо» они берутся из файла турнира
_INFO_KEYS = (
    "start", "prizeShareUsd", "feeUsd", "blindIntervalMin", "lateRegCloseLevel", "earlyBird",
    "seatsPerTable", "startingStackChips",
)  # fmt: skip


def merge(
    shots: list[tuple[str, Shot]], existing: dict | None, captured: date
) -> tuple[dict, list[str]]:
    """Запись турнира из кадров захода и прежнего файла (`existing`, `None` — файла нет) и
    предупреждения. `captured` — дата съёмки: год начала турнира на кадре не виден.

    Строка кортежа — имя файла кадра для текстов отказов. Выплаты, входы и шапка — из кадров
    «Призового фонда»; поля «Инфо» — из кадра «Инфо», а без него из файла.
    """
    prizes, infos, used, skipped = _sorted(shots)  # проверки 1, 14
    if not infos and existing is None:  # 2
        raise _no_info()
    _legible(used)  # 3
    title = _one_title(used)
    facts = _info_facts(infos, captured) if infos else _file_facts(existing)

    final = _one_pass(prizes, facts["lateRegCloseLevel"])
    places_paid = _places_paid(prizes)
    payouts = _joined(prizes)  # 4, R15
    _seams(payouts, places_paid)  # 5, 6
    for name, shot in used:  # 7 на всех кадрах, затем 8 на всех
        _header_sums(name, shot)
    for name, shot in used:
        _header_average(name, shot, facts["startingStackChips"])

    header = max((shot.header for _, shot in prizes), key=lambda h: (h.entrants, -h.players_left))
    total = sum((last - first + 1) * amount for first, last, amount in payouts)
    warnings = []
    if abs(total - header.prize_pool_usd) > _CENT * places_paid + _CENT:
        if final:  # 9
            raise ValueError(
                f"сумма выплат {_usd(total)} не равна призовому фонду "
                f"{_usd(header.prize_pool_usd)}: перечитайте строки или снимите кадр заново"
            )
        warnings.append(  # 10
            f"выплаты предварительные: сумма {_usd(total)} против фонда "
            f"{_usd(header.prize_pool_usd)}"
        )
    warnings += skipped  # 14 — после 10, по порядку таблицы

    if existing is not None:
        _same_tournament(existing, title, facts["startingStackChips"], header.entrants)  # 11
        if _file_field(existing, "payoutsFinal") is True and not final:  # 12
            raise ValueError(
                "в файле турнира уже окончательные выплаты, а кадры сняты во время поздней "
                "регистрации"
            )

    record = {
        "format": FORMAT,
        "version": VERSION,
        "title": title,
        "start": facts["start"],
        "prizeShareUsd": facts["prizeShareUsd"],
        "feeUsd": facts["feeUsd"],
        "buyInUsd": header.buy_in_usd,
        "pko": "Bounty" in title,
        "blindIntervalMin": facts["blindIntervalMin"],
        "lateRegCloseLevel": facts["lateRegCloseLevel"],
        "earlyBird": facts["earlyBird"],
        "seatsPerTable": facts["seatsPerTable"],
        "startingStackChips": facts["startingStackChips"],
        "payouts": [
            {"from": first, "to": last, "amount": amount} for first, last, amount in payouts
        ],
        "placesPaid": places_paid,
        "payoutsFinal": final,
        "entrants": header.entrants,
        "playersLeft": header.players_left,
        "lateRegOpen": not final,
        "prizePoolUsd": header.prize_pool_usd,
    }
    # 15: та же проверка, что у `coach start`
    _validate_context(context_from_dict(context_payload(record, None)))
    return record, warnings


def tournament_path(directory: str, title: str, start: date) -> str:
    """`<directory>/<title> <YYYY-MM-DD>.json`; знаки, запрещённые в именах Windows, — `_`."""
    return os.path.join(directory, f"{_RESERVED.sub('_', title)} {start:%Y-%m-%d}.json")


def find(directory: str, title: str) -> list[dict]:
    """Файлы турниров с этим названием в папке по дате начала: `[{"path", "start",
    "payoutsFinal"}]`. JSON не файла турнира и нечитаемый JSON пропускаются; нет папки — `[]`,
    не папка или папка не читается — `ValueError`."""
    if not os.path.exists(directory):
        return []
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        raise ValueError(f"не удалось прочитать папку {directory!r}: {exc}") from exc
    found = []
    for name in names:
        path = os.path.join(directory, name)
        if not name.endswith(".json") or not os.path.isfile(path):
            continue
        try:
            record = _load(path)
        except ValueError:
            continue
        if record.get("title") == title:
            found.append(
                {
                    "path": path,
                    "start": record.get("start"),
                    "payoutsFinal": record.get("payoutsFinal"),
                }
            )
    return sorted(found, key=lambda entry: str(entry["start"]))


def save(shots: list[tuple[str, Shot]], directory: str, captured: date) -> dict:
    """Заход в файл турнира: найти файл, `merge`, записать целиком (временный файл и замена).

    С кадром «Инфо» файл — по названию и дате начала; без него — единственный файл с этим
    названием в папке. Ответ — `{"tournament": путь, "payoutsFinal", "warnings"}`.

    Поиск файла идёт по названию, поэтому до него — проверки 1 и 3 (решение R14): неуверенное
    название выбрало бы чужой файл или ни одного. Отсюда единственное отступление от порядка
    таблицы: без «Инфо», без файла и с неуверенным полем отказ — проверка 3, а не 2. Отказы поиска
    — тоже до `merge`: 13 (файлов несколько) и 2 (без «Инфо» файла нет — путь не из чего взять).
    """
    _, infos, used, _ = _sorted(shots)
    _legible(used)
    title = _one_title(used)
    if infos:
        name, shot = infos[0]
        path = tournament_path(directory, title, _start(name, shot.info, captured)[0])
        existing = _load(path) if os.path.exists(path) else None
    else:
        found = find(directory, title)
        if len(found) > 1:  # 13
            paths = ", ".join(entry["path"] for entry in found)
            raise ValueError(f"турниров «{title}» несколько: {paths} — добавьте кадр «Инфо»")
        if not found:  # 2: файла нет, а без «Инфо» его не создать
            raise _no_info()
        path = found[0]["path"]
        existing = _load(path)
    record, warnings = merge(shots, existing, captured)
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"не удалось записать {path!r}: {exc}") from exc
    write_json(path, record, prefix=".tournament-")
    return {"tournament": path, "payoutsFinal": record["payoutsFinal"], "warnings": warnings}


def read(paths: list[str], directory: str) -> dict:
    """Заход из файлов кадров (`poker-engine lobby read`): дата съёмки, распознавание каждого
    кадра, разбор и `save`. Ответ — как у `save`.

    Файлы проверяются до распознавания (`captured_date`): оно идёт 11–16 с на кадр, и пропавший
    последний кадр не должен ждать первых. Имя кадра в текстах отказов — имя файла без папки.
    """
    if not paths:
        raise ValueError("нет кадров лобби")
    captured = captured_date(paths)
    shots = []
    for path in paths:
        try:
            lines, width, height = lobby_ocr.ocr_image(path)
        except OSError as exc:  # не картинка или файл пропал после проверки
            raise ValueError(f"не удалось прочитать {path!r}: {exc}") from exc
        shots.append((os.path.basename(path), read_shot(lines, width, height)))
    return save(shots, directory, captured)


def captured_date(paths: list[str]) -> date:
    """Дата съёмки — дата изменения самого нового кадра: год начала турнира на кадре не виден
    (`_start`), а кадры захода снимаются подряд."""
    stamps = []
    for path in paths:
        try:
            stamps.append(os.path.getmtime(path))
        except OSError as exc:
            raise ValueError(f"не удалось прочитать {path!r}: {exc}") from exc
    return date.fromtimestamp(max(stamps))


# --- проверки ---------------------------------------------------------------------------------


def _sorted(shots):
    """Кадры «Призового фонда», «Инфо», те и другие в порядке вызова и предупреждения о прочих
    (проверки 1 и 14)."""
    prizes = [(name, shot) for name, shot in shots if shot.kind == "prizes"]
    infos = [(name, shot) for name, shot in shots if shot.kind == "info"]
    if not prizes:
        raise ValueError("нет кадра «Призового фонда»")
    used = [(name, shot) for name, shot in shots if shot.kind in ("prizes", "info")]
    skipped = [
        f"кадр {name} пропущен: это не «Инфо» и не «Призовой фонд»"
        for name, shot in shots
        if shot.kind not in ("prizes", "info")
    ]
    return prizes, infos, used, skipped


def _legible(shots) -> None:
    """Проверка 3: у нужного поля уверенность OCR ниже порога — отказ с полем и кадром."""
    for name, shot in shots:
        if shot.low_confidence:
            raise ValueError(
                f"поле «{shot.low_confidence[0]}» прочитано неуверенно на кадре {name}: "
                "снимите его заново"
            )


def _one_title(shots) -> str:
    """Название турнира; у кадров одного вызова оно одно, иначе кадры от разных турниров."""
    title = shots[0][1].title
    for _, shot in shots:
        if shot.title != title:
            raise _other_tournament("название", f"«{title}»", f"«{shot.title}»")
    return title


def _info_facts(infos, captured: date) -> dict:
    """Поля «Инфо» записи с кадра; кадры «Инфо» одного вызова читаются одинаково."""
    first_name, first = infos[0]
    for name, shot in infos[1:]:
        if shot.info != first.info:
            raise ValueError(f"кадры «Инфо» читаются по-разному: {first_name} и {name}")
    info = first.info
    return {
        "start": _start(first_name, info, captured)[1],
        "prizeShareUsd": info.prize_share_usd,
        "feeUsd": info.fee_usd,
        "blindIntervalMin": info.blind_interval_min,
        "lateRegCloseLevel": info.late_reg_close_level,
        "earlyBird": info.early_bird,
        "seatsPerTable": info.seats_per_table,
        "startingStackChips": info.starting_stack_chips,
    }


def _file_facts(existing: dict) -> dict:
    return {key: _file_field(existing, key) for key in _INFO_KEYS}


def _start(name: str, info: Info, captured: date) -> tuple[date, str]:
    """Дата начала и `YYYY-MM-DDTHH:MM`. Год на кадре не виден: год съёмки, а месяц начала
    позже месяца съёмки — прошлый год (турнир начался до Нового года)."""
    month, day, hour, minute = info.start
    year = captured.year - (month > captured.month)
    try:
        start = date(year, month, day)
    except ValueError:
        raise ValueError(f"на кадре {name} невозможная дата начала: {day:02}.{month:02}") from None
    return start, f"{start:%Y-%m-%d}T{hour:02}:{minute:02}"


def _one_pass(prizes, close_level: int) -> bool:
    """Выплаты окончательные: шапка кадров выплат на уровне закрытия поздней регистрации или
    позже. Кадры одного вызова — из одного захода (R13)."""
    finals = {shot.header.level >= close_level for _, shot in prizes}
    if len(finals) > 1:
        names = ", ".join(name for name, _ in prizes)
        raise ValueError(f"кадры «Призового фонда» сняты в разных заходах: {names}")
    return finals.pop()


def _places_paid(prizes) -> int:
    """«N призовых мест» — с кадров, где строка видна (у продолжения прокрутки её нет), одно на
    всех (R12, R13)."""
    seen = [(name, shot.places_paid) for name, shot in prizes if shot.places_paid is not None]
    if not seen:
        raise ValueError(
            "не найдено число призовых мест: снимите кадр «Призового фонда» со строкой "
            "«N призовых мест»"
        )
    first_name, places_paid = seen[0]
    for name, other in seen[1:]:
        if other != places_paid:
            raise ValueError(
                f"число призовых мест читается по-разному: {places_paid} на кадре {first_name} "
                f"и {other} на кадре {name}"
            )
    return places_paid


def _joined(prizes) -> list[tuple[int, int, float]]:
    """Строки всех кадров по местам; строка, видная на двух кадрах, читается одинаково — иначе
    отказ с обоими прочтениями, а не выбор одного (спека §7.2). Проверка 4 — те же места, другой
    приз; R15 — места строк пересекаются, но не совпадают («11–12» и «11–13»)."""
    rows: dict[tuple[int, int], tuple[float, str]] = {}
    for name, shot in prizes:
        for first, last, amount in shot.payouts:
            seen, _ = rows.setdefault((first, last), (amount, name))
            if seen != amount:  # 4
                raise ValueError(
                    f"строка мест {first}–{last} читается по-разному: {_usd(seen)} и {_usd(amount)}"
                )
    ordered = sorted(rows.items())
    reach = (0, 0, "")  # строка, дальше всех ушедшая вниз по местам: с места, по место, кадр
    for (first, last), (_, name) in ordered:
        if first <= reach[1]:  # R15
            raise ValueError(
                f"строка мест читается по-разному: {reach[0]}–{reach[1]} на кадре {reach[2]} "
                f"и {first}–{last} на кадре {name}"
            )
        reach = (first, last, name)
    return [(first, last, amount) for (first, last), (amount, _) in ordered]


def _seams(payouts, places_paid: int) -> None:
    """Проверки 5 и 6: первая строка с места 1, каждая следующая — с «прошлый конец + 1»,
    последняя кончается на `places_paid`. Строки не пересекаются — это уже проверил `_joined`."""
    expected = 1
    for first, last, _ in payouts:
        if first > expected:  # 5
            raise _hole(expected, first - 1)
        expected = last + 1
    if expected - 1 < places_paid:  # 6
        raise _hole(expected, places_paid)


def _hole(first: int, last: int) -> ValueError:
    if first == last:
        return ValueError(f"нет места {first}: снимите кадр «Призового фонда», где оно видно")
    return ValueError(f"нет мест {first}–{last}: снимите кадр «Призового фонда», где они видны")


def _no_info() -> ValueError:
    return ValueError("нет кадра «Инфо»: без него не узнать стартовый стек и размер стола")


def _header_sums(name: str, shot: Shot) -> None:
    """Проверка 7: уникальные и ре-энтри шапки дают входы."""
    header = shot.header
    if header.unique + header.reentries != header.entrants:  # 7
        raise ValueError(
            f"в шапке {name} уникальных и ре-энтри {header.unique} + {header.reentries}, "
            f"а входов {header.entrants}"
        )


def _header_average(name: str, shot: Shot, starting: int) -> None:
    """Проверка 8: средний стек шапки против стартового стека × входы / осталось."""
    header = shot.header
    check_positive(header.players_left, "остаток игроков")
    calc = starting * header.entrants / header.players_left
    if abs(calc - header.average_stack_chips) > _AVERAGE_TOLERANCE * calc:  # 8
        raise ValueError(
            f"средний стек шапки {header.average_stack_chips:,} не сходится с расчётом "
            f"{calc:,.0f} на кадре {name}"
        )


def _same_tournament(existing: dict, title: str, starting: int, entrants: int) -> None:
    """Проверка 11: заход 2 — тот же турнир, что заход 1 в файле: название, стартовый стек,
    входов не меньше."""
    if _file_field(existing, "title") != title:
        raise _other_tournament("название", f"«{existing['title']}»", f"«{title}»")
    was = _file_field(existing, "startingStackChips")
    if was != starting:
        raise _other_tournament("стартовый стек", f"{was:,}", f"{starting:,}")
    if entrants < _file_field(existing, "entrants"):
        raise _other_tournament("входы", existing["entrants"], entrants)


def _other_tournament(field: str, was, now) -> ValueError:
    return ValueError(f"кадры от другого турнира: {field} {was} против {now}")


# --- файл -------------------------------------------------------------------------------------


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"файл турнира повреждён: {path}") from exc
    if not isinstance(record, dict) or record.get("format") != FORMAT:
        raise ValueError(f"файл турнира повреждён: {path}")
    return record


def _file_field(existing: dict, key: str):
    if key not in existing:
        raise ValueError(f"файл турнира повреждён: нет поля {key}")
    return existing[key]


def _usd(amount: float) -> str:
    """Сумма как в лобби: `$11,896.06`."""
    return f"${amount:,.2f}"
