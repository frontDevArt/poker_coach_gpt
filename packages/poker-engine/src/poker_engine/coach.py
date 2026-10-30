"""Файл раздачи и команды `coach` (спека тренера §5).

Одна раздача — один JSON-файл: контекст и кадры как пришли, шаги с ответами советников, итоги
улиц. Файл — единственное состояние разбора: модель-тренер ничего не помнит и не считает, каждый
шаг перечитывает файл и выводит узлы из кадров заново. Ответ шага хранится целиком — он
`history` следующих шагов.

Файл меняется только целиком: новое содержимое пишется во временный файл рядом и встаёт на место
через `os.replace`. Неудачный шаг файл не трогает, а `step` + `undo` возвращает его байт в байт.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile

from . import frames
from .advice import advise
from .handstate import _validate_context, context_from_dict

FORMAT = "poker-coach-hand"
VERSION = 1
# Поля файла и их форма — для текста «файл раздачи повреждён: <поле>».
_FIELDS = (("context", dict), ("frames", list), ("steps", list), ("streets", dict))


def start(path: str, context: dict) -> dict:
    """Новый файл раздачи без кадров. Файл уже есть — отказ: перезаписи нет.

    Контекст проверяется сразу, чтобы ошибка в нём не всплыла только на первом кадре. Средний
    стек в фишках делится на большой блайнд кадра — до первого шага проверяется только он сам.
    """
    if os.path.exists(path):
        raise ValueError(f"файл раздачи уже есть: {path}")
    _validate_context(context_from_dict(frames.context_payload(context, None)))
    _write(
        path,
        {
            "format": FORMAT,
            "version": VERSION,
            "context": context,
            "frames": [],
            "steps": [],
            "streets": {},
        },
    )
    return {"hand": path, "steps": 0}


def step(path: str, frame: dict) -> dict:
    """Кадр в конец раздачи, совет на нём с ответами прошлых шагов в `history`, запись.

    Отказ советников (`advisor: null`) — нормальный шаг, он хранится. Битый кадр или раздача,
    которую не пропускает валидатор, — `ValueError`, файл прежний.
    """
    data = _load(path)
    seen = [*data["frames"], frame]
    nodes = [frames.node_payload(raw) for raw in seen]
    context = frames.context_payload(data["context"], seen[-1])
    answer = advise(context, nodes, [done["answer"] for done in data["steps"]])
    number = len(seen)
    record = {"frame": number, "advisor": answer["advisor"], "answer": answer, "why": []}
    data["frames"].append(frame)
    data["steps"].append(record)
    _write(path, data)
    return {
        "step": number,
        "advisor": answer["advisor"],
        "answer": answer,
        "why": record["why"],
        "streets": data["streets"],
    }


def undo(path: str) -> dict:
    """Снимает последний кадр и его шаг — когда кадр прочитан неверно."""
    data = _load(path)
    if not data["frames"]:
        raise ValueError("в раздаче нет кадров: отменять нечего")
    number = len(data["frames"])
    data["frames"].pop()
    data["steps"].pop()
    _write(path, data)
    return {"undone": number, "steps": number - 1}


def _load(path: str) -> dict:
    if not os.path.exists(path):
        raise ValueError(f"файла раздачи нет: {path}")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ValueError(f"не удалось прочитать {path!r}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise _damaged("не JSON") from None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise _damaged("format")
    # `True == 1` в Python: версия — целое, а не логическое.
    version = data.get("version")
    if isinstance(version, bool) or version != VERSION:
        raise _damaged("version")
    for key, kind in _FIELDS:
        if not isinstance(data.get(key), kind):
            raise _damaged(key)
    if not all(isinstance(raw, dict) for raw in data["frames"]):
        raise _damaged("frames")
    # Шаг на каждый кадр: удачный `step` пишет оба, `undo` снимает оба.
    if len(data["steps"]) != len(data["frames"]) or not all(
        isinstance(done, dict) and isinstance(done.get("answer"), dict) for done in data["steps"]
    ):
        raise _damaged("steps")
    return data


def _damaged(what: str) -> ValueError:
    return ValueError(f"файл раздачи повреждён: {what}")


def _write(path: str, data: dict) -> None:
    """Атомарная запись: временный файл в той же папке, затем `os.replace` поверх.

    Байты собираются до того, как тронут диск: сериализация, упавшая на середине, не оставит
    полфайла. Отступ и порядок ключей постоянны — `step` + `undo` дают тот же файл байт в байт.
    """
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    try:
        handle, temporary = tempfile.mkstemp(prefix=".hand-", suffix=".tmp", dir=directory)
    except OSError as exc:
        raise ValueError(f"не удалось записать {path!r}: {exc}") from exc
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(payload)
        os.replace(temporary, path)
    except BaseException as exc:
        with contextlib.suppress(OSError):
            os.remove(temporary)
        if isinstance(exc, OSError):
            raise ValueError(f"не удалось записать {path!r}: {exc}") from exc
        raise
