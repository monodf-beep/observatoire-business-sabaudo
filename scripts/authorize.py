#!/usr/bin/env python3
"""Autorisation Google (à lancer UNE FOIS sur une machine avec navigateur).

Déclenche les deux flux OAuth (Gmail en lecture + Drive en écriture) et crée
les fichiers `config/token.json` et `config/token_drive.json`.

Pourquoi ce script ? Un serveur VPS n'a pas de navigateur : on autorise donc
ici (sur ton ordinateur), puis on copie le dossier `config/` sur le VPS.
Voir docs/DEPLOIEMENT_HOSTINGER.md.

Usage :
    python scripts/authorize.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.logger import get_logger  # noqa: E402

log = get_logger("authorize")


def main() -> int:
    load_dotenv(ROOT / ".env")
    log.info("=== Autorisation Google (Gmail + Drive) ===")
    log.info("Une page Google va s'ouvrir dans ton navigateur, deux fois.")

    # Gmail (lecture)
    try:
        from scripts.gmail_collect import build_service

        build_service()
        log.info("✅ Autorisation Gmail OK → config/token.json créé.")
    except Exception as exc:
        log.error("Échec autorisation Gmail : %s", exc)
        return 1

    # Drive (écriture des fichiers créés par l'app)
    try:
        from utils.drive_upload import _get_service

        _get_service()
        log.info("✅ Autorisation Drive OK → config/token_drive.json créé.")
    except Exception as exc:
        log.error("Échec autorisation Drive : %s", exc)
        return 1

    log.info("")
    log.info("Terminé. Copie maintenant le dossier config/ sur ton VPS")
    log.info("(credentials.json + token.json + token_drive.json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
