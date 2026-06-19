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

import argparse
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
from urllib.parse import urlparse

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
# Liens utilitaires / réseaux sociaux à ÉCARTER d'office.
_LINK_SKIP = (
    "unsubscribe", "desabon", "désabon", "optout", "opt-out", "/preferences",
    "gestion-abonnement", "list-manage", "view-in-browser", "/webversion",
    "webview", "mirror", "/vb/", "manage/", "profile-center",
    "facebook.com", "twitter.com", "x.com/", "linkedin.com", "instagram.com",
    "youtube.com", "youtu.be", "tiktok.com", "wa.me", "whatsapp", "t.me/",
    "mailto:", "tel:", "javascript:", "google.com/maps",
)
# Hôtes d'ESP / traceurs d'emailing : un lien qui RESTE sur l'un d'eux n'est pas une
# vraie source externe (c'est un tracker, ou la version web de l'email lui-même).
_ESP_HOSTS = (
    "4dem.it", "mailchef", "list-manage.com", "mailchimp", "campaign-archive",
    "brevosend", "sendinblue", "sibautomation", "sendibm", "mailjet", "mlsend",
    "mailerlite", "sendgrid", "sarbacane", "sbc24", "hubspotemail", "hs-sites",
    "rs6.net", "constantcontact", "cmail", "createsend", "mailup", "sg-mail",
)
# Ancre indiquant la « version web » de la newsletter (« ouvrir dans le navigateur »).
_WEB_VERSION_RE = re.compile(
    r"navigateur|browser|en ?ligne|version ?web|vedi.*(online|browser)|"
    r"visualizza|view.*browser|online version|leggi.*online", re.I)


def _esp_host(host: str) -> bool:
    host = (host or "").lower()
    return any(e in host for e in _ESP_HOSTS)


def _resolve_url(url: str, timeout: int = 5) -> str:
    """Suit les redirections jusqu'à l'URL finale réelle. '' si échec/inaccessible."""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl() or ""
    except Exception:
        return ""


def _anchors(payload: dict) -> list[tuple[str, str]]:
    """(href, texte d'ancre) de tous les liens HTTP de l'email HTML."""
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
    out: list[tuple[str, str]] = []
    for m in _A_RE.finditer("\n".join(htmls)):
        href = m.group(1).strip()
        if href.lower().startswith("http"):
            text = clean_text(_TAG_RE.sub(" ", m.group(2))).strip()
            out.append((href, text))
    return out


def extract_web_version(payload: dict) -> str:
    """Lien « ouvrir dans le navigateur » : permalien web de la newsletter."""
    for href, text in _anchors(payload):
        if _WEB_VERSION_RE.search(text):
            return href
    return ""


def extract_links(payload: dict, *, resolve: bool = True, cap: int = 40) -> list[dict]:
    """Liens de CONTENU (les SOURCES citées), traceurs « déballés » vers l'URL réelle.

    On suit la redirection des liens enveloppés par un routeur d'emailing (ESP) pour
    retrouver l'article réel. Un lien qui ne répond pas, ou qui reste sur un domaine
    d'ESP après résolution, est écarté : c'est ce qui évite le « on clique, on n'a
    rien ». Déduplique sur l'URL finale.
    """
    out: list[dict] = []
    seen: set[str] = set()
    resolved = 0
    for href, text in _anchors(payload):
        low = href.lower()
        if any(s in low for s in _LINK_SKIP) or _WEB_VERSION_RE.search(text):
            continue
        final = href
        host = urlparse(href).netloc.lower().removeprefix("www.")
        if _esp_host(host):
            if not resolve or resolved >= cap:
                continue
            resolved += 1
            real = _resolve_url(href)
            if not real:
                continue
            final = real
            host = urlparse(final).netloc.lower().removeprefix("www.")
            if _esp_host(host):
                continue  # toujours chez l'ESP → pas une vraie source externe
        norm = final.lower().split("#")[0].rstrip("/")
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"url": final, "text": text[:160]})
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
        "web_version": extract_web_version(payload),
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
    parser = argparse.ArgumentParser(description="Collecte Gmail des newsletters de veille.")
    parser.add_argument("--force", action="store_true",
                        help="Re-traiter les emails déjà collectés (ré-applique l'extraction "
                             "et la résolution des liens sur les newsletters existantes).")
    parser.add_argument("--lookback", type=int, default=None,
                        help="Fenêtre de collecte en jours (défaut : GMAIL_LOOKBACK_DAYS ou 8).")
    args = parser.parse_args()
    log.info("=== Démarrage collecte Gmail%s ===", " (--force)" if args.force else "")

    whitelist = load_whitelist()
    if not whitelist:
        log.error("Whitelist vide : rien à collecter. Arrêt.")
        return 1

    try:
        service = build_service()
    except (FileNotFoundError, SystemExit) as exc:
        log.error("Authentification impossible : %s", exc)
        return 1

    lookback = args.lookback if args.lookback is not None else int(os.getenv("GMAIL_LOOKBACK_DAYS", "8"))
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
        existed = out.exists()
        if existed and not args.force:
            dup_count += 1
            continue
        try:
            write_json(out, record)
            new_count += 1
            log.info("[%s]%s %s", territory, " (maj)" if existed else "",
                     record["title"][:80] or "(sans objet)")
        except OSError as exc:
            err_count += 1
            log.error("Écriture impossible (%s) : %s", out, exc)

    log.info(
        "=== Fin collecte Gmail : %d traité(s)/maj, %d doublon(s) ignoré(s), %d erreur(s) ===",
        new_count, dup_count, err_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
