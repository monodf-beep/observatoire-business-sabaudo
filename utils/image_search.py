"""Illustration des brèves : trouve une VRAIE PHOTO pertinente et LIBRE DE DROITS
quand la source n'expose qu'un logo (cas fréquent de l'institutionnel).

Pipeline :
  1. recherche d'images Creative Commons via l'API Openverse (sans clé, usage
     commercial) à partir d'une requête dérivée du titre / de l'acteur ;
  2. (option) validation par un LLM VISION : la photo est-elle une vraie image
     éditoriale EN LIEN avec le sujet ? (rejette logos résiduels et hors-sujet) ;
  3. repli silencieux : aucune photo convaincante → '' (la carte de territoire prend
     le relais en amont).

Tout est MIS EN CACHE (logs/) et FAIL-OPEN : sans réseau / sans clé API, on n'illustre
simplement pas — jamais d'erreur bloquante. Openverse = licences CC → pas de risque
de droits (contrairement au hotlink d'une image de presse quelconque).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from utils.sources import is_logo_image

ROOT = Path(__file__).resolve().parent.parent
_SEARCH_CACHE = ROOT / "logs" / "image_search_cache.json"
_JUDGE_CACHE = ROOT / "logs" / "image_judge_cache.json"
_ILLUS_CACHE = ROOT / "logs" / "image_illustration_cache.json"
_OPENVERSE = "https://api.openverse.org/v1/images/"
_UA = "ObservatoireBusinessSabaudo/1.0 (+https://culturasabauda.eu)"
_DEFAULT_JUDGE_MODEL = "claude-haiku-4-5"

# Mots vides à retirer de la requête (FR + IT + EN), pour ne garder que les termes utiles.
_STOP = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "à", "au", "aux",
    "en", "pour", "sur", "dans", "par", "avec", "sans", "ce", "cette", "ces", "son", "sa",
    "ses", "leur", "qui", "que", "dont", "plus", "moins", "il", "elle", "se", "ne", "pas",
    "the", "a", "of", "and", "to", "in", "for", "on", "with", "il", "lo", "gli", "i", "e",
    "per", "con", "su", "da", "che", "del", "della", "dei", "delle", "al", "alla",
}


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _query(actor: str, title: str) -> str:
    """Requête d'images concise : acteur (si parlant) + mots-clés forts du titre."""
    terms: list[str] = []
    actor = (actor or "").strip()
    if 2 < len(actor) < 40 and not actor.lower().startswith(("radar", "économie", "economia")):
        terms.append(actor)
    norm = re.sub(r"[^\w\s'-]", " ", (title or ""))
    for w in norm.split():
        wl = w.lower().strip("'-")
        if len(wl) >= 4 and wl not in _STOP and wl not in {t.lower() for t in terms}:
            terms.append(w)
        if len(terms) >= 5:
            break
    return " ".join(terms).strip()


def search_photo(query: str, *, log=None) -> str:
    """URL d'une photo CC pertinente (Openverse), ou '' . Mémoïsé par requête."""
    query = (query or "").strip()
    if not query:
        return ""
    cache = _load(_SEARCH_CACHE)
    if query in cache:
        return cache[query]

    url = ""
    try:
        qs = urllib.parse.urlencode({
            "q": query, "license_type": "commercial", "size": "large",
            "page_size": "8", "mature": "false",
        })
        req = urllib.request.Request(_OPENVERSE + "?" + qs,
                                     headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read(400_000).decode("utf-8", "replace"))
        for res in data.get("results", []):
            cand = (res.get("url") or "").strip()
            if not cand.lower().startswith("http") or is_logo_image(cand):
                continue
            w, h = res.get("width") or 0, res.get("height") or 0
            if w and w < 400:                     # trop petit → souvent une vignette/icône
                continue
            if w and h and (w / h > 3 or h / w > 3):  # bannière très allongée → on évite
                continue
            url = cand
            break
    except Exception as exc:
        if log:
            log.info("Recherche photo échouée (%s) : %s", query[:40], exc)
        url = ""

    cache[query] = url
    _save(_SEARCH_CACHE, cache)
    return url


