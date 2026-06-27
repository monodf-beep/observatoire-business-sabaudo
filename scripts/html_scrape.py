#!/usr/bin/env python3
"""Script 2bis — Scraping HTML générique des sources SANS flux RSS.

Beaucoup d'acteurs économiques (BNI, Confindustria, agences locales…) n'ont pas
de flux RSS mais publient une page d'actualité. Ce module va chercher ces pages,
en extrait les ARTICLES (titre + lien + image) par heuristique générique, et écrit
des enregistrements compatibles avec le reste du pipeline (mêmes JSON que rss_collect).

Sources : config/sources_a_scraper.txt (lignes de type « html »).
Sortie  : 01_Veille_brute/AAAA-MM-[territoire]/scrape_*.json

Heuristique (générique, donc imparfaite — c'est assumé) :
- on lit tous les liens <a> de la page et leur contenu (texte + <img> imbriquée) ;
- on regroupe par URL (un article = un lien interne au site) ;
- on garde ceux dont le texte ressemble à un TITRE (assez long, pas un menu) ;
- l'IMAGE est filtrée (pas de logo/blason/icône) et marquée « image_ok » : seules
  ces vraies photos sont autorisées dans la newsletter (cf. synthesize.py).

Usage :
    python scripts/html_scrape.py                 # toutes les sources « html »
    python scripts/html_scrape.py --debug         # affiche sans écrire
    python scripts/html_scrape.py --cap 20        # max d'articles par site
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402
from utils.sources import is_blocked_image, load_blocked_image_domains  # noqa: E402
from utils.textutils import clean_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sources_a_scraper.txt"
OUTPUT_DIR = ROOT / "01_Veille_brute"

log = get_logger("html_scrape")

_UA = ("Mozilla/5.0 (compatible; ObservatoireBusinessSabaudo/1.0; +https://culturasabauda.eu)")

# Chemins à écarter (navigation, comptes, taxonomies, langues, mentions légales…).
_SKIP_PATH = (
    "/tag/", "/tags/", "/category/", "/categorie/", "/categoria/", "/author/",
    "/page/", "/pagina/", "/wp-login", "/wp-admin", "/feed", "/login", "/signin",
    "/account", "/cart", "/panier", "/search", "/recherche", "/privacy", "/cookie",
    "/mentions", "/cgu", "/cgv", "/contact", "/newsletter", "/rss", "/sitemap",
    "/it/", "/en/", "/de/", "/es/",  # variantes de langue (on garde la version par défaut)
)
# Textes d'ancre « non-titre » (menus, boutons).
_GENERIC = {
    "accueil", "home", "menu", "contact", "actualités", "actualites", "news",
    "lire la suite", "leggi", "leggi tutto", "read more", "scopri", "scopri di piu",
    "en savoir plus", "voir plus", "tous les articles", "suivant", "précédent",
    "precedent", "next", "previous", "newsletter", "s'inscrire", "se connecter",
    "connexion", "accedi", "login", "cookie", "mentions légales", "plan du site",
}
# Indices de logo/visuel non-éditorial dans une URL d'image.
_IMG_BAD = ("logo", "sprite", "icon", "favicon", "placeholder", "default", "avatar",
            "blason", "stemma", "flag", "/badge", "banner", "header", "footer", "/ui/")


class _Anchors(HTMLParser):
    """Extrait [(href, texte, img, alt)] de tous les <a> (gère <img> imbriquée)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[dict] = []
        self.out: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        d = dict(attrs)
        if tag == "a":
            self._stack.append({"href": d.get("href", "") or "", "text": [], "img": "", "alt": ""})
        elif tag == "img" and self._stack:
            cur = self._stack[-1]
            if not cur["img"]:
                cur["img"] = (d.get("src") or d.get("data-src") or d.get("data-lazy-src")
                              or d.get("data-original") or "")
                cur["alt"] = d.get("alt", "") or ""

    def handle_data(self, data: str) -> None:
        if self._stack and data.strip():
            self._stack[-1]["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._stack:
            a = self._stack.pop()
            self.out.append(a)


def _regdomain(host: str) -> str:
    """Domaine « enregistrable » approximatif (2 derniers labels) pour comparer."""
    host = (host or "").lower().split(":")[0]
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _fetch(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            return ""
        raw = r.read(2_000_000)  # cap 2 Mo
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    if m:
        charset = m.group(1)
    return raw.decode(charset, errors="replace")


def _good_image(src: str, page_url: str, blocked: set[str]) -> str:
    """URL d'image éditoriale (vraie photo) ou '' si logo/icône/proscrite."""
    if not src:
        return ""
    src = urljoin(page_url, src.strip())
    low = src.lower()
    if low.startswith("data:") or low.endswith(".svg"):
        return ""
    if any(b in low for b in _IMG_BAD):
        return ""
    if not low.startswith("http"):
        return ""
    if is_blocked_image(src, blocked):
        return ""
    return src


# Indices qu'une URL pointe vers un ARTICLE daté (et non une page de menu/service).
_NEWS_HINTS = ("/news", "/post/", "/actualit", "/article", "/press", "/comunicat",
               "/notiz", "/blog/", "/evenement", "/event", "/2024/", "/2025/", "/2026/")


def _is_article_link(href: str, page_host: str) -> bool:
    p = urlparse(href)
    if p.scheme not in ("http", "https"):
        return False
    if _regdomain(p.netloc) != _regdomain(page_host):
        return False  # lien externe → pas un article du site
    path = (p.path or "").lower()
    if path in ("", "/") or any(s in path for s in _SKIP_PATH):
        return False
    # Article = chemin « actu » (date, /news/, /post/…) OU slug long (≥ 4 tirets).
    return any(h in path for h in _NEWS_HINTS) or path.count("-") >= 4


def _title_ok(text: str) -> bool:
    t = clean_text(text).strip()
    if len(t) < 30 or len(t) > 200:
        return False
    if t.lower() in _GENERIC:
        return False
    # Vrai titre éditorial : au moins 5 mots (élimine les libellés de menu/service).
    return len(t.split()) >= 5


def scrape_page(url: str, territory: str, *, cap: int, timeout: int,
                blocked: set[str]) -> list[dict]:
    """Renvoie une liste d'enregistrements (titre+lien+image) extraits de la page."""
    try:
        html = _fetch(url, timeout)
    except Exception as exc:
        log.warning("Page illisible %s : %s", url, exc)
        return []
    if not html:
        return []

    parser = _Anchors()
    try:
        parser.feed(html)
    except Exception as exc:
        log.warning("Parsing impossible %s : %s", url, exc)
        return []

    page_host = urlparse(url).netloc
    # Regroupe par URL d'article : on fusionne titre (meilleur texte) + image.
    by_url: dict[str, dict] = {}
    for a in parser.out:
        href = urljoin(url, (a["href"] or "").split("#")[0].strip())
        if not _is_article_link(href, page_host):
            continue
        text = clean_text(" ".join(a["text"]))
        slot = by_url.setdefault(href, {"title": "", "image": ""})
        # Titre : UNIQUEMENT le texte du lien (pas l'alt d'image, source de bruit).
        if _title_ok(text) and len(text) > len(slot["title"]):
            slot["title"] = text
        if not slot["image"]:
            img = _good_image(a["img"], url, blocked)
            if img:
                slot["image"] = img

    site = urlparse(url).netloc.replace("www.", "")
    now = datetime.now(timezone.utc).isoformat()
    records = []
    seen_titles: set[str] = set()
    for href, slot in by_url.items():
        if not slot["title"]:
            continue
        tkey = slot["title"].lower()
        if tkey in seen_titles:
            continue
        seen_titles.add(tkey)
        records.append({
            "source": "scrape",
            "feed_url": url,
            "territoire": territory,
            "date": now,            # pas de date par article en HTML → date de collecte
            "date_estimee": True,
            "title": slot["title"],
            "link": href,
            "body": "",
            "image": slot["image"],
            "image_ok": bool(slot["image"]),  # vraie photo vérifiée → utilisable en newsletter
            "feed_title": site,
            "collected_at": now,
        })
        if len(records) >= cap:
            break
    return records


def _load_html_sources() -> list[tuple[str, str, str]]:
    """[(nom, url, territoire), ...] pour les lignes de type « html »."""
    if not CONFIG.exists():
        log.error("Fichier introuvable : %s", CONFIG)
        return []
    out = []
    for raw in CONFIG.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ";" not in line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) >= 4 and parts[3].lower() == "html":
            out.append((parts[0], parts[1], parts[2]))
    return out


def _url_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _write(record: dict) -> bool:
    try:
        dt = datetime.fromisoformat(record["date"])
    except (ValueError, KeyError):
        dt = datetime.now(timezone.utc)
    folder = OUTPUT_DIR / f"{dt:%Y-%m}-{record['territoire']}"
    out = folder / f"scrape_{_url_id(record['link'])}.json"
    if out.exists():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Scraping HTML des sources sans RSS.")
    parser.add_argument("--debug", action="store_true", help="Affiche sans rien écrire.")
    parser.add_argument("--cap", type=int, default=15, help="Max d'articles par site (15).")
    args = parser.parse_args()

    socket.setdefaulttimeout(20)
    blocked = load_blocked_image_domains()
    sources = _load_html_sources()
    log.info("=== Scraping HTML : %d source(s) de type « html » ===", len(sources))

    total_new = total_found = 0
    for name, url, terr in sources:
        recs = scrape_page(url, terr, cap=args.cap, timeout=20, blocked=blocked)
        total_found += len(recs)
        n_img = sum(1 for r in recs if r.get("image_ok"))
        if args.debug:
            print(f"\n=== {name} [{terr}] — {len(recs)} article(s), {n_img} avec photo ===")
            for r in recs:
                print(f"   {'📷' if r['image_ok'] else '  '} {r['title'][:70]}")
                print(f"      {r['link'][:90]}")
            continue
        new = sum(1 for r in recs if _write(r))
        total_new += new
        log.info("[%s] %s → %d article(s), %d nouveau(x), %d photo(s)", terr, name, len(recs), new, n_img)

    if args.debug:
        log.info("=== (debug) %d article(s) trouvé(s), rien écrit ===", total_found)
    else:
        log.info("=== Fin scraping HTML : %d nouveau(x) sur %d trouvé(s) ===", total_new, total_found)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
