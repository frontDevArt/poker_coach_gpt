"""Атомарная запись JSON-файла — общая для файла раздачи (`coach`) и файла турнира (`lobby`)."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile


def write_json(path: str, data: dict, prefix: str) -> None:
    """Атомарная запись: временный файл `<prefix>….tmp` в той же папке, затем `os.replace` поверх.

    Байты собираются до того, как тронут диск: сериализация, упавшая на середине, не оставит
    полфайла. Отступ и порядок ключей постоянны — та же запись даёт тот же файл байт в байт.
    Сбой диска — `ValueError` «не удалось записать …», файл прежний, временного не остаётся.
    """
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    try:
        handle, temporary = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
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
