#!/usr/bin/env bash
# Installation de l'Observatoire Économique Espace Sabaudo.
# Crée l'environnement virtuel, installe les dépendances et prépare le .env.
# Usage : bash install.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Vérification de Python 3.11+"
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERREUR : Python 3 introuvable. Installe Python 3.11+ puis relance." >&2
  exit 1
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    sys.exit("ERREUR : Python 3.11+ requis (version detectee : %d.%d)" % sys.version_info[:2])
PY

echo "==> Création de l'environnement virtuel (.venv)"
python3 -m venv .venv

echo "==> Installation des dépendances"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Création du fichier .env (à compléter)"
  cp .env.example .env
else
  echo "==> .env déjà présent, conservé tel quel"
fi

mkdir -p config 01_Veille_brute "02_Veille_traitée/Synthèses_hebdomadaires" logs

echo ""
echo "✅ Installation terminée."
echo ""
echo "Étapes suivantes :"
echo "  1. Éditer .env et coller ANTHROPIC_API_KEY"
echo "  2. Déposer config/credentials.json (voir docs/SETUP_GOOGLE_OAUTH.md)"
echo "  3. Activer l'environnement :   source .venv/bin/activate"
echo "  4. Premier test :              python scripts/synthesize.py --upload"
