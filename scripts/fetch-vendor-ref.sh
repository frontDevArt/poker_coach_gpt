#!/usr/bin/env bash
# Клонирует референсные репозитории в vendor-ref/ (read-only, не в git).
# Используются как источник по формату данных GG и для cross-check (T4).
# Версии пинятся в vendor-ref.lock — без этого «воспроизводимо» было бы на словах.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/vendor-ref"
LOCK="$ROOT/vendor-ref.lock"
mkdir -p "$DEST"

if [ ! -f "$LOCK" ]; then
  echo "нет $LOCK" >&2
  exit 1
fi

# Комментарии и пустые строки пропускаются; остальное — dir repo sha.
# tr срезает CR: лок может лечь на диск с CRLF, и тогда sha уедет в checkout с хвостом.
while read -r dir repo sha; do
  case "${dir:-}" in ''|'#'*) continue ;; esac

  if [ ! -d "$DEST/$dir/.git" ]; then
    git clone "https://github.com/$repo.git" "$DEST/$dir"
  fi

  if [ "$(git -C "$DEST/$dir" rev-parse HEAD)" = "$sha" ]; then
    echo "ok   $dir ($sha)"
    continue
  fi

  git -C "$DEST/$dir" fetch --quiet origin "$sha" 2>/dev/null || git -C "$DEST/$dir" fetch --quiet origin
  git -C "$DEST/$dir" checkout --quiet --detach "$sha"
  echo "pin  $dir -> $sha"
done < <(tr -d '\r' < "$LOCK")

echo
echo "Готово. vendor-ref/ соответствует vendor-ref.lock."
