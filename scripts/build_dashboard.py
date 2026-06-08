#!/usr/bin/env python3
"""Génère le tableau de bord visuel « Business Sabaudo » (page HTML autonome).

Agrège les données des synthèses hebdomadaires (02_Veille_traitee/
Syntheses_hebdomadaires/*.json) et produit une page HTML unique récapitulative.

Usage :
    python scripts/build_dashboard.py            # écrit dashboard.html en local
    python scripts/build_dashboard.py --upload   # + dépôt du fichier sur le Drive
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.dashboard import render_dashboard  # noqa: E402
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"

log = get_logger("build_dashboard")


def load_weeks() -> list[tuple[str, dict]]:
    """Charge les données de chaque semaine : [(week_id, data), ...]."""
    weeks: list[tuple[str, dict]] = []
    if not OUTPUT_DIR.exists():
        return weeks
    for jf in sorted(OUTPUT_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Synthèse illisible ignorée (%s) : %s", jf.name, exc)
            continue
        weeks.append((jf.stem, data))
    return weeks


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Tableau de bord Business Sabaudo.")
    parser.add_argument("--upload", action="store_true", help="Déposer la page sur le Drive.")
    args = parser.parse_args()

    weeks = load_weeks()
    if not weeks:
        log.warning("Aucune donnée de synthèse (%s). Tableau de bord non généré.", OUTPUT_DIR)
        return 0

    generated = f"{datetime.now(timezone.utc):%d/%m/%Y}"
    html = render_dashboard(weeks, generated_at=generated)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    log.info("Tableau de bord écrit : %s (%d semaine(s)).", DASHBOARD_PATH, len(weeks))

    if args.upload:
        from utils.drive_upload import upload_file

        subfolder = os.getenv("DRIVE_VEILLE_TRAITEE_SUBFOLDER", "02_Veille_traitee")
        file_id = upload_file(DASHBOARD_PATH, subfolder=subfolder)
        if file_id:
            log.info("Tableau de bord déposé sur le Drive (id=%s).", file_id)
        else:
            log.warning("Dépôt Drive échoué — le fichier local reste disponible.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
