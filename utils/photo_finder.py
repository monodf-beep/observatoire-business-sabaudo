"""Recherche AUTOMATIQUE d'une photo représentative d'un acteur économique.

Quand la « une » vient de la presse (image retirée par design), on veut mieux
qu'une bannière générique : la vraie photo de l'entreprise/institution citée.

Stratégie, sans nouvelle infrastructure (réutilise la clé API Anthropic déjà
présente dans le pipeline) :
  1. Claude + son outil de recherche web intégré → identifie le SITE OFFICIEL de
     l'acteur (son propre domaine, pas la presse ni un annuaire).
  2. On télécharge la page et on extrait son image de partage (og:image /
     twitter:image) — l'image que l'organisation a elle-même choisie pour la
     représenter. Étape déterministe, pas d'hallucination.
  3. On valide que l'URL pointe bien vers une vraie image.

Tout échec (pas de site trouvé, page injoignable, pas d'image) renvoie "" :
l'appelant retombe alors sur la bannière de territoire. Jamais d'exception levée.

⚠ Droits : l'og:image est l'image de communication publique de l'acteur. Pour un
média qui CRÉDITE et LIE l'acteur, c'est l'usage le plus défendable — mais cela
reste une décision éditoriale (cf. config/actor_images.txt).
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from utils.logger import get_logger

log = get_logger("photo_finder")

_UA = "Mozilla/5.0 (compatible; CulturaSabaudaBot/1.0; +https://culturasabauda.eu)"

# Domaines jamais retenus comme « site officiel » (presse, annuaires, agrégateurs).
_BLOCKED_HOST_PARTS = (
    "google.", "news.google", "facebook.", "instagram.", "linkedin.", "twitter.",
    "x.com", "youtube.", "pagesjaunes.", "societe.com", "mappy.", "cylex",
    "wikipedia.", "leboncoin.", "amazon.", "tripadvisor.",
)


def _ask_official_site(actor: str, territory: str, title: str, *, api_key: str, model: str) -> str:
    """Demande à Claude (recherche web activée) l'URL du site officiel de l'acteur."""
    prompt = (
        "Tu aides un observatoire économique régional à illustrer un article.\n"
        f"Acteur (sujet de l'article) : « {actor} »\n"
        f"Territoire : {territory}\n"
        f"Angle de l'article : « {title} »\n\n"
        "Trouve, via recherche web, le SITE OFFICIEL de cet acteur (son propre "
        "domaine d'entreprise/institution). N'accepte JAMAIS : un site de presse, "
        "un annuaire (pagesjaunes, societe.com…), un réseau social, Wikipédia.\n"
        "Réponds UNIQUEMENT par un objet JSON, sans autre texte :\n"
        '{"site": "https://…"}  (page d\'accueil ou page la plus pertinente)\n'
        "ou {\"site\": null} si tu ne peux pas l'identifier avec confiance."
    )
    try:
        from utils.web_search import web_search_text
        text = web_search_text(prompt, api_key=api_key, model=model, max_uses=3)
    except Exception as exc:  # SDK trop ancien, outil indisponible, erreur réseau…
        log.warning("Recherche web indisponible (photo) pour « %s » : %s — "
                    "vérifier anthropic>=0.49.0 et l'accès à l'outil web_search.",
                    actor, exc)
        return ""
    match = re.search(r"\{[^{}]*\"site\"[^{}]*\}", text, re.S)
    if not match:
        return ""
    try:
        site = (json.loads(match.group(0)).get("site") or "").strip()
    except json.JSONDecodeError:
        return ""
    if not site.startswith(("http://", "https://")):
        return ""
    host = urlparse(site).netloc.lower()
    if any(part in host for part in _BLOCKED_HOST_PARTS):
        log.info("Site écarté (presse/annuaire/réseau) pour « %s » : %s", actor, host)
        return ""
    return site


def _extract_og_image(page_url: str) -> str:
    """Télécharge la page et renvoie l'URL absolue de son og:image / twitter:image."""
    try:
        req = Request(page_url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=15) as resp:
            html = resp.read(300_000).decode("utf-8", "ignore")
    except Exception as exc:
        log.info("Page injoignable (%s) : %s", page_url, exc)
        return ""
    patterns = (
        r'<meta[^>]+(?:property|name)=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image(?::url)?["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    )
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            return urljoin(page_url, m.group(1).strip())
    return ""


def _validate_image(url: str) -> bool:
    """Vrai si l'URL renvoie une vraie image (type MIME image/* ou en-tête magique)."""
    try:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=15) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            head = resp.read(32)
    except Exception:
        return False
    if ctype.startswith("image/"):
        return True
    return (
        head.startswith(b"\xff\xd8\xff")              # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")       # PNG
        or head[:4] == b"RIFF" and head[8:12] == b"WEBP"  # WEBP
        or head[:3] == b"GIF"                          # GIF
    )


def find_actor_photo(actor: str, territory: str, title: str, *, api_key: str, model: str) -> str:
    """Renvoie l'URL d'une photo représentative de l'acteur, ou "" si rien de fiable."""
    actor = (actor or "").strip()
    if not actor or not api_key:
        return ""
    site = _ask_official_site(actor, territory, title, api_key=api_key, model=model)
    if not site:
        return ""
    image = _extract_og_image(site)
    if not image:
        return ""
    if not _validate_image(image):
        log.info("og:image invalide pour « %s » : %s", actor, image)
        return ""
    log.info("Photo trouvée pour « %s » : %s (via %s)", actor, image, urlparse(site).netloc)
    return image
