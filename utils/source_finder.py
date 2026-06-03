"""Recherche AUTOMATIQUE d'un lien légitime pour « Lire l'article ».

Quand une info arrive via la presse (lien retiré par design — on ne promeut pas
les journaux concurrents), on veut tout de même offrir au lecteur un lien utile,
en respectant une hiérarchie éditoriale :

  1. Nos Alpes (média PARTENAIRE, nosalpes.eu) : s'ils ont traité le sujet, on
     met leur lien.
  2. Sinon, une SOURCE PRIMAIRE / officielle : communiqué de l'entreprise ou de
     l'organisme concerné, site institutionnel, organisme public, université,
     site officiel de l'événement. Jamais un concurrent presse.

Mécanique identique à la photo automatique : Claude + recherche web intégrée,
puis filtrage déterministe (on rejette tout domaine de presse connu et tout lien
injoignable). Aucune exception levée : un échec laisse simplement le lien vide.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from utils.logger import get_logger
from utils.sources import is_press

log = get_logger("source_finder")

_UA = "Mozilla/5.0 (compatible; CulturaSabaudaBot/1.0; +https://culturasabauda.eu)"
_PARTNER_HOST = "nosalpes.eu"

# Jamais retenus : agrégateurs, réseaux sociaux, annuaires (ni source primaire,
# ni partenaire). La presse concurrente est filtrée à part via press_domains.txt.
_BLOCKED_HOST_PARTS = (
    "news.google", "google.", "facebook.", "instagram.", "linkedin.", "twitter.",
    "x.com", "youtube.", "pagesjaunes.", "societe.com", "mappy.", "cylex",
    "wikipedia.", "leboncoin.", "amazon.",
)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _url_reachable(url: str) -> bool:
    """Vrai si l'URL répond (page existante)."""
    try:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=15) as resp:
            return 200 <= getattr(resp, "status", resp.getcode()) < 400
    except Exception:
        return False


# Langue à privilégier pour le lien, selon le territoire (la version locale prime
# sur une éventuelle version anglaise renvoyée par défaut).
_LANG_BY_TERRITORY = {
    "Savoie": "français", "Nice": "français", "Alcotra": "français",
    "Piemonte": "italien", "Vallee-Aoste": "italien",
}


def _ask_link(title: str, actor: str, territory: str, *, api_key: str, model: str) -> dict | None:
    """Demande à Claude (recherche web) le meilleur lien selon la hiérarchie éditoriale."""
    lang_pref = _LANG_BY_TERRITORY.get(territory, "français")
    prompt = (
        "Tu sources un article pour un observatoire économique de l'espace sabaudo.\n"
        f"Sujet : « {title} »\n"
        f"Acteur principal : « {actor} »\n"
        f"Territoire : {territory}\n\n"
        "Trouve, via recherche web, le MEILLEUR lien à mettre derrière « Lire "
        "l'article », par ordre de priorité STRICT :\n"
        "1) Un article du média partenaire NOS ALPES (site nosalpes.eu) qui traite "
        "CE sujet précis. S'il existe et correspond clairement → kind = \"partner\".\n"
        "2) Sinon, une SOURCE PRIMAIRE/officielle : le SITE OFFICIEL DE L'ACTEUR nommé "
        "ci-dessus (entreprise, université, organisme public, Région…) ou son "
        "communiqué, le site officiel de l'événement (ex. choosefrance.fr). Cherche-le "
        "MÊME SI l'information a d'abord été relayée par la presse. → kind = \"primary\".\n"
        "INTERDIT : un site de presse ou d'actualité généraliste concurrent "
        "(journaux régionaux, agrégateurs, Google News), les réseaux sociaux, les "
        "annuaires, Wikipédia.\n"
        f"LANGUE : privilégie la version en {lang_pref} de la page (Nos Alpes est "
        "bilingue FR/IT : choisis la bonne langue). Si tu tombes d'abord sur une "
        f"version anglaise (/en/…), cherche et renvoie plutôt la version en {lang_pref} "
        "si elle existe.\n"
        "Le lien doit pointer vers la PAGE PRÉCISE (l'article ou le communiqué), pas "
        "une page d'accueil générique.\n"
        "Réponds UNIQUEMENT par un objet JSON, sans autre texte :\n"
        '{"url": "https://…", "kind": "partner"|"primary"}  ou  {"url": null}'
    )
    try:
        from utils.web_search import web_search_text
        text = web_search_text(prompt, api_key=api_key, model=model, max_uses=4)
    except Exception as exc:
        log.warning("Recherche web indisponible (lien) pour « %s » : %s — "
                    "vérifier anthropic>=0.49.0 et l'accès à l'outil web_search.",
                    title, exc)
        return None
    match = re.search(r"\{[^{}]*\"url\"[^{}]*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    return {"url": url, "kind": (data.get("kind") or "primary").strip().lower()}


def find_canonical_link(title: str, actor: str, territory: str, *,
                        press: set[str], api_key: str, model: str) -> dict | None:
    """Renvoie {url, domain, kind} pour « Lire l'article », ou None si rien de fiable.

    kind ∈ {"partner" (Nos Alpes), "primary" (source primaire/officielle)}.
    Filtre déterministe : rejette presse concurrente, agrégateurs, liens morts.
    """
    if not title or not api_key:
        return None
    found = _ask_link(title, actor, territory, api_key=api_key, model=model)
    if not found:
        return None
    url = found["url"]
    domain = _domain(url)
    is_partner_link = domain == _PARTNER_HOST or domain.endswith("." + _PARTNER_HOST)
    if any(part in domain for part in _BLOCKED_HOST_PARTS):
        log.info("Lien écarté (agrégateur/réseau) pour « %s » : %s", title, domain)
        return None
    if not is_partner_link and is_press(domain, press):
        log.info("Lien écarté (presse concurrente) pour « %s » : %s", title, domain)
        return None
    if not _url_reachable(url):
        log.info("Lien injoignable pour « %s » : %s", title, url)
        return None
    kind = "partner" if is_partner_link else "primary"
    log.info("Lien trouvé pour « %s » : %s (%s)", title, url, kind)
    return {"url": url, "domain": domain, "kind": kind}
