#!/usr/bin/env python3
"""Autorisation Google (à lancer UNE FOIS) — Gmail (lecture) + Drive (écriture).

Crée les fichiers `config/token.json` et `config/token_drive.json`.

Deux modes :
- défaut : ouvre un navigateur local (machine de bureau avec interface graphique) ;
- `--manual` : pour un serveur SANS navigateur (VPS). Le script affiche une URL,
  tu autorises dans ton navigateur, puis tu recolles l'URL de redirection.

Usage :
    python scripts/authorize.py              # poste de bureau
    python scripts/authorize.py --manual     # serveur / VPS
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.logger import get_logger  # noqa: E402

log = get_logger("authorize")


def main() -> int:
    parser = argparse.ArgumentParser(description="Autorisation Google (Gmail + Drive).")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Mode sans navigateur local (serveur/VPS) : copier/coller de l'URL.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    log.info("=== Autorisation Google (Gmail + Drive) ===")
    if args.manual:
        log.info("Mode manuel : autorisation par copier/coller d'URL (deux fois).")

    # Gmail (lecture)
    try:
        from scripts.gmail_collect import build_service

        build_service(manual=args.manual)
        log.info("✅ Autorisation Gmail OK → config/token.json créé.")
    except Exception as exc:
        log.error("Échec autorisation Gmail : %s", exc)
        return 1

    # Drive (écriture des fichiers créés par l'app)
    try:
        from utils.drive_upload import _get_service

        _get_service(manual=args.manual)
        log.info("✅ Autorisation Drive OK → config/token_drive.json créé.")
    except Exception as exc:
        log.error("Échec autorisation Drive : %s", exc)
        return 1

    log.info("Terminé. Tu peux maintenant lancer gmail_collect.py et synthesize.py --upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
