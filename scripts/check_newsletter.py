#!/usr/bin/env python3
"""Boucle de vérification de la newsletter « Business Sabaudo ».

Contrôle le HTML EXACT envoyé à Brevo (02_Veille_traitee/Syntheses_hebdomadaires/
derniere_newsletter.html) et signale tout ce qui ne doit PAS partir :

  1. Tirets cadratins (— / –) dans le texte    → charte : interdits
  2. Images servies par un hôte proscrit        → CDN de presse / agrégateur
  3. Liens de traceur d'emailing (ESP)          → « on clique, on n'a rien »
  4. Liens pointant vers un journal (presse)    → radar : jamais de lien
  5. Balises <img> au src vide / cassé          → cartes sans visuel
  6. Coquilles de fusion (placeholders {{…}})   → variables non remplies

Sortie : rapport lisible + code retour 0 (tout bon) ou 1 (au moins un problème).
À lancer juste après synthesize/push_brevo, AVANT de valider le brouillon.

Usage :
    python scripts/check_newsletter.py
    python scripts/check_newsletter.py chemin/vers/un.html
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.sources import (  # noqa: E402
    is_blocked_image,
    is_press,
    load_blocked_image_domains,
    load_press_domains,
)

DEFAULT_HTML = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires" / "derniere_newsletter.html"

# Hôtes d'ESP / traceurs (mêmes que gmail_collect : un lien qui y mène n'est pas
# une vraie source).
_ESP_HOSTS = (
    "4dem.it", "mailchef", "list-manage.com", "mailchimp", "campaign-archive",
    "brevosend", "sendinblue", "sibautomation", "sendibm", "mailjet", "mlsend",
    "mailerlite", "sendgrid", "sarbacane", "sbc24", "hubspotemail", "hs-sites",
    "rs6.net", "constantcontact", "cmail", "createsend", "mailup", "sg-mail",
    "click.", "trk.", "/wbs", "/c/", "mkt.dynamics", "tracking",
)

_IMG_SRC_RE = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']*)["']""", re.I)
_A_HREF_RE = re.compile(r"""<a\b[^>]*\bhref=["']([^"']+)["']""", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
# Placeholders non remplis. On EXCLUT {{contact.*}} / {{params.*}} : ce sont des
# variables Brevo légitimes (personnalisation remplie à l'envoi). On vise les vrais
# trous de gabarit : {titre}, {{ une }}, %%FOO%%, %recipient…
_PLACEHOLDER_RE = re.compile(
    r"\{\{\s*(?!contact\.|params\.)[\w .]+\}\}|%recipient|%%[A-Z_]+%%|\{[a-z_]{3,}\}")


def _visible_text(html: str) -> str:
    """Texte visible (sans balises ni <style>/<head>) pour chercher les tirets."""
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<head\b.*?</head>", " ", html, flags=re.I | re.S)
    return _TAG_RE.sub(" ", html)


def _esp(host: str, url: str) -> bool:
    low = (host + " " + url).lower()
    return any(e in low for e in _ESP_HOSTS)


def check(html: str) -> list[tuple[str, str, list[str]]]:
    """Renvoie [(niveau, libellé, exemples), ...]. niveau ∈ {OK, ERREUR, ALERTE}."""
    results: list[tuple[str, str, list[str]]] = []
    blocked = load_blocked_image_domains()
    press = load_press_domains()

    # 1. Tirets cadratins dans le texte visible
    text = _visible_text(html)
    dashes = re.findall(r"[^\s]*[—–][^\s]*", text)
    results.append(
        ("ERREUR" if dashes else "OK", "Tirets cadratins (— / –)", dashes[:5])
    )

    # 2. Images proscrites + 5. images au src vide
    imgs = _IMG_SRC_RE.findall(html)
    bad_imgs = [u for u in imgs if u and is_blocked_image(u, blocked)]
    empty_imgs = [u for u in imgs if not u.strip()]
    results.append(
        ("ERREUR" if bad_imgs else "OK", "Images de presse / agrégateur proscrites", bad_imgs[:5])
    )
    results.append(
        ("ALERTE" if empty_imgs else "OK", "Balises <img> au src vide", empty_imgs[:5])
    )

    # 3. & 4. Liens : ESP/traceur et presse
    hrefs = [h for h in _A_HREF_RE.findall(html) if h.lower().startswith("http")]
    esp_links, press_links = [], []
    for h in hrefs:
        host = urlparse(h).netloc.lower().removeprefix("www.")
        if _esp(host, h):
            esp_links.append(h)
        elif host and is_press(host, press):
            press_links.append(h)
    results.append(
        ("ERREUR" if esp_links else "OK", "Liens de traceur d'emailing (ESP)", esp_links[:5])
    )
    results.append(
        ("ERREUR" if press_links else "OK", "Liens vers un journal (radar : interdit)", press_links[:5])
    )

    # 6. Placeholders de fusion non remplis
    holes = _PLACEHOLDER_RE.findall(html)
    results.append(
        ("ALERTE" if holes else "OK", "Variables de fusion non remplies", holes[:5])
    )

    return results


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HTML
    if not path.exists():
        print(f"✗ Fichier introuvable : {path}")
        print("  Lance d'abord : python scripts/synthesize.py --brevo --force")
        return 2
    html = path.read_text(encoding="utf-8")
    results = check(html)

    print(f"\n  Vérification : {path.name}  ({len(html):,} caractères)\n")
    n_err = n_warn = 0
    for level, label, examples in results:
        mark = {"OK": "✓", "ALERTE": "▲", "ERREUR": "✗"}[level]
        print(f"  {mark}  {label}")
        if level == "ERREUR":
            n_err += 1
        elif level == "ALERTE":
            n_warn += 1
        for ex in examples:
            print(f"       · {ex[:110]}")
    print()
    if n_err:
        print(f"  ✗ {n_err} problème(s) bloquant(s) — NE PAS envoyer en l'état.\n")
        return 1
    if n_warn:
        print(f"  ▲ {n_warn} point(s) à vérifier (non bloquant).\n")
        return 0
    print("  ✓ Tout est propre — la newsletter peut être validée.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
