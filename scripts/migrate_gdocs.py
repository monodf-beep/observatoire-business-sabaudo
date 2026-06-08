#!/usr/bin/env python3
"""Migration : convertit les synthèses Markdown existantes en Google Docs natifs.

Parcourt les synthèses locales (02_Veille_traitee/Syntheses_hebdomadaires/*.md) et
crée/met à jour, pour chacune, un Google Doc mis en forme dans le Drive. Idempotent
(dédoublonnage par titre) : on peut le relancer sans créer de doublon.

Usage :
    python scripts/migrate_gdocs.py            # toutes les semaines présentes
    python scripts/migrate_gdocs.py 2026-W23   # une seule semaine
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"

log = get_logger("migrate_gdocs")


def _week_label_human(week_id: str) -> str:
    """Réutilise le format humain de synthesize sans dépendance circulaire."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from synthesize import week_label_human

    return week_label_human(week_id)


def main() -> int:
    load_dotenv(ROOT / ".env")
    from utils.drive_upload import upload_markdown_as_gdoc

    subfolder = os.getenv("DRIVE_VEILLE_TRAITEE_SUBFOLDER", "02_Veille_traitee")
    only = sys.argv[1] if len(sys.argv) > 1 else None

    if not OUTPUT_DIR.exists():
        log.error("Aucune synthèse locale trouvée (%s absent).", OUTPUT_DIR)
        return 1

    md_files = sorted(OUTPUT_DIR.glob("*.md"))
    if only:
        md_files = [f for f in md_files if f.stem == only]
    if not md_files:
        log.warning("Aucune synthèse à migrer%s.", f" pour {only}" if only else "")
        return 0

    ok = 0
    for md in md_files:
        doc_name = f"Business Sabaudo — {_week_label_human(md.stem)}"
        doc_id = upload_markdown_as_gdoc(md, subfolder=subfolder, name=doc_name)
        if doc_id:
            log.info("✓ %s → Google Doc (id=%s)", md.name, doc_id)
            ok += 1
        else:
            log.warning("✗ %s : conversion échouée", md.name)

    log.info("Migration terminée : %d/%d synthèse(s) en Google Doc.", ok, len(md_files))
    return 0 if ok == len(md_files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
