"""Traduction du contenu de la newsletter via l'API Anthropic (FR -> autre langue).

Principe : on garde UNE seule sélection éditoriale (le dict `data` produit en
français) et on traduit uniquement les champs visibles par le lecteur. La
structure, les liens, les images, les territoires et les noms propres sont
conservés tels quels. On traduit, on ne réécrit pas et on n'invente rien.

Champs traduits : subject, preheader, signature, et pour la une / les articles /
les ponts : titre + résumé ; pour les signaux : titre.
"""
from __future__ import annotations

import copy
import json
import os

from utils.logger import get_logger

log = get_logger("translate")

_LANG_NAME = {"it": "italien", "fr": "français", "en": "anglais"}
DEFAULT_MODEL = "claude-sonnet-4-6"


def _translate_segments(segments: list[str], target_lang: str, model: str) -> list[str]:
    """Traduit une liste de segments ; renvoie une liste de même longueur/ordre."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY non définie : traduction impossible.")

    lang_name = _LANG_NAME.get(target_lang, target_lang)
    payload = json.dumps(segments, ensure_ascii=False)
    prompt = (
        f"Traduis en {lang_name} les segments du tableau JSON ci-dessous (newsletter "
        "économique B2B). Règles STRICTES :\n"
        "- Renvoie UNIQUEMENT un tableau JSON de chaînes, MÊME longueur et MÊME ordre.\n"
        "- Conserve les NOMS PROPRES tels quels (entreprises, institutions, lieux : "
        "Politecnico, Confindustria, Sophia-Antipolis…).\n"
        "- Garde une chaîne vide pour toute entrée vide. Ne fusionne, n'ajoute, ne "
        "supprime aucun élément.\n"
        "- Traduction fidèle et idiomatique, ton B2B sérieux. Ne commente pas.\n\n"
        f"{payload}"
    )
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text").strip()
    # Le modèle peut entourer le tableau de ```json … ``` ou d'un texte : on isole le [ … ].
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"Réponse de traduction inattendue : {text[:200]}")
    out = json.loads(text[start:end + 1])
    if not isinstance(out, list) or len(out) != len(segments):
        raise ValueError(
            f"Traduction de longueur incohérente ({len(out)} ≠ {len(segments)})."
        )
    return [str(x) for x in out]


def translate_email_data(data: dict, target_lang: str, model: str | None = None) -> dict:
    """Renvoie une COPIE de `data` avec le contenu traduit et `lang` positionné.

    Pour `target_lang == 'fr'` : renvoie une copie inchangée (juste `lang='fr'`).
    Lève en cas d'échec (l'appelant décide d'ignorer la langue ou non).
    """
    out = copy.deepcopy(data)
    if target_lang == "fr":
        out["lang"] = "fr"
        return out

    model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)

    # 1) Rassembler les segments à traduire, en mémorisant comment les ré-affecter.
    segments: list[str] = []
    setters: list = []  # callables qui posent la valeur traduite

    def add(get, set_) -> None:
        segments.append(get() or "")
        setters.append(set_)

    add(lambda: out.get("subject", ""), lambda v: out.__setitem__("subject", v))
    add(lambda: out.get("preheader", ""), lambda v: out.__setitem__("preheader", v))
    add(lambda: out.get("signature", ""), lambda v: out.__setitem__("signature", v))

    hero = out.get("hero")
    if hero:
        add(lambda: hero.get("title", ""), lambda v: hero.__setitem__("title", v))
        add(lambda: hero.get("summary", ""), lambda v: hero.__setitem__("summary", v))
    for s in out.get("signaux", []):
        add(lambda s=s: s.get("title", ""), lambda v, s=s: s.__setitem__("title", v))
    for it in out.get("items", []):
        add(lambda it=it: it.get("title", ""), lambda v, it=it: it.__setitem__("title", v))
        add(lambda it=it: it.get("summary", ""), lambda v, it=it: it.__setitem__("summary", v))
    for p in out.get("ponts", []):
        add(lambda p=p: p.get("title", ""), lambda v, p=p: p.__setitem__("title", v))
        add(lambda p=p: p.get("summary", ""), lambda v, p=p: p.__setitem__("summary", v))

    # 2) Traduire puis ré-affecter dans le même ordre.
    log.info("Traduction de %d segment(s) vers %s…", len(segments), target_lang)
    translated = _translate_segments(segments, target_lang, model)
    for setter, value in zip(setters, translated):
        setter(value)

    out["lang"] = target_lang
    return out
