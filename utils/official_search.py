"""Retrouve l'URL de l'article/communiqué OFFICIEL sur le site d'un acteur.

Quand une brève vient de la presse (mode radar), on ne lie pas le journal. Si on
connaît le DOMAINE officiel de l'acteur (config/official_links.txt), ce module
demande à Claude de retrouver, via l'outil de recherche web restreint à ce
domaine, la page précise qui traite du sujet. L'URL renvoyée provient des
résultats de recherche réels (jamais devinée) ; '' si rien de pertinent.

Opt-in : ne s'active que si OFFICIAL_LINK_SEARCH=1 (voir is_enabled()). Conçu pour
être tolérant aux pannes : toute erreur réseau/API/SDK renvoie '' (la brève reste
alors sans lien, sans casser la synthèse).
"""
from __future__ import annotations

import os
import re
from urllib.parse import urljoin, urlparse

from utils.logger import get_logger

log = get_logger("official_search")

_WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}

# Métadonnées d'image sociale (og:image / twitter:image), ordre/attributs variables.
_OG_IMAGE_PATTERNS = (
    re.compile(r'<meta[^>]+property=["\']og:image(?::secure_url|:url)?["\'][^>]+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url|:url)?["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']', re.I),
)


def is_enabled() -> bool:
    """Vrai si la recherche de liens officiels est explicitement activée."""
    return os.getenv("OFFICIAL_LINK_SEARCH", "").strip() in {"1", "true", "True", "yes"}


def _normalize_url(url: str) -> str:
    """Nettoie une URL renvoyée par la recherche : espaces parasites (y compris
    insécables encodés %C2%A0) qui se glissent dans les slugs et cassent le lien."""
    url = (url or "").strip()
    # Espace insécable (brut ou encodé) collé dans un slug → on le retire.
    url = url.replace("%C2%A0", "").replace("%c2%a0", "").replace("\xa0", "")
    return url.replace(" ", "%20")


def fetch_page(url: str, timeout: int = 10, max_bytes: int = 200_000) -> tuple[str, str, str]:
    """Récupère une page et indique si elle EXISTE vraiment.

    Renvoie (url_finale, html, statut) où statut vaut :
    - "ok"       : page accessible (HTML disponible pour en extraire l'og:image) ;
    - "notfound" : page inexistante (HTTP 404/410) → le lien doit être ABANDONNÉ ;
    - "error"    : incertain (blocage temporaire, timeout, 403…) → on conserve le
                   lien (souvent valide pour un humain) mais sans og:image.
    """
    import urllib.error
    import urllib.request

    url = _normalize_url(url)
    if not url:
        return "", "", "notfound"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (BusinessSabaudo/1.0; veille éco)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read(max_bytes).decode("utf-8", errors="ignore")
            return resp.geturl() or url, html, "ok"
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            log.warning("Lien officiel inexistant (HTTP %s) : %s", exc.code, url)
            return url, "", "notfound"
        log.warning("Lien officiel : HTTP %s (%s) — lien conservé sans image", exc.code, url)
        return url, "", "error"
    except Exception as exc:  # réseau, TLS, timeout, décodage…
        log.warning("Lien officiel injoignable (%s) : %s — lien conservé sans image", url, exc)
        return url, "", "error"


def og_image_from_html(html: str, base_url: str) -> str:
    """Extrait l'URL d'image sociale (og:image / twitter:image) d'un HTML, ou ''."""
    for pattern in _OG_IMAGE_PATTERNS:
        match = pattern.search(html or "")
        if match and match.group(1).strip():
            img = urljoin(base_url, match.group(1).strip())
            if img.lower().startswith(("http://", "https://")):
                return img
    return ""



def _urls_on_domain(blocks, domain: str) -> list[str]:
    """Extrait toutes les URLs (résultats web + citations) hébergées sur `domain`."""
    urls: list[str] = []

    def keep(url: str) -> None:
        if not url:
            return
        host = (urlparse(url).netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host == domain or host.endswith("." + domain):
            urls.append(url)

    for block in blocks:
        btype = getattr(block, "type", "")
        # Résultats de recherche web (server tool result)
        if btype == "web_search_tool_result":
            for res in getattr(block, "content", None) or []:
                keep(getattr(res, "url", "") or (res.get("url", "") if isinstance(res, dict) else ""))
        # Citations attachées au texte de la réponse
        if btype == "text":
            for cit in getattr(block, "citations", None) or []:
                keep(getattr(cit, "url", "") or (cit.get("url", "") if isinstance(cit, dict) else ""))
    return urls


def _text_of(blocks) -> str:
    return " ".join(
        getattr(b, "text", "") for b in blocks if getattr(b, "type", "") == "text"
    )


def find_article_url(actor: str, title: str, summary: str, domain: str,
                     model: str, api_key: str | None = None) -> str:
    """Retrouve l'URL de l'article officiel sur `domain` traitant du sujet, ou ''."""
    if not domain or not title:
        return ""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ""
    try:
        import anthropic
    except ImportError:
        return ""

    tool = {**_WEB_SEARCH_TOOL, "allowed_domains": [domain]}
    prompt = (
        f"Sur le site officiel {domain}, trouve LA page (article, actualité ou "
        f"communiqué de presse) qui traite précisément de ce sujet :\n\n"
        f"Acteur : {actor or '—'}\n"
        f"Sujet : {title}\n"
        f"Détail : {summary or '—'}\n\n"
        f"Réponds UNIQUEMENT par l'URL exacte de cette page (sur {domain}). "
        f"Si aucune page pertinente n'existe sur ce site, réponds exactement : AUCUN.\n"
        f"Ne renvoie jamais la page d'accueil seule."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[tool],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # réseau, SDK trop ancien, quota… → on n'attache rien
        log.warning("Recherche lien officiel (%s) impossible : %s", domain, exc)
        return ""

    blocks = message.content or []
    text = _text_of(blocks)
    if "AUCUN" in text.upper() and "http" not in text.lower():
        return ""

    # 1) URL explicitement citée dans le texte de réponse, si sur le bon domaine.
    for m in re.findall(r"https?://[^\s)\"']+", text):
        host = (urlparse(m).netloc or "").lower().removeprefix("www.")
        if host == domain or host.endswith("." + domain):
            return m.rstrip(".,);")
    # 2) Repli : première URL des résultats/citations hébergée sur le domaine.
    on_domain = _urls_on_domain(blocks, domain)
    return on_domain[0] if on_domain else ""
