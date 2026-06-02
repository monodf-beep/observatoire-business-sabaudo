#!/usr/bin/env python3
"""Script 2 — Collecte de flux RSS/Atom.

- Liste de flux en entrée : config/rss_feeds.txt (url;territoire)
- Collecte quotidienne, déduplication par URL d'article
- Sortie : un fichier JSON par article dans 01_Veille_brute/AAAA-MM-[territoire]/
- Gestion d'erreurs : flux mort, timeout, flux mal formé

Scheduler prévu : cron quotidien 8h (voir crontab.txt).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import mktime

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402
from utils.textutils import clean_text, html_to_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "01_Veille_brute"
FEEDS_FILE = CONFIG_DIR / "rss_feeds.txt"

log = get_logger("rss_collect")


def load_feeds() -> list[tuple[str, str]]:
    """Charge [(url, territoire), ...] depuis le fichier de flux."""
    if not FEEDS_FILE.exists():
        log.error("Fichier de flux introuvable : %s", FEEDS_FILE)
        return []
    feeds: list[tuple[str, str]] = []
    for lineno, raw in enumerate(FEEDS_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ";" not in line:
            log.warning("Ligne %d ignorée (format url;territoire attendu) : %r", lineno, line)
            continue
        url, territory = (part.strip() for part in line.split(";", 1))
        if url and territory:
            feeds.append((url, territory))
    log.info("%d flux RSS à collecter", len(feeds))
    return feeds


def _entry_date(entry) -> str:
    """Date ISO de l'article (published, sinon updated, sinon maintenant)."""
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            try:
                return datetime.fromtimestamp(mktime(struct), tz=timezone.utc).isoformat()
            except (ValueError, OverflowError, TypeError):
                continue
    return datetime.now(timezone.utc).isoformat()


def _entry_summary(entry) -> str:
    raw = entry.get("summary", "")
    if not raw and entry.get("content"):
        raw = entry["content"][0].get("value", "")
    return html_to_text(raw) if raw else ""


_IMG_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)


def _entry_image(entry) -> str:
    """URL d'une image illustrant l'article (media, enclosure, ou 1er <img>)."""
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key)
        if media and media[0].get("url"):
            return media[0]["url"]
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            if link.get("href"):
                return link["href"]
    html = ""
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
    html = html or entry.get("summary", "")
    match = _IMG_RE.search(html)
    return match.group(1) if match else ""


def _url_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def output_path(record: dict) -> Path:
    try:
        dt = datetime.fromisoformat(record["date"])
    except (ValueError, KeyError):
        dt = datetime.now(timezone.utc)
    folder = OUTPUT_DIR / f"{dt:%Y-%m}-{record['territoire']}"
    return folder / f"rss_{_url_id(record['link'])}.json"


def collect_feed(url: str, territory: str, feed_lib) -> tuple[int, int]:
    """Collecte un flux. Retourne (nouveaux, doublons)."""
    new = dup = 0
    try:
        parsed = feed_lib.parse(url)
    except Exception as exc:  # parse ne lève quasi jamais, mais par sécurité
        log.error("Flux illisible %s : %s", url, exc)
        return 0, 0

    if getattr(parsed, "bozo", 0) and not parsed.entries:
        reason = getattr(parsed, "bozo_exception", "inconnue")
        log.error("Flux mort ou mal formé %s : %s", url, reason)
        return 0, 0

    for entry in parsed.entries:
        link = entry.get("link") or entry.get("id")
        if not link:
            continue
        record = {
            "source": "rss",
            "feed_url": url,
            "territoire": territory,
            "date": _entry_date(entry),
            "title": clean_text(entry.get("title", "")),
            "link": link,
            "body": _entry_summary(entry),
            "image": _entry_image(entry),
            "feed_title": clean_text(getattr(parsed.feed, "title", "")),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        out = output_path(record)
        if out.exists():
            dup += 1
            continue
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            new += 1
        except OSError as exc:
            log.error("Écriture impossible (%s) : %s", out, exc)

    log.info("[%s] %s → %d nouveau(x), %d doublon(s)", territory, url, new, dup)
    return new, dup


def main() -> int:
    load_dotenv(ROOT / ".env")
    log.info("=== Démarrage collecte RSS ===")

    try:
        import feedparser
    except ImportError as exc:
        raise SystemExit(
            "Dépendance feedparser manquante. Exécuter : pip install -r requirements.txt"
        ) from exc

    # Timeout réseau global (gère les flux qui ne répondent pas)
    timeout = int(os.getenv("RSS_TIMEOUT", "30"))
    socket.setdefaulttimeout(timeout)

    feeds = load_feeds()
    if not feeds:
        log.error("Aucun flux à collecter. Arrêt.")
        return 1

    total_new = total_dup = 0
    for url, territory in feeds:
        new, dup = collect_feed(url, territory, feedparser)
        total_new += new
        total_dup += dup

    log.info("=== Fin collecte RSS : %d nouveau(x), %d doublon(s) ===", total_new, total_dup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