def judge_image(image_url: str, title: str, *, model: str | None = None, log=None) -> bool:
    """LLM VISION : la photo est-elle une vraie image éditoriale EN LIEN avec le titre ?
    Mémoïsé par URL. Fail-open : sans clé/erreur → True (on garde la photo trouvée)."""
    if not image_url:
        return False
    cache = _load(_JUDGE_CACHE)
    if image_url in cache:
        return bool(cache[image_url])

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return True  # pas de juge dispo → on garde la photo (libre de droits de toute façon)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model or os.getenv("IMAGE_JUDGE_MODEL", _DEFAULT_JUDGE_MODEL),
            max_tokens=10,
            system=("Tu vérifies si une image illustre correctement une brève économique. "
                    "Réponds UNIQUEMENT par OUI ou NON."),
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "url", "url": image_url}},
                {"type": "text", "text": (
                    f"Titre de la brève : « {title} ».\n"
                    "Cette image est-elle une VRAIE PHOTO éditoriale en lien plausible avec le sujet "
                    "(pas un logo, pas un pictogramme, pas un hors-sujet manifeste) ? Réponds OUI ou NON.")},
            ]}],
        )
        text = "".join(getattr(b, "text", "") for b in msg.content).strip().lower()
        verdict = text.startswith("oui") or text.startswith("yes")
    except Exception as exc:
        if log:
            log.info("Juge vision indisponible : %s", exc)
        verdict = True  # erreur transitoire → on ne perd pas la photo

    cache[image_url] = verdict
    _save(_JUDGE_CACHE, cache)
    return verdict


_SOCIAL = ("facebook", "twitter", "x.com", "instagram", "youtube", "youtu.be",
           "linkedin", "pinterest", "tiktok")


def find_illustration(title: str, summary: str = "", *, model: str | None = None, log=None) -> str:
    """SCRAPE une vraie photo du web : recherche des articles sur le sujet, récupère
    la photo (og:image) d'un résultat pertinent, la valide par vision. '' si rien."""
    from utils import official_search

    search_model = os.getenv("OFFICIAL_SEARCH_MODEL", "claude-sonnet-4-6")
    query = (f"{title}. {summary}").strip()
    urls = official_search.web_search_urls(query, search_model)
    judge_model = os.getenv("IMAGE_JUDGE_MODEL", _DEFAULT_JUDGE_MODEL)
    for u in urls:
        host = urllib.parse.urlparse(u).netloc.lower()
        if any(s in host for s in _SOCIAL):
            continue
        final, html, status = official_search.fetch_page(u)
        if status != "ok" or not html:
            continue
        og = official_search.og_image_from_html(html, final)
        if not og or is_logo_image(og):
            continue
        if judge_image(og, title, model=judge_model, log=log):
            if log:
                log.info("Photo web (article) pour « %s » : %s", title[:40], og)
            return og
    return ""


def illustrate(title: str, actor: str = "", *, summary: str = "", judge: bool = True,
               model: str | None = None, log=None) -> str:
    """Trouve une photo pour une brève, MISE EN CACHE par titre. Ordre :
    1) photo libre de droits (Openverse/CC) ; 2) photo scrapée d'un article web (validée
    par vision). '' si rien de convaincant → carte de territoire en amont."""
    if os.getenv("NEWSLETTER_WEB_IMAGES", "1").strip() == "0":
        return ""
    key = _query(actor, title) or (title or "")[:80]
    cache = _load(_ILLUS_CACHE)
    if key in cache:
        return cache[key]

    do_judge = judge and os.getenv("NEWSLETTER_IMAGE_JUDGE", "1").strip() != "0"
    result = ""
    # 1. Banque libre de droits (gratuit, rare sur l'hyper-local).
    cc = search_photo(_query(actor, title), log=log)
    if cc and (not do_judge or judge_image(cc, title, model=model, log=log)):
        result = cc
    # 2. Scraping d'une vraie photo d'article via recherche web (le vrai levier local).
    if not result:
        result = find_illustration(title, summary, model=model, log=log)

    cache[key] = result
    _save(_ILLUS_CACHE, cache)
    return result
