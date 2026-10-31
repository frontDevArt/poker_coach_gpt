"""Распознавание кадра лобби GG: RapidOCR по двум вырезкам (план D40, Задача 2; спека лобби §8).

Тонкий слой: открыть кадр, вырезать шапку и среднюю колонку, увеличить, вызвать RapidOCR, вернуть
строки с рамками в пикселях исходного кадра. Разбор строк в поля — `lobby_read`, здесь его нет.
RapidOCR и Pillow подключаются внутри функции: без группы `[lobby]` модуль импортируется, а
вызов отказывает.

Почему вырезки, а не весь кадр. На целом кадре, увеличенном вдвое, RapidOCR терял цифру «1» места
1, склеивал «1474|349» в «14741349», а классификатор угла текста переворачивал одиночные цифры
(«6» читалось как «9» с уверенностью 1.0, и проверка уверенности такое не ловит). Поэтому
классификатор угла выключен, а читаются только две области, из которых разбор берёт поля:
шапка с названием (весь кадр по ширине, крупнее — счётчики мелкие) и средняя колонка
(«Инфо», «Структура», «Призовой фонд»). Панели «Бэкинг» и «Игроки» с никами не читаются вовсе.

Счётчик «A|B» шапки с потерянной чертой («1455335») перечитывается узкой вырезкой.

Границы — доли ширины кадра, не пиксели: интерфейс GG масштабируется по ширине окна, а высота
окна меняется (1035 px и 740 px при той же ширине). Шапка кончается на `0.155·ширина` — между
подписью «Распределение выплат» (до ~0.150) и подписями вкладок (с ~0.164). Около 16 с на кадр на
i5-4460 (спайк по целому кадру — ~31 с).
"""

import re

from poker_engine.lobby_read import Line

_NO_DEPS = 'для разбора лобби нужны зависимости: pip install -e ".[lobby]"'

_HEADER_BOTTOM = 0.155  # доля ширины кадра; граница шапки и тела
_BODY_LEFT = 0.345  # средняя колонка — доли ширины кадра
_BODY_RIGHT = 0.655
_HEADER_SCALE = 3
_BODY_SCALE = 2

_FUSED = re.compile(r"\d{5,}")  # «1455335»: RapidOCR потерял черту счётчика «1455|335»
_SPLIT = re.compile(r"\d+\s*\|\s*\d+")
_REREAD_PAD = 8
_REREAD_SCALES = (4, 6, 3)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            raise ValueError(_NO_DEPS) from None
        _engine = RapidOCR()
    return _engine


def _read_crop(engine, image, box, scale):
    """Строки области `box` (левый, верхний, правый, нижний, пиксели кадра), увеличенной в
    `scale` раз (LANCZOS); рамки — в пикселях кадра."""
    import numpy as np
    from PIL import Image

    left, top, right, bottom = box
    crop = image.crop(box)
    big = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    # use_cls=False: классификатор угла переворачивает одиночные цифры (6 <-> 9)
    result, _ = engine(np.asarray(big)[:, :, ::-1], use_cls=False)  # RapidOCR ждёт BGR
    lines = []
    for quad, text, score in result or []:
        xs = [point[0] / scale + left for point in quad]
        ys = [point[1] / scale + top for point in quad]
        lines.append(
            Line(
                text=text,
                x=min(xs),
                y=min(ys),
                w=max(xs) - min(xs),
                h=max(ys) - min(ys),
                score=float(score),
            )
        )
    return lines


def _repair_counters(engine, image, lines):
    """Счётчик «уникальные | ре-энтри» иногда читается без черты («1455|335» → «1455335») с
    уверенностью 1.0, а разобрать склейку нельзя. Такая строка читается заново узкой вырезкой
    (поля `_REREAD_PAD` px) на нескольких увеличениях; принимается первое чтение вида `A|B`.
    Не вышло — строка остаётся как была, разбор откажет по ней сам."""
    repaired = []
    for line in lines:
        if _FUSED.fullmatch(line.text.strip()):
            box = (
                int(line.x - _REREAD_PAD),
                int(line.y - _REREAD_PAD),
                int(line.x + line.w + _REREAD_PAD),
                int(line.y + line.h + _REREAD_PAD),
            )
            for scale in _REREAD_SCALES:
                again = _read_crop(engine, image, box, scale)
                if len(again) == 1 and _SPLIT.fullmatch(again[0].text.strip()):
                    line = again[0]
                    break
        repaired.append(line)
    return repaired


def ocr_image(path: str) -> tuple[list[Line], int, int]:
    """Строки шапки и средней колонки кадра `path`, его ширина и высота в пикселях.

    `Line.x`, `Line.y` — левый верхний угол охватывающего прямоугольника в пикселях кадра.
    Строки отсортированы по `(y, x)`.
    """
    try:
        from PIL import Image
    except ImportError:
        raise ValueError(_NO_DEPS) from None
    engine = _get_engine()
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = image.size
    split = round(_HEADER_BOTTOM * width)
    left = round(_BODY_LEFT * width)
    right = round(_BODY_RIGHT * width)
    header = _read_crop(engine, image, (0, 0, width, split), _HEADER_SCALE)
    lines = _repair_counters(engine, image, header)
    lines += _read_crop(engine, image, (left, split, right, height), _BODY_SCALE)
    lines.sort(key=lambda line: (line.y, line.x))
    return lines, width, height
