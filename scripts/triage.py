#!/usr/bin/env python3
"""Étage de TRI LLM de la veille (à lancer après la collecte, avant build_dashboard).

Parcourt les éléments de la semaine courante (après les filtres par mots-clés) et
demande à un modèle léger, pour chacun : GARDER/JETER (pertinence économique pour le
périmètre sabaudo) + un TITRE propre. Le résultat est mis en cache (logs/triage_cache.json)
et consommé par build_dashboard. Chaque élément n'est jugé qu'UNE fois.

Usage :
    python scripts/triage.py            # juge les nouveaux éléments de la semaine
    python scripts/triage.py --stats    # n'appelle pas le LLM ; montre l'état du cache
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from scripts.build_dashboard import load_latest_week_items  # noqa: E402
from utils.logger import get_logger  # noqa: E402
from utils.triage import item_key, load_cache, triage  # noqa: E402

log = get_logger("triage")


def _units() -> list[dict]:
    """Tous les éléments de la semaine (sans tri) → unités à juger."""
    _week, by_territory = load_latest_week_items(apply_triage=False)[:2]
    units, seen = [], set()
    for terr, items in by_territory.items():
        for it in items:
            key = item_key(it.get("url", ""), it.get("title", ""))
            if key in seen:
                continue
            seen.add(key)
            units.append({
                "key": key,
                "title": it.get("title", ""),
                "source": it.get("source", ""),
                "territoire": terr,
            })
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description="Tri LLM de la veille.")
    parser.add_argument("--stats", action="store_true", help="État du cache, sans appel LLM.")
    args = parser.parse_args()

    units = _units()
    cache = load_cache()
    new = [u for u in units if u["key"] not in cache]
    log.info("Semaine : %d élément(s), %d déjà jugé(s), %d à juger.",
             len(units), len(units) - len(new), len(new))

    if args.stats:
        kept = sum(1 for v in cache.values() if v.get("keep"))
        log.info("Cache : %d verdicts (%d gardés, %d jetés).", len(cache), kept, len(cache) - kept)
        return 0

    cache = triage(units, log=log)
    judged = {u["key"]: cache.get(u["key"], {}) for u in units}
    kept = sum(1 for v in judged.values() if v.get("keep"))
    log.info("=== Tri terminé : %d gardé(s) / %d jeté(s) sur %d ===",
             kept, len(units) - kept, len(units))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
