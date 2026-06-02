#!/usr/bin/env python3
"""Crée un BROUILLON de campagne Brevo à partir d'une synthèse hebdomadaire.

- Lit la section « DRAFT NEWSLETTER » de la synthèse Markdown.
- La convertit en HTML et crée une campagne email en BROUILLON dans Brevo.
- ⚠ N'ENVOIE JAMAIS : Franck relit dans Brevo puis déclenche l'envoi lui-même.

Configuration (.env) :
    BREVO_API_KEY        clé API Brevo (Paramètres > SMTP & API > Clés API)
    BREVO_SENDER_NAME    nom de l'expéditeur (ex. Cultura Sabauda)
    BREVO_SENDER_EMAIL   email expéditeur VALIDÉ dans Brevo
    BREVO_LIST_ID        id(s) de la liste de destinataires (ex. 3 ou 3,4)

Usage :
    python scripts/push_brevo.py                 # dernière synthèse disponible
    python scripts/push_brevo.py --week 2026-W24
    python scripts/push_brevo.py --file 02_Veille_traitee/Syntheses_hebdomadaires/2026-W24.md
    python scripts/push_brevo.py --check         # liste expéditeurs + listes Brevo
    python scripts/push_brevo.py --force         # créer le brouillon même si semaine creuse
"""
from __future__ import annotations

import argparse
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
from utils.markdown_html import md_to_html_fragment, wrap_email_html  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SYNTH_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"

log = get_logger("push_brevo")

# Balises techniques émises par synthesize.py pour délimiter la newsletter.
_SUBJECT_RE = re.compile(r"<!--\s*BREVO:SUBJECT:(.*?)-->", re.S)
_START = "<!-- BREVO:START -->"
_END = "<!-- BREVO:END -->"
# Indices d'une semaine sans contenu publiable (synthèse « creuse »).
_EMPTY_HINTS = ("non publiable", "non exploitable", "aucun signal fort identifiable")


def find_synthesis(week: str | None, file_arg: str | None) -> Path | None:
    if file_arg:
        path = Path(file_arg)
        return path if path.is_file() else None
    if week:
        path = SYNTH_DIR / f"{week}.md"
        return path if path.is_file() else None
    if not SYNTH_DIR.exists():
        return None
    candidates = sorted(SYNTH_DIR.glob("*.md"))
    return candidates[-1] if candidates else None


def _clean_subject(raw: str) -> str:
    subject = re.sub(r"[*_`#>]", "", raw).strip().strip('"').strip("«»").strip()
    return subject[:120]


def _fallback_section(md_text: str) -> str | None:
    """Repli : section dont le titre contient « NEWSLETTER » jusqu'au prochain titre."""
    lines = md_text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if re.match(r"^#{1,6}\s", line) and "NEWSLETTER" in line.upper():
            start = idx + 1
            break
    if start is None:
        return None
    body = []
    for line in lines[start:]:
        if re.match(r"^#{1,2}\s", line):  # prochain titre de niveau 1/2 -> fin
            break
        body.append(line)
    text = "\n".join(body).strip()
    return text or None


def extract_newsletter(md_text: str, week: str) -> tuple[str, str]:
    """Renvoie (objet, corps Markdown) de la newsletter à partir de la synthèse."""
    subject = None
    m = _SUBJECT_RE.search(md_text)
    if m:
        subject = _clean_subject(m.group(1))

    if _START in md_text and _END in md_text:
        body = md_text.split(_START, 1)[1].split(_END, 1)[0].strip()
    else:
        body = _fallback_section(md_text)

    if not body:
        log.warning("Section newsletter introuvable — repli sur la synthèse complète.")
        body = md_text

    body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()

    if not subject:
        for line in body.splitlines():
            mo = re.match(r"^\**\s*objet\s*\**\s*[:\-]\s*(.+)$", line.strip(), re.I)
            if mo:
                subject = _clean_subject(mo.group(1))
                break
    if not subject:
        subject = f"Business Sabaudo — semaine {week}"
    return subject, body


def _looks_empty(body: str) -> bool:
    low = body.lower()
    return len(body) < 200 or any(hint in low for hint in _EMPTY_HINTS)


def _env_list_ids() -> list[int]:
    raw = os.getenv("BREVO_LIST_ID", "").strip()
    ids = [int(x) for x in re.split(r"[,;\s]+", raw) if x.strip().isdigit()]
    return ids


def push_file(md_path: Path, week: str | None = None, force: bool = False) -> int | None:
    """Crée le brouillon Brevo à partir d'un fichier de synthèse. Renvoie l'id ou None.

    Ne lève pas d'exception : journalise et renvoie None en cas de souci, pour
    rester sans danger quand on l'appelle depuis le cron (synthesize --brevo).
    """
    api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    list_ids = _env_list_ids()

    missing = [k for k, v in {
        "BREVO_API_KEY": api_key,
        "BREVO_SENDER_NAME": sender_name,
        "BREVO_SENDER_EMAIL": sender_email,
        "BREVO_LIST_ID": list_ids,
    }.items() if not v]
    if missing:
        log.warning("Configuration Brevo incomplète (%s). Brouillon non créé.", ", ".join(missing))
        return None

    week = week or md_path.stem
    md_text = md_path.read_text(encoding="utf-8")
    subject, body_md = extract_newsletter(md_text, week)

    if _looks_empty(body_md) and not force:
        log.info("Semaine %s sans newsletter publiable — brouillon Brevo ignoré (--force pour forcer).", week)
        return None

    fragment = md_to_html_fragment(body_md)
    html = wrap_email_html(fragment, subject)
    name = f"Business Sabaudo — {week}"

    try:
        campaign_id = create_draft_campaign(
            api_key=api_key,
            name=name,
            subject=subject,
            sender_name=sender_name,
            sender_email=sender_email,
            list_ids=list_ids,
            html_content=html,
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
    parser = argparse.ArgumentParser(description="Brouillon de campagne Brevo depuis une synthèse.")
    parser.add_argument("--week", help="Semaine ISO cible (AAAA-WNN).")
    parser.add_argument("--file", help="Chemin explicite d'un fichier de synthèse .md.")
    parser.add_argument("--check", action="store_true", help="Lister expéditeurs et listes Brevo, puis quitter.")
    parser.add_argument("--force", action="store_true", help="Créer le brouillon même si la semaine est creuse.")
    args = parser.parse_args()

    if args.check:
        api_key = os.getenv("BREVO_API_KEY")
        if not api_key:
            log.error("BREVO_API_KEY absente du .env.")
            return 1
        return _do_check(api_key)

    md_path = find_synthesis(args.week, args.file)
    if not md_path:
        log.error("Aucune synthèse trouvée (week=%s, file=%s).", args.week, args.file)
        return 1

    log.info("Synthèse source : %s", md_path)
    campaign_id = push_file(md_path, args.week, force=args.force)
    return 0 if campaign_id is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
