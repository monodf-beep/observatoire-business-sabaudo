"""Tri par LLM de la veille « Business Sabaudo ».

Les filtres par mots-clés ne savent pas juger la PERTINENCE réelle ni distinguer un
vrai titre d'article d'un fragment de corps. Ce module confie cette décision à un
modèle léger (Haiku) : pour chaque élément il décide GARDER/JETER (intérêt économique
pour le périmètre sabaudo) et NETTOIE le titre.

Mise en cache sur disque (logs/triage_cache.json) : chaque élément n'est jugé qu'UNE
fois (clé = hash url+titre). Les builds suivants relisent le cache → coût quasi nul.

Fail-safe : en l'absence de clé API ou en cas d'erreur, on renvoie « garder » pour
tout (la veille n'est jamais cassée par le tri).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_FILE = ROOT / "logs" / "triage_cache.json"
DEFAULT_MODEL = "claude-haiku-4-5"
BATCH = 25


def item_key(url: str, title: str) -> str:
    """Clé stable d'un élément (URL si dispo, sinon titre normalisé)."""
    base = (url or "").strip().lower().split("#")[0].rstrip("/")
    if not base:
        t = unicodedata.normalize("NFD", title or "")
        base = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
        base = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", base)).strip()
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


_SYSTEM = (
    "Tu filtres une veille ÉCONOMIQUE pour l'Observatoire Business Sabaudo, qui couvre "
    "la Savoie/Haute-Savoie, le Piémont (Turin), la Vallée d'Aoste, Nice/Alpes-Maritimes "
    "et l'espace transfrontalier Alcotra. Public : décideurs et entreprises. "
    "Tu juges chaque élément avec exigence."
)

_INSTRUCTIONS = (
    "Pour CHAQUE élément ci-dessous, décide s'il s'agit d'une vraie information à "
    "intérêt ÉCONOMIQUE pour ce public (entreprises, emploi, investissement, innovation, "
    "immobilier d'entreprise, commerce, tourisme d'affaires, financements, implantations, "
    "politiques économiques, projets de territoire).\n\n"
    "JETTE (keep=false) : faits divers, accidents, criminalité, météo/canicule, sport, "
    "nécrologies, people, culture/spectacles sans angle business, santé individuelle, "
    "et tout FRAGMENT non informatif (ex. « Si vous n'arrivez pas à lire ce message », "
    "« Commerce | Hôtel | Restaurant », « Prosegui la lettura », « actions renforcées sur "
    "le territoire », « 3 e 4 dicembre a Bari », un simple nom d'entreprise sans contexte).\n"
    "GARDE (keep=true) UNIQUEMENT une information économique substantielle et compréhensible.\n\n"
    "Pour chaque élément gardé, réécris un TITRE propre, factuel, concis (max ~110 caractères), "
    "sans emoji ni « >> ». Si keep=false, titre = \"\".\n\n"
    "Réponds STRICTEMENT par un tableau JSON, un objet par élément dans l'ordre :\n"
    "[{\"i\":0,\"keep\":true,\"titre\":\"...\"}, ...]\n\n"
    "Éléments :\n"
)


def _parse_json_array(text: str) -> list | None:
    text = text.strip()
    if "```" in text:
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _call(units: list[dict], model: str, api_key: str) -> dict:
    """Appelle le LLM sur un lot ; renvoie {key: {keep, title}}."""
    import anthropic

    lines = []
    for i, u in enumerate(units):
        lines.append(f'{i}. [{u.get("territoire","")}] ({u.get("source","")}) {u.get("title","")[:200]}')
    prompt = _INSTRUCTIONS + "\n".join(lines)
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model, max_tokens=4096, system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content)
    arr = _parse_json_array(text)
    out: dict = {}
    if not arr:
        return out
    for obj in arr:
        try:
            i = int(obj.get("i"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(units):
            keep = bool(obj.get("keep"))
            out[units[i]["key"]] = {
                "keep": keep,
                "title": (obj.get("titre") or "").strip() if keep else "",
            }
    return out


def triage(units: list[dict], *, model: str | None = None, log=None) -> dict:
    """Juge une liste d'éléments {key,title,source,territoire}. Renvoie le cache complet
    {key: {keep, title}}. N'appelle le LLM que pour les éléments NON déjà en cache."""
    cache = load_cache()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    todo = [u for u in units if u["key"] not in cache]
    if not todo:
        return cache
    if not api_key:
        if log:
            log.warning("ANTHROPIC_API_KEY absente — tri LLM ignoré (tout est gardé).")
        return cache
    model = model or os.getenv("TRIAGE_MODEL", DEFAULT_MODEL)
    try:
        import anthropic  # noqa: F401
    except ImportError:
        if log:
            log.warning("Dépendance anthropic absente — tri LLM ignoré.")
        return cache

    done = 0
    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        try:
            verdicts = _call(batch, model, api_key)
        except Exception as exc:  # le tri ne doit jamais casser la collecte
            if log:
                log.warning("Tri LLM (lot %d) échoué : %s", start // BATCH, exc)
            verdicts = {}
        for u in batch:
            # Défaut « garder » si le modèle n'a rien dit sur cet item (fail-open).
            cache[u["key"]] = verdicts.get(u["key"], {"keep": True, "title": u["title"]})
        done += len(batch)
        if log:
            log.info("Tri LLM : %d/%d éléments jugés…", done, len(todo))
    save_cache(cache)
    return cache
