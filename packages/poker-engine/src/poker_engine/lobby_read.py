"""Разбор лобби GG: строки распознавания одного кадра → поля (план D40, Задачи 2–3; спека лобби
§3, §8).

Строку отдаёт `lobby_ocr`, разбор её читает. Поля ищутся по форме чисел и взаимному расположению,
а не по подписям и не по пикселям: подписи RapidOCR читает латинскими двойниками («ypOBeHb 17»
вместо «Уровень 17»), а размер окна разный (1195×1035 и 1200×740). Подписи-двойники читаются
только там, где форма числа поле не различает («N призовых мест», «N игроков на стол», «N мин»,
месяц даты, строка Early Bird). Число как прочитано: разбор ничего не достраивает и не двигает
(спека §4); чего на кадре нет — отказ с именем поля, а не догадка.

Модуль не тянет распознавание, поэтому импортируется без группы `[lobby]`.
"""

import re
import unicodedata
from dataclasses import dataclass

# доля ширины кадра: граница шапки и тела; та же, по которой `lobby_ocr` режет вырезки
HEADER_BOTTOM = 0.155
_MIN_SCORE = 0.8  # уверенность OCR ниже — поле в `low_confidence`
_ROW = 0.5  # строки в одном ряду: центры ближе половины высоты большей

_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)"  # «2,351» или «2351»; запятые — только по три цифры
_MONEY = rf"\$({_NUM}(?:\.\d{{2}})?)"
_COUNTER = re.compile(rf"({_NUM})/({_NUM})")  # «осталось / входы»
_SPLIT = re.compile(r"(\d+)\|(\d+)")  # «уникальные | ре-энтри»
_BLINDS = re.compile(rf"{_NUM}/{_NUM}\s*\({_NUM}\)")  # «2,500 / 5,000 (600)»
# «146,571 (29.3 BB)»; лишняя скобка в начале («（146,571(29.3 BB)») — шум OCR, не число
_STACK = re.compile(rf"\(?({_NUM})\s*\(\s*\d+(?:\.\d+)?\s*BB\s*\)", re.IGNORECASE)
_MONEY_ONLY = re.compile(_MONEY)
_TITLE = re.compile(rf".*[^\W\d_].*?\s*{_MONEY}")  # «Fifty Stack $5.50»: слова и цена
_LEVEL = re.compile(r"\D*[^\W\d_]\s*(\d{1,3})")  # «ypOBeHb17»: подпись и номер в конце
_PLACE = re.compile(r"(\d+)(?:~(\d+))?")  # «11~12» или «7»
_SHARE = re.compile(r"\$(\d+\.\d{2})\s*\+\s*\$(\d+\.\d{2})")  # «$5.06+$0.44»

# по свёрнутому тексту (`_fold`): двойники приведены к латинице в нижнем регистре
_PLACES_PAID = re.compile(rf"({_NUM})\s*np.*")  # «330 npM30BbIX MeCT»
_DATE = re.compile(r"(\S{3})\s*(\d{1,2}),\s*(\d{1,2}):(\d{2})(?:\s*\(.*?(\d+)\))?")
_INTERVAL = re.compile(r"(?<!\d)(\d+)\s*m[nwmu]h$")  # «… 8MNH» — «8 мин» в конце строки
_SEATS = re.compile(r"(\d+)\s*\D*rpok\D*ha\s*cto\D*")  # «8MrpoKOBHa CTOn», не «за финальным»
_EARLY_BIRD = re.compile(r"early\s*bird|pahh")  # «Early Bird» или «PaHHAA nITAWKa»

# двойники кириллицы в латинице: так RapidOCR читает русские подписи
_FOLD = str.maketrans(
    {
        "а": "a", "в": "b", "г": "r", "д": "a", "е": "e", "ё": "e", "з": "3", "и": "n",
        "й": "n", "к": "k", "л": "n", "м": "m", "н": "h", "о": "o", "п": "n", "р": "p",
        "с": "c", "т": "t", "у": "y", "ф": "φ", "х": "x", "ш": "w", "щ": "w", "ь": "b",
        "ю": "o", "я": "a", "中": "φ",
    }
)  # fmt: skip

