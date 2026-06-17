#!/usr/bin/env python3
"""Script 1 — Collecte des emails de veille depuis Gmail.

- Authentification Gmail API OAuth2 (config/credentials.json)
- Whitelist d'expéditeurs (config/whitelist_gmail.txt) avec territoire associé
- Extraction : objet, date, expéditeur, corps texte nettoyé
- Sortie : un fichier JSON par email dans 01_Veille_brute/AAAA-MM-[territoire]/
- Déduplication par message-id (le fichier de sortie est nommé d'après le message-id)

Scheduler prévu : cron du lundi 7h (voir crontab.txt).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402
from utils.textutils import clean_text, html_to_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "01_Veille_brute"
WHITELIST_FILE = CONFIG_DIR / "whitelist_gmail.txt"
TOKEN_PATH = CONFIG_DIR / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

log = get_logger("gmail_collect")


# --------------------------------------------------------------------------- #
# Whitelist
# --------------------------------------------------------------------------- #
def load_whitelist() -> list[tuple[str, str]]:
    """Charge [(motif, territoire), ...] depuis le fichier whitelist."""
    if not WHITELIST_FILE.exists():
        log.error("Whitelist introuvable : %s", WHITELIST_FILE)
        return []
    entries: list[tuple[str, str]] = []
    for lineno, raw in enumerate(WHITELIST_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ";" not in line:
            log.warning("Ligne %d ignorée (format motif;territoire attendu) : %r", lineno, line)
            continue
        pattern, territory = (part.strip() for part in line.split(";", 1))
        if pattern and territory:
            entries.append((pattern.lower().lstrip("@"), territory))
    log.info("Whitelist chargée : %d expéditeur(s)", len(entries))
    return entries


def match_territory(sender: str, whitelist: list[tuple[str, str]]) -> str:
    """Associe un expéditeur à un territoire via la whitelist."""
    sender = (sender or "").lower()
    for pattern, territory in whitelist:
        if pattern in sender:
            return territory
    return "Indetermine"


# --------------------------------------------------------------------------- #
# Authentification & service Gmail
# --------------------------------------------------------------------------- #
def build_service(manual: bool = False):
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SystemExit(
            "Dépendances Google manquantes. Exécuter : pip install -r requirements.txt"
        ) from exc

    from utils.google_auth import load_credentials

    cred_file = Path(os.getenv("GMAIL_CREDENTIALS_PATH", CONFIG_DIR / "credentials.json"))
    creds = load_credentials(SCOPES, TOKEN_PATH, cred_file, manual=manual)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# --------------------------------------------------------------------------- #
# Requête & parsing
# --------------------------------------------------------------------------- #
def build_query(whitelist: list[tuple[str, str]], lookback_days: int) -> str:
    senders = sorted({pattern for pattern, _ in whitelist})
    from_clause = " OR ".join(f"from:{s}" for s in senders)
    return f"({from_clause}) newer_than:{lookback_days}d"


def list_messages(service, query: str) -> list[dict]:
    """Liste tous les messages correspondant à la requête (avec pagination)."""
    from googleapiclient.errors import HttpError

    messages: list[dict] = []
    page_token = None
    try:
        while True:
            resp = (
                service.users()
                .messages()
                # includeSpamTrash : les expéditeurs sont whitelistés (donc de
                # confiance) ; on récupère leurs emails même si Gmail les a classés
                # en spam (cas vu : une confirmation Camera di Torino tombée en spam).
                .list(userId="me", q=query, pageToken=page_token, maxResults=100,
                      includeSpamTrash=True)
                .execute()
            )
            messages.extend(resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except HttpError as exc:
        log.error("Erreur Gmail lors du listing (quota ?) : %s", exc)
    log.info("%d message(s) correspondant à la whitelist", len(messages))
    return messages


def _get_with_retry(service, message_id: str, attempts: int = 3):
    """Récupère un message complet avec backoff sur quota/erreurs transitoires."""
    from googleapiclient.errors import HttpError

    for attempt in range(1, attempts + 1):
        try:
            return (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status in (403, 429, 500, 503) and attempt < attempts:
                wait = 2 ** attempt
                log.warning("Quota/erreur Gmail (%s) sur %s, retry dans %ds", status, message_id, wait)
                time.sleep(wait)
                continue
            log.error("Échec récupération message %s : %s", message_id, exc)
            return None
    return None


def _decode_part(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_body(payload: dict) -> str:
    """Extrait le corps texte (priorité text/plain, repli text/html)."""
    plain: list[str] = []
    html: list[str] = []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")
        if part.get("parts"):
            for sub in part["parts"]:
                walk(sub)
        elif data:
            if mime == "text/plain":
                plain.append(_decode_part(data))
            elif mime == "text/html":
                html.append(_decode_part(data))

    walk(payload)
    if plain:
        return clean_text("\n".join(plain))
    if html:
        return html_to_text("\n".join(html))
    return ""


_IMG_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["'][^>]*>""", re.I)
# Indices d'images de traçage / décoratives à écarter.
_IMG_SKIP = ("pixel", "track", "beacon", "spacer", "/o/", "open.", "1x1", "transparent")


