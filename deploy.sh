#!/usr/bin/env bash
# Déploiement / mise à jour de l'Observatoire sur le VPS.
# Récupère la dernière version du code, active la recherche de liens officiels
# dans .env, puis (par défaut) lance une synthèse de TEST locale — aucun envoi.
#
# Usage :
#   bash deploy.sh            # pull + .env + synthèse de test
#   bash deploy.sh --no-test  # pull + .env seulement (pas d'appel API)
set -euo pipefail

cd "$(dirname "$0")"

RUN_TEST=1
for arg in "$@"; do
  case "$arg" in
    --no-test) RUN_TEST=0 ;;
    *) echo "Argument inconnu : $arg (attendu : --no-test)" >&2; exit 2 ;;
  esac
done

# 1) Mise à jour du code — on FORCE toujours la branche canonique --------------
# (Évite le piège où le VPS reste bloqué sur une mauvaise branche / un vieux
#  commit : on se réaligne durement sur le tip distant à chaque déploiement.
#  Les secrets/données — .env, credentials.json, 01_/02_… — ne sont pas suivis
#  par git, donc intacts. Seul le CODE est réécrit ; sa source de vérité est GitHub.)
BRANCH="${DEPLOY_BRANCH:-claude/pensive-einstein-S5Fds}"
echo "==> Mise à jour du code (branche forcée : $BRANCH)"
git fetch origin "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
echo "==> Maintenant sur : $(git log --oneline -1)"

# 2) Activation de OFFICIAL_LINK_SEARCH dans .env (idempotent) -----------------
if [ ! -f .env ]; then
  echo "⚠  .env absent — copie depuis .env.example (à compléter : ANTHROPIC_API_KEY…)."
  cp .env.example .env
fi
if grep -q '^OFFICIAL_LINK_SEARCH=' .env; then
  sed -i 's/^OFFICIAL_LINK_SEARCH=.*/OFFICIAL_LINK_SEARCH=1/' .env
else
  echo 'OFFICIAL_LINK_SEARCH=1' >> .env
fi
echo "==> OFFICIAL_LINK_SEARCH=1 (liens « site officiel » activés)"

# 3) Interpréteur Python (venv si présent) ------------------------------------
if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
  echo "==> Dépendances à jour dans .venv"
  .venv/bin/pip install --quiet -r requirements.txt
else
  PY=python3
  echo "⚠  .venv introuvable — utilisation de python3 système (lance install.sh pour créer le venv)."
fi

# 4) Synthèse de test (locale, aucun envoi) -----------------------------------
if [ "$RUN_TEST" = "1" ]; then
  echo "==> Synthèse de test (aucun envoi ; brouillon local uniquement)…"
  "$PY" scripts/synthesize.py
else
  echo "==> Test ignoré (--no-test)."
fi

echo ""
echo "✅ Déploiement terminé."
echo "   • Code à jour, OFFICIAL_LINK_SEARCH=1"
echo "   • Le cron existant prend le relais (collecte quotidienne + synthèse du vendredi)."