# месяц даты «Инфо» по трём буквам: ключ — настоящее сокращение, свёрнутое `_FOLD`, поэтому
# «окт» и двойник «OKT» дают одно; на кадрах видны «OKT» и «ceH». У «ю» латинского двойника на
# кадрах не было — свёрнут в «o» ради трёх букв. Неизвестный — отказ «время начала», не догадка
_MONTHS = {
    abbr.translate(_FOLD): number
    for number, abbrs in enumerate(
        ("янв", "фев", "мар", "апр", ("мая", "май"), "июн", "июл", "авг", "сен", "окт", "ноя",
         "дек"),
        start=1,
    )
    for abbr in ((abbrs,) if isinstance(abbrs, str) else abbrs)
}  # fmt: skip


@dataclass(frozen=True)
class Line:
    """Строка OCR: текст, рамка в пикселях исходного кадра (левый верхний угол, ширина,
    высота) и уверенность распознавания 0..1."""

    text: str
    x: float
    y: float
    w: float
    h: float
    score: float


@dataclass(frozen=True)
class Header:
    """Шапка лобби — она есть на каждом кадре."""

    level: int
    players_left: int
    entrants: int
    unique: int
    reentries: int
    prize_pool_usd: float
    buy_in_usd: float
    average_stack_chips: int


@dataclass(frozen=True)
class Info:
    """Вкладка «Инфо»."""

    prize_share_usd: float  # «$5.06+$0.44» → 5.06
    fee_usd: float  # → 0.44
    starting_stack_chips: int
    start: tuple[int, int, int, int]  # месяц, день, час, минута
    late_reg_close_level: int  # «(Уровень 17)»
    blind_interval_min: int
    seats_per_table: int  # «8 игроков на стол»
    early_bird: bool


@dataclass(frozen=True)
class Shot:
    """Один кадр лобби: что на нём и поля."""

    kind: str  # "prizes" | "info" | "other"
    title: str  # «Fifty Stack $5.50»
    header: Header
    payouts: list[tuple[int, int, float]]  # (с места, по место, приз $), только у "prizes"
    places_paid: int | None  # «N призовых мест», только у "prizes" и если строка на кадре
    info: Info | None  # только у "info"
    low_confidence: list[str]  # имена полей с уверенностью OCR < 0.8


def _norm(text: str) -> str:
    """NFKC (полноширинные скобки и цифры — обычные), без пробелов вокруг `~ / |`, `-` между
    числами — `~` диапазона."""
    text = unicodedata.normalize("NFKC", text).strip()
    text = re.sub(r"\s*([~/|])\s*", r"\1", text)
    return re.sub(r"(?<=\d)\s*-\s*(?=\d)", "~", text)


def _fold(text: str) -> str:
    """`_norm`, нижний регистр и кириллица → латинские двойники: «OKT» и «окт» — одно."""
    return _norm(text).lower().translate(_FOLD)


def _int(number: str) -> int:
    return int(number.replace(",", ""))


def _usd(number: str) -> float:
    return float(number.replace(",", ""))


def _cy(line: Line) -> float:
    return line.y + line.h / 2


def _same_row(a: Line, b: Line) -> bool:
    return abs(_cy(a) - _cy(b)) < _ROW * max(a.h, b.h)


def _missing(field: str) -> ValueError:
    return ValueError(f"на кадре не найдено: {field}")


