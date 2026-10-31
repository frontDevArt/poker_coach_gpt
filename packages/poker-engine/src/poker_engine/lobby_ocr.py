"""Распознавание кадра лобби GG: RapidOCR на всём кадре (план D40, Задача 2; спека лобби §8).

Тонкий слой: открыть кадр, увеличить вдвое, вызвать RapidOCR, вернуть строки с рамками в
пикселях исходного кадра. Разбор строк в поля — `lobby_read`, здесь его нет. RapidOCR и Pillow
подключаются внутри функции: без группы `[lobby]` модуль импортируется, а вызов отказывает.
Замер спайка — около 31 с на кадр 1195×1035 на i5-4460.
"""

from poker_engine.lobby_read import Line

_SCALE = 2
_NO_DEPS = 'для разбора лобби нужны зависимости: pip install -e ".[lobby]"'

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


def ocr_image(path: str) -> tuple[list[Line], int, int]:
    """Строки кадра `path`, его ширина и высота в пикселях.

    Кадр увеличивается вдвое (LANCZOS), RapidOCR читает его целиком, рамки делятся обратно на 2.
    `Line.x`, `Line.y` — левый верхний угол охватывающего прямоугольника.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise ValueError(_NO_DEPS) from None
    engine = _get_engine()
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = image.size
    big = image.resize((width * _SCALE, height * _SCALE), Image.LANCZOS)
    result, _ = engine(np.asarray(big)[:, :, ::-1])  # RapidOCR ждёт BGR
    lines = []
    for box, text, score in result or []:
        xs = [point[0] / _SCALE for point in box]
        ys = [point[1] / _SCALE for point in box]
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
    return lines, width, height
