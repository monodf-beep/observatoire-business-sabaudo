#!/usr/bin/env python3
"""Crée un BROUILLON de campagne Brevo à partir des données structurées d'une semaine.

- Entrée : 02_Veille_traitee/Syntheses_hebdomadaires/AAAA-WNN.json (écrit par synthesize.py)
- Rendu : gabarit « magazine » (utils/newsletter_variants.variant_magazine)
- ⚠ N'ENVOIE JAMAIS : Franck relit dans Brevo puis déclenche l'envoi lui-même.

Configuration (.env) :
    BREVO_API_KEY        clé API Brevo
    BREVO_SENDER_NAME    nom de l'expéditeur (ex. Cultura Sabauda)
    BREVO_SENDER_EMAIL   email expéditeur VALIDÉ dans Brevo
    BREVO_LIST_ID        id(s) de la liste de destinataires (ex. 2 ou 2,3)
    BREVO_LOGO_URL       (option) URL du logo hébergé (bibliothèque média Brevo)

Usage :
    python scripts/push_brevo.py --week 2026-W24     # rend et crée le brouillon
    python scripts/push_brevo.py --file chemin.json
    python scripts/push_brevo.py --check             # liste expéditeurs + listes Brevo
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.brevo import (  # noqa: E402
    BrevoError,
    campaign_edit_url,
    create_draft_campaign,
    list_contact_lists,
    list_senders,
)
from utils.logger import get_logger  # noqa: E402
from utils.newsletter_variants import variant_magazine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SYNTH_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"

log = get_logger("push_brevo")


def find_data(week: str | None, file_arg: str | None) -> Path | None:
    if file_arg:
        path = Path(file_arg)
        return path if path.is_file() else None
    if week:
        path = SYNTH_DIR / f"{week}.json"
        return path if path.is_file() else None
    if not SYNTH_DIR.exists():
        return None
    candidates = sorted(SYNTH_DIR.glob("*.json"))
    return candidates[-1] if candidates else None


def _env_list_ids() -> list[int]:
    raw = os.getenv("BREVO_LIST_ID", "").strip()
    return [int(x) for x in re.split(r"[,;\s]+", raw) if x.strip().isdigit()]


def create_from_data(data: dict, force: bool = False) -> int | None:
    """Rend la newsletter et crée le brouillon Brevo. Renvoie l'id, ou None.

    Ne lève jamais : journalise et renvoie None (sans danger en cron).
    """
    api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    list_ids = _env_list_ids()
    missing = [k for k, v in {
        "BREVO_API_KEY": api_key, "BREVO_SENDER_NAME": sender_name,
        "BREVO_SENDER_EMAIL": sender_email, "BREVO_LIST_ID": list_ids,
    }.items() if not v]
    if missing:
        log.warning("Configuration Brevo incomplète (%s). Brouillon non créé.", ", ".join(missing))
        return None

    if not data.get("hero") and not data.get("items") and not force:
        log.info("Semaine sans contenu newsletter — brouillon Brevo ignoré (--force pour forcer).")
        return None

    # Logo : on privilégie l'URL hébergée en .env (les data-URI ne passent pas en email)
    data = dict(data)
    if os.getenv("BREVO_LOGO_URL"):
        data["logo_url"] = os.getenv("BREVO_LOGO_URL")
    if os.getenv("BREVO_PICTO_URL"):
        data["pictogram_url"] = os.getenv("BREVO_PICTO_URL")

    subject = data.get("subject") or f"Business Sabaudo — {data.get('week_label', '')}"
    html = variant_magazine(data)
    name = f"Business Sabaudo — {data.get('week_label', '')}".strip(" —")

    try:
        campaign_id = create_draft_campaign(
            api_key=api_key, name=name, subject=subject,
            sender_name=sender_name, sender_email=sender_email,
            list_ids=list_ids, html_content=html,
        )
    except BrevoError as exc:
        log.error("Création du brouillon Brevo échouée : %s", exc)
        return None

    log.info("Brouillon Brevo créé (id=%s) — objet : %s", campaign_id, subject)
    log.info("À relire/envoyer ici : %s", campaign_edit_url(campaign_id))
    log.info("⚠ Aucun envoi automatique — validation et envoi manuels par Franck.")
    return campaign_id


def _do_check(api_key: str) -> int:
    try:
        senders = list_senders(api_key)
        lists = list_contact_lists(api_key)
    except BrevoError as exc:
        log.error("Appel Brevo échoué : %s", exc)
        return 1
    log.info("=== Expéditeurs validés (BREVO_SENDER_EMAIL) ===")
    for s in senders:
        flag = "✅" if s.get("active") else "⏳ (à valider)"
        log.info("  %s — %s  %s", s.get("name", "?"), s.get("email", "?"), flag)
    if not senders:
        log.info("  (aucun expéditeur — à créer dans Brevo > Expéditeurs)")
    log.info("=== Listes de contacts (BREVO_LIST_ID) ===")
    for lst in lists:
        log.info("  id=%s — %s (%s abonnés)", lst.get("id"), lst.get("name", "?"), lst.get("totalSubscribers", "?"))
    if not lists:
        log.info("  (aucune liste — à créer dans Brevo > Contacts > Listes)")
    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Brouillon de campagne Brevo (gabarit magazine).")
    parser.add_argument("--week", help="Semaine ISO cible (AAAA-WNN).")
    parser.add_argument("--file", help="Chemin explicite d'un fichier de données .json.")
    parser.add_argument("--check", action="store_true", help="Lister expéditeurs et listes Brevo, puis quitter.")
    parser.add_argument("--force", action="store_true", help="Créer le brouillon même si la semaine est creuse.")
    args = parser.parse_args()

    if args.check:
        api_key = os.getenv("BREVO_API_KEY")
        if not api_key:
            log.error("BREVO_API_KEY absente du .env.")
            return 1
        return _do_check(api_key)

    path = find_data(args.week, args.file)
    if not path:
        log.error("Aucune donnée newsletter trouvée (week=%s, file=%s). Lancer synthesize.py d'abord.",
                  args.week, args.file)
        return 1
    log.info("Données source : %s", path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Fichier de données illisible (%s) : %s", path, exc)
        return 1

    campaign_id = create_from_data(data, force=args.force)
    return 0 if campaign_id is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