def extract_image(payload: dict) -> str:
    """1ʳᵉ image http « réelle » de l'email HTML (hors pixels de traçage)."""
    htmls: list[str] = []

    def walk(part: dict) -> None:
        body = part.get("body", {})
        data = body.get("data")
        if part.get("parts"):
            for sub in part["parts"]:
                walk(sub)
        elif data and part.get("mimeType") == "text/html":
            htmls.append(_decode_part(data))

    walk(payload)
    for match in _IMG_RE.finditer("\n".join(htmls)):
        tag = match.group(0).lower()
        src = match.group(1)
        if not src.lower().startswith("http"):
            continue
        if any(t in tag for t in _IMG_SKIP):
            continue
        if re.search(r'(width|height)=["\']?1\b', tag):
            continue
        return src
    return ""


def _header(headers: list[dict], name: str) -> str:
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


_A_RE = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*?>(.*?)</a>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
# Fragments d'URL à ÉCARTER : traceurs/ESP, réseaux sociaux, liens utilitaires.
# Une newsletter institutionnelle cite des SOURCES (annonces, appels, dossiers) :
# ce sont elles qu'on veut garder ; le reste est du bruit d'emailing.
_LINK_SKIP = (
    "unsubscribe", "desabon", "désabon", "optout", "opt-out", "/preferences",
    "gestion-abonnement", "list-manage", "view-in-browser", "/webversion",
    "webview", "mirror", "/vb/", "manage/", "profile-center",
    "facebook.com", "twitter.com", "x.com/", "linkedin.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "wa.me", "whatsapp", "t.me/",
    "mailto:", "tel:", "javascript:", "google.com/maps",
)


def extract_links(payload: dict) -> list[dict]:
    """Liens de CONTENU d'une newsletter HTML — les « sources » qu'elle cite.

    Filtre les liens utilitaires (désabonnement, voir en ligne), les traceurs et
    les réseaux sociaux ; déduplique. C'est la matière qui, en aval, devient
    autant d'items de veille pointant vers la source officielle.
    """
    htmls: list[str] = []

    def walk(part: dict) -> None:
        body = part.get("body", {})
        data = body.get("data")
        if part.get("parts"):
            for sub in part["parts"]:
                walk(sub)
        elif data and part.get("mimeType") == "text/html":
            htmls.append(_decode_part(data))

    walk(payload)
    out: list[dict] = []
    seen: set[str] = set()
    for m in _A_RE.finditer("\n".join(htmls)):
        url = m.group(1).strip()
        low = url.lower()
        if not low.startswith("http"):
            continue
        if any(s in low for s in _LINK_SKIP):
            continue
        norm = low.split("#")[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        text = clean_text(_TAG_RE.sub(" ", m.group(2))).strip()
        out.append({"url": url, "text": text[:160]})
    return out


def parse_message(msg: dict) -> dict:
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    subject = _header(headers, "Subject").strip()
    sender = _header(headers, "From").strip()
    message_id = _header(headers, "Message-ID").strip()

    # Date : on privilégie internalDate (epoch ms, fiable), repli sur l'en-tête Date
    date_iso = ""
    internal = msg.get("internalDate")
    if internal:
        try:
            date_iso = datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc).isoformat()
        except (ValueError, OverflowError):
            date_iso = ""
    if not date_iso:
        raw_date = _header(headers, "Date")
        try:
            date_iso = parsedate_to_datetime(raw_date).isoformat()
        except (TypeError, ValueError):
            date_iso = datetime.now(timezone.utc).isoformat()

    return {
        "source": "gmail",
        "message_id": message_id or msg.get("id", ""),
        "gmail_id": msg.get("id", ""),
        "date": date_iso,
        "from": sender,
        "title": subject,
        "body": extract_body(payload),
        "image": extract_image(payload),
        "links": extract_links(payload),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# Sortie / déduplication
# --------------------------------------------------------------------------- #
def _safe_id(message_id: str) -> str:
    """Identifiant de fichier stable et sûr dérivé du message-id."""
    digest = hashlib.sha1(message_id.encode("utf-8")).hexdigest()[:16]
    return digest


def output_path(record: dict, territory: str) -> Path:
    try:
        dt = datetime.fromisoformat(record["date"])
    except (ValueError, KeyError):
        dt = datetime.now(timezone.utc)
    folder = OUTPUT_DIR / f"{dt:%Y-%m}-{territory}"
    return folder / f"gmail_{_safe_id(record['message_id'])}.json"


def write_json(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    load_dotenv(ROOT / ".env")
    log.info("=== Démarrage collecte Gmail ===")

    whitelist = load_whitelist()
    if not whitelist:
        log.error("Whitelist vide : rien à collecter. Arrêt.")
        return 1

    try:
        service = build_service()
    except (FileNotFoundError, SystemExit) as exc:
        log.error("Authentification impossible : %s", exc)
        return 1

    lookback = int(os.getenv("GMAIL_LOOKBACK_DAYS", "8"))
    query = build_query(whitelist, lookback)
    log.info("Requête Gmail : %s", query)

    messages = list_messages(service, query)
    new_count = dup_count = err_count = 0

    for meta in messages:
        msg = _get_with_retry(service, meta["id"])
        if msg is None:
            err_count += 1
            continue
        record = parse_message(msg)
        territory = match_territory(record["from"], whitelist)
        out = output_path(record, territory)
        if out.exists():
            dup_count += 1
            continue
        try:
            write_json(out, record)
            new_count += 1
            log.info("[%s] %s", territory, record["title"][:80] or "(sans objet)")
        except OSError as exc:
            err_count += 1
            log.error("Écriture impossible (%s) : %s", out, exc)

    log.info(
        "=== Fin collecte Gmail : %d nouveau(x), %d doublon(s), %d erreur(s) ===",
        new_count, dup_count, err_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