class _Reader:
    """Разбор одного кадра; `self.unsure` копит поля с низкой уверенностью по порядку чтения."""

    def __init__(self, lines: list[Line], width: int):
        split = HEADER_BOTTOM * width
        self.width = width
        self.header = [line for line in lines if _cy(line) < split]
        self.body = sorted((line for line in lines if _cy(line) >= split), key=_cy)
        self.unsure: list[str] = []

    def _mark(self, field: str, *lines: Line) -> None:
        if min(line.score for line in lines) < _MIN_SCORE and field not in self.unsure:
            self.unsure.append(field)

    def _right(self, line: Line, match=None) -> bool:
        return line.x + line.w / 2 > self.width / 2

    def _find(self, lines, pattern, field, *, fold=False, where=lambda line, match: True):
        """Верхняя строка, целиком совпавшая с `pattern` (и с условием `where`), и её
        совпадение; нет — отказ с именем поля."""
        for line in sorted(lines, key=_cy):
            match = pattern.fullmatch(_fold(line.text) if fold else _norm(line.text))
            if match and where(line, match):
                return line, match
        raise _missing(field)

    # --- шапка ---

    def title(self) -> str:
        """Строка со словами и ценой в конце и её соседи слева в том же ряду той же высоты —
        «Fifty» + «Stack $5.50» склеиваются через пробел."""
        anchor, _ = self._find(self.header, _TITLE, "название")
        parts = [anchor]
        while True:
            left = parts[0]
            near = [
                line
                for line in self.header
                if line not in parts
                and _same_row(line, left)
                and min(line.h, left.h) >= 0.6 * max(line.h, left.h)
                and 0 <= left.x - (line.x + line.w) < 0.5 * left.h
            ]
            if not near:
                break
            parts.insert(0, max(near, key=lambda line: line.x))
        self._mark("название", *parts)
        return " ".join(_norm(line.text) for line in parts)

    def read_header(self) -> Header:
        # номер в конце подписи слева от блайндов «A/B (C)» в том же ряду правой половины шапки:
        # «#Typ60» («#Турбо») слева под названием тоже кончается цифрами
        blinds, _ = self._find(self.header, _BLINDS, "уровень")
        levels = [
            (line, match)
            for line in self.header
            if self._right(line)
            and _same_row(line, blinds)
            and line.x + line.w <= blinds.x
            and (match := _LEVEL.fullmatch(_norm(line.text)))
        ]
        if not levels:
            raise _missing("уровень")
        level_line, level = max(levels, key=lambda pair: pair[0].x)
        self._mark("уровень", level_line)

        counter_line, counter = self._find(
            self.header, _COUNTER, "счётчик игроков", where=self._right
        )
        self._mark("счётчик игроков", counter_line)
        split_line, split = self._find(
            self.header, _SPLIT, "уникальные и ре-энтри", where=self._right
        )
        self._mark("уникальные и ре-энтри", split_line)

        # призовой фонд — самая левая сумма шапки, одна в своём столбце; правее — столбец
        # «бай-ин / гарантия / оверлей», бай-ин в нём верхний и выше ряда «A|B»
        money = [
            (line, match)
            for line in self.header
            if (match := _MONEY_ONLY.fullmatch(_norm(line.text)))
        ]
        if not money:
            raise _missing("призовой фонд")
        pool_line, pool = min(money, key=lambda pair: pair[0].x)
        pool_right = pool_line.x + pool_line.w
        if any(line is not pool_line and line.x < pool_right for line, _ in money):
            raise _missing("призовой фонд")
        self._mark("призовой фонд", pool_line)
        buy_ins = [
            (line, match)
            for line, match in money
            if line.x >= pool_right
            and _cy(line) < _cy(split_line)
            and not _same_row(line, split_line)
        ]
        if not buy_ins:
            raise _missing("бай-ин")
        buy_in_line, buy_in = min(buy_ins, key=lambda pair: _cy(pair[0]))
        self._mark("бай-ин", buy_in_line)

        # средний стек — нижняя «N (x BB)» правой колонки, ниже ряда «A|B» (выше — старт/мин.
        # и макс. стек); без неё макс. стек средним не становится
        stacks = [
            (line, match)
            for line in self.header
            if self._right(line)
            and _cy(line) > _cy(split_line)
            and not _same_row(line, split_line)
            and (match := _STACK.fullmatch(_norm(line.text)))
        ]
        if not stacks:
            raise _missing("средний стек")
        average_line, average = max(stacks, key=lambda pair: _cy(pair[0]))
        self._mark("средний стек", average_line)

        return Header(
            level=int(level[1]),
            players_left=_int(counter[1]),
            entrants=_int(counter[2]),
            unique=int(split[1]),
            reentries=int(split[2]),
            prize_pool_usd=_usd(pool[1]),
            buy_in_usd=_usd(buy_in[1]),
            average_stack_chips=_int(average[1]),
        )

    # --- «Призовой фонд» ---

    def payouts(self) -> tuple[list[tuple[int, int, float]], int | None]:
        """Таблица «место — $приз» и «N призовых мест» над ней.

        Ячейки места и приза — пара, если они в одном ряду, место левее и каждая — ближайшая
        к другой. Ячейка без пары выпадает: место по порядку строк не достраивается, дыру назовёт
        проверка стыка (Задача 4)."""
        places = [(line, m) for line in self.body if (m := _PLACE.fullmatch(_norm(line.text)))]
        prizes = [
            (line, m) for line in self.body if (m := _MONEY_ONLY.fullmatch(_norm(line.text)))
        ]

        def nearest(line, others, left):
            row = [
                (other, m)
                for other, m in others
                if _same_row(line, other)
                and (other.x + other.w <= line.x if left else line.x + line.w <= other.x)
            ]
            return min(row, key=lambda pair: abs(_cy(pair[0]) - _cy(line)), default=(None, None))

        rows = []
        for prize_line, prize in prizes:
            place_line, place = nearest(prize_line, places, left=True)
            if place_line is not None and nearest(place_line, prizes, left=False)[0] is prize_line:
                rows.append((prize_line, place_line, place, prize))

        top = min((_cy(row[0]) for row in rows), default=None)
        counts = [
            (line, m)
            for line in self.body
            if (top is None or _cy(line) < top)
            and (m := _PLACES_PAID.fullmatch(_fold(line.text)))
        ]
        places_paid = None
        if counts:
            if not rows:
                raise _missing("таблица выплат")
            count_line, count = max(counts, key=lambda pair: _cy(pair[0]))
            self._mark("число призовых мест", count_line)
            places_paid = _int(count[1])

        payouts = []
        for prize_line, place_line, place, prize in rows:
            lo = int(place[1])
            hi = int(place[2]) if place[2] else lo
            name = f"выплата мест {lo}–{hi}" if hi != lo else f"выплата места {lo}"
            self._mark(name, place_line, prize_line)
            payouts.append((lo, hi, _usd(prize[1])))
        return payouts, places_paid

    # --- «Инфо» ---

    def info(self) -> Info | None:
        """Строки «Инфо» под строкой «$a+$b»; без неё кадр — не «Инфо»."""
        shares = [(line, m) for line in self.body if (m := _SHARE.fullmatch(_norm(line.text)))]
        if not shares:
            return None
        share_line, share = shares[0]
        self._mark("бай-ин и комиссия", share_line)
        below = [line for line in self.body if _cy(line) > _cy(share_line)]

        stack_line, stack = self._find(below, _STACK, "стартовый стек")
        self._mark("стартовый стек", stack_line)

        # «окт 30, 23:05» — начало; «окт 31, 01:30 (Уровень 17)» — конец поздней регистрации
        start_line, start = self._find(
            below, _DATE, "время начала", fold=True,
            where=lambda line, m: m[5] is None and m[1] in _MONTHS,
        )  # fmt: skip
        self._mark("время начала", start_line)
        close_line, close = self._find(
            below, _DATE, "конец поздней регистрации", fold=True,
            where=lambda line, m: m[5] is not None,
        )  # fmt: skip
        self._mark("конец поздней регистрации", close_line)

        intervals = [m for line in below if (m := _INTERVAL.search(_fold(line.text)))]
        if not intervals:
            raise _missing("интервал блайндов")

        seats_line, seats = self._find(below, _SEATS, "размер стола", fold=True)
        self._mark("размер стола", seats_line)

        return Info(
            prize_share_usd=float(share[1]),
            fee_usd=float(share[2]),
            starting_stack_chips=_int(stack[1]),
            start=(_MONTHS[start[1]], int(start[2]), int(start[3]), int(start[4])),
            late_reg_close_level=int(close[5]),
            blind_interval_min=int(intervals[0][1]),
            seats_per_table=int(seats[1]),
            early_bird=any(_EARLY_BIRD.search(_fold(line.text)) for line in below),
        )


def read_shot(lines: list[Line], width: int, height: int) -> Shot:
    """Поля одного кадра лобби по строкам OCR (`lobby_ocr.ocr_image`).

    `kind`: "prizes" — есть таблица выплат, "info" — есть строки «Инфо», иначе "other"
    («Структура» с её таблицами блайндов и «входов → мест» — тоже "other"). Шапка обязательна на
    любом кадре: нет её поля — `ValueError` «на кадре не найдено: {поле}». `height` не нужен
    разбору (границы — доли ширины), он в подписи ради симметрии с `ocr_image`.
    """
    reader = _Reader(lines, width)
    title = reader.title()
    header = reader.read_header()
    payouts, places_paid = reader.payouts()
    info = None if payouts else reader.info()
    kind = "prizes" if payouts else "info" if info else "other"
    return Shot(
        kind=kind,
        title=title,
        header=header,
        payouts=payouts,
        places_paid=places_paid,
        info=info,
        low_confidence=reader.unsure,
    )
