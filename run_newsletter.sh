#!/usr/bin/env bash
# Lancement sécurisé de la newsletter : tire le code à jour AVANT de synthétiser.
# Usage : ./run_newsletter.sh [--week 2026-W23] [--brevo] [--force] [--no-pull]
#
# Sans --no-pull : git pull automatique (recommandé).
# Avec --no-pull : lance directement (utile quand on travaille sur une branche locale).

set -euo pipefail
cd "$(dirname "$0")"

BRANCH=$(git rev-parse --abbrev-ref HEAD)
PULL=1
ARGS=()

for arg in "$@"; do
  if [[ "$arg" == "--no-pull" ]]; then
    PULL=0
  else
    ARGS+=("$arg")
  fi
done

if [[ $PULL -eq 1 ]]; then
  echo "── git pull origin $BRANCH ──────────────────────"
  git pull origin "$BRANCH"
  echo "─────────────────────────────────────────────────"
fi

COMMIT=$(git rev-parse --short HEAD)
echo "▶ Lancement sur commit $COMMIT (branche : $BRANCH)"
echo ""

python -m scripts.synthesize "${ARGS[@]}"
