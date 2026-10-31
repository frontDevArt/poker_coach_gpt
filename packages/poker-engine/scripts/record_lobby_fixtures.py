"""Запись фикстур распознавания лобби (план D40, Задача 2; спека лобби §8).

Прогоняет кадры лобби через `poker_engine.lobby_ocr.ocr_image` и пишет по JSON на кадр: имя —
имя файла без `.png`, формат `{"width", "height", "captured", "lines": [{text, x, y, w, h,
score}]}`; `captured` — дата изменения файла. Скриншоты в репозиторий не идут, в фикстуры — тоже.

**Маска ников.** Ники игроков в фикстуры не попадают: текст строки заменяется на «•», рамка и
уверенность остаются. `ocr_image` панели «Бэкинг» и «Игроки» не читает вовсе, поэтому
ников там нет и так; маска по их зонам — вторая, страховочная линия на случай, если область чтения
расширят. Живая зона — строка лидеров шапки. Маскируется центр рамки в зонах, где GG показывает
ники: панели «Бэкинг» (левее `0.34·ширина`) и «Игроки» (правее `0.65·ширина`) ниже 190 px, и строка
лидеров в шапке (левее 400 px, ниже 100 px, выше 190 px). Заголовок турнира (выше 100 px), счётчики
шапки справа и средняя колонка («Инфо», «Структура», «Призовой фонд») не маскируются: из них разбор
берёт поля. Каждую фикстуру глазами сверяют: ни одного ника.

Запуск из `packages/poker-engine`:
`.venv/Scripts/python scripts/record_lobby_fixtures.py <png…> --out tests/data/lobby`
(Linux — `.venv/bin/python`). Нужна группа `[lobby]`; около 11–16 с на кадр на i5-4460.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import time

MASK = "•"
_HEADER_BOTTOM = 190
_TITLE_BOTTOM = 100
_LEADERS_RIGHT = 400
_BACKING_RIGHT = 0.34
_PLAYERS_LEFT = 0.65


def is_nick_zone(line, width: int) -> bool:
    """Центр рамки `line` лежит там, где GG показывает ники (правило — в докстринге модуля)."""
    cx = line.x + line.w / 2
    cy = line.y + line.h / 2
    if cy > _HEADER_BOTTOM:
        return cx < _BACKING_RIGHT * width or cx > _PLAYERS_LEFT * width
    return cy > _TITLE_BOTTOM and cx < _LEADERS_RIGHT


def fixture_dict(lines, width: int, height: int, captured: str) -> dict:
    """Фикстура: строки с маской ников, рамки округлены до 0.1 px, уверенность — до 4 знаков."""
    return {
        "width": width,
        "height": height,
        "captured": captured,
        "lines": [
            {
                "text": MASK if is_nick_zone(line, width) else line.text,
                "x": round(line.x, 1),
                "y": round(line.y, 1),
                "w": round(line.w, 1),
                "h": round(line.h, 1),
                "score": round(line.score, 4),
            }
            for line in lines
        ],
    }


def main(argv=None) -> int:
    from poker_engine.cli import _ensure_utf8_stdout
    from poker_engine.lobby_ocr import ocr_image

    _ensure_utf8_stdout()  # кириллица в print не должна ронять пакетную запись на консоли cp1251/cp1252
    parser = argparse.ArgumentParser(description="Записать фикстуры распознавания лобби")
    parser.add_argument("images", nargs="+", type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for image in args.images:
        started = time.perf_counter()
        lines, width, height = ocr_image(str(image))
        captured = datetime.date.fromtimestamp(image.stat().st_mtime).isoformat()
        target = args.out / f"{image.stem}.json"
        data = fixture_dict(lines, width, height, captured)
        target.write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"{target}: {len(lines)} строк, {time.perf_counter() - started:.1f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
