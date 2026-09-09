#!/usr/bin/env bash
# Клонирует референсные репозитории в vendor-ref/ (read-only, не в git).
# Используются как источник по формату данных GG и для cross-check (T4).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/vendor-ref"
mkdir -p "$DEST"

clone() {
  local repo="$1" dir="$2"
  if [ -d "$DEST/$dir/.git" ]; then
    echo "skip $dir (уже склонирован)"
    return
  fi
  git clone --depth 50 "https://github.com/$repo.git" "$DEST/$dir"
}

clone "matthiola0/poker-hand-review"      "poker-hand-review"
clone "McDic/pokercraft-local"            "pokercraft-local"
clone "LayorX/GGPoker-Hand-Analyzer"      "ggpoker-hand-analyzer"
clone "AHTOOOXA/poker-charts"             "poker-charts"
clone "uoftcprg/pokerkit"                 "pokerkit"

echo
echo "Готово. Зафиксировать использованные коммиты:"
for d in "$DEST"/*/; do
  [ -d "$d/.git" ] || continue
  printf '%-28s %s\n' "$(basename "$d")" "$(git -C "$d" rev-parse --short HEAD)"
done
