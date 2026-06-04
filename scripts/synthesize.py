#!/usr/bin/env python3
"""Script 3 — Synthèse hebdomadaire via l'API Anthropic.

- Entrée : fichiers JSON de la semaine ISO courante dans 01_Veille_brute/
- Appel API Anthropic (modèle configurable, défaut claude-sonnet-4-6)
- Prompt : synthèse par territoire + 5 signaux forts + draft newsletter
- Sortie : Markdown dans 02_Veille_traitée/Synthèses_hebdomadaires/AAAA-WNN.md
- PAS d'envoi automatique : validation de Franck requise avant publication

Option : --upload pour téléverser le Markdown sur Google Drive après génération.
Scheduler prévu : cron du vendredi 18h (voir crontab.txt).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "01_Veille_brute"
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"
DEFAULT_MODEL = "claude-sonnet-4-6"

# Bornes pour rester dans une enveloppe de tokens raisonnable
MAX_BODY_CHARS = 1500
MAX_ITEMS_PER_TERRITORY = 40

log = get_logger("synthesize")


def iso_week_id(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def load_all_records() -> dict[str, dict[str, list[dict]]]:
    """Charge tous les enregistrements, groupés par semaine ISO puis territoire."""
    weeks: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    if not INPUT_DIR.exists():
        log.warning("Dossier de veille brute absent : %s", INPUT_DIR)
        return weeks

    for json_file in INPUT_DIR.rglob("*.json"):
        try:
            record = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Fichier illisible ignoré (%s) : %s", json_file, exc)
            continue
        try:
            dt = datetime.fromisoformat(record.get("date", ""))
        except ValueError:
            continue
        week = iso_week_id(dt)
        # Territoire : champ explicite (RSS) ou déduit du dossier parent (Gmail)
        territory = record.get("territoire") or _territory_from_path(json_file)
        record["territoire"] = territory
        weeks[week][territory].append(record)

    return weeks


def select_week(all_weeks: dict[str, dict], requested: str | None, now: datetime) -> str:
    """Choisit la semaine à synthétiser.

    - Si une semaine est explicitement demandée (--week), on la respecte.
    - Sinon on prend la semaine courante ; si elle est vide, on se replie sur la
      dernière semaine passée contenant des données (cas fréquent : flux RSS en retard).
    """
    if requested:
        return requested
    current = iso_week_id(now)
    if current in all_weeks:
        return current
    prior = sorted(w for w in all_weeks if w <= current)
    if prior:
        log.info("Semaine courante %s sans donnée → repli sur %s", current, prior[-1])
        return prior[-1]
    return current


def _territory_from_path(json_file: Path) -> str:
    # Dossier au format AAAA-MM-Territoire (le territoire peut contenir un tiret,
    # ex. Vallee-Aoste) → on découpe seulement sur les deux premiers tirets.
    parts = json_file.parent.name.split("-", 2)
    return parts[2] if len(parts) == 3 else "Indetermine"


def build_registry(by_territory: dict[str, list[dict]]) -> dict[int, dict]:
    """Numérote chaque enregistrement de la semaine (id stable -> enregistrement)."""
    registry: dict[int, dict] = {}
    next_id = 1
    for territory in sorted(by_territory):
        for rec in by_territory[territory][:MAX_ITEMS_PER_TERRITORY]:
            registry[next_id] = rec
            next_id += 1
    return registry


def build_prompt(registry: dict[int, dict], target_week: str) -> str:
    lines: list[str] = []
    by_terr: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for rid, rec in registry.items():
        by_terr[rec.get("territoire", "Indetermine")].append((rid, rec))
    for territory in sorted(by_terr):
        lines.append(f"\n## Territoire : {territory} ({len(by_terr[territory])} élément(s))")
        for rid, rec in by_terr[territory]:
            origin = rec.get("feed_title") or rec.get("from") or rec.get("feed_url", "")
            date = rec.get("date", "")[:10]
            body = (rec.get("body") or "").strip()[:MAX_BODY_CHARS]
            link = rec.get("link", "")
            lines.append(f"\n### [#{rid}] {rec.get('title', '(sans titre)')}")
            lines.append(f"- Source : {origin} | Date : {date}")
            if link:
                lines.append(f"- Lien : {link}")
            if body:
                lines.append(f"- Contenu : {body}")
    corpus = "\n".join(lines)

    instructions = (
        "Tu es l'assistant éditorial de Cultura Sabauda, média économique de l'espace\n"
        "sabaudo (Savoie, Piémont, Vallée d'Aoste, Nice, périmètre Alcotra).\n\n"
        "À partir des contenus collectés cette semaine (chacun identifié par [#id]),\n"
        "produis DEUX choses, dans cet ordre IMPÉRATIF (le bloc JSON d'abord).\n\n"
        "PARTIE 1 — COMMENCE par les données de la newsletter, dans UN SEUL bloc ```json```.\n"
        "  Schéma EXACT (n'invente aucun texte absent des sources ; réfère chaque élément\n"
        "  par son id [#id] pour qu'on rattache le lien, la source et l'image d'origine) :\n"
        "  ```json\n"
        "  {\n"
        '    "objet": "objet email, 60 caractères max, porteur de valeur",\n'
        '    "preheader": "phrase de prévisualisation qui complète l\'objet",\n'
        '    "une": {"id": <id>, "titre": "titre éditorialisé", "resume": "2-3 phrases", "acteur": "source primaire"},\n'
        '    "signaux": [{"id": <id>, "titre": "titre court"}],\n'
        '    "articles": [{"id": <id>, "titre": "titre éditorialisé", "resume": "2-3 phrases", "acteur": "source primaire"}],\n'
        '    "ponts": [{"id": <id>, "titre": "titre orienté lien", "resume": "le lien transfrontalier", "acteur": "source primaire"}],\n'
        '    "signature": "Bonne lecture,\\nLa rédaction, Cultura Sabauda"\n'
        "  }\n"
        "  ```\n"
        "  - Remplace chaque <id> par un identifiant RÉEL [#id] de la liste ci-dessous\n"
        "    (un entier ≥ 1 réellement présent). N'invente JAMAIS d'id, n'utilise pas 0.\n"
        "  - 'acteur' = l'ENTITÉ PRIMAIRE de l'info (l'entreprise, l'institution, l'organisme\n"
        "    concerné : ex. « FC Annecy », « Casino de Saint-Vincent », « CCI Nice »). JAMAIS\n"
        "    le journal/média qui l'a relayée — on ne cite pas la presse comme source.\n"
        "  - 'une' = l'actualité la plus marquante (le héros).\n"
        "  - 'signaux' = 3 à 5 signaux forts (titres courts).\n"
        "  - 'articles' = 4 à 6 brèves éditorialisées (hors 'une'), une par sujet fort.\n"
        "  - RÈGLE ANTI-DOUBLON ABSOLUE : chaque id ne peut figurer QUE DANS UNE SEULE\n"
        "    section ('une', 'signaux', 'articles' ou 'ponts'). Un article choisi comme\n"
        "    'une' ne doit PAS réapparaître dans 'signaux' ni dans 'articles'. Un signal\n"
        "    ne doit PAS réapparaître dans 'articles'. Vérifie chaque id avant de le placer.\n"
        "  - ÉQUILIBRE TERRITORIAL : la sélection ('une' + 'signaux' + 'articles') doit\n"
        "    REPRÉSENTER CHAQUE TERRITOIRE qui dispose d'au moins un contenu à valeur\n"
        "    économique dans le corpus ci-dessous. Si un territoire (ex. Piémont, Vallée\n"
        "    d'Aoste) a des éléments exploitables, retiens-en AU MOINS UN, même s'il est\n"
        "    moins spectaculaire que l'actu d'un autre territoire — l'observatoire couvre\n"
        "    TOUT l'espace sabaudo, pas seulement le territoire le plus actif de la semaine.\n"
        "    N'invente rien pour un territoire dépourvu de contenu : un territoire sans\n"
        "    élément exploitable reste légitimement absent.\n"
        "  - SOURCES INSTITUTIONNELLES À PRIVILÉGIER : les contenus émanant directement\n"
        "    d'incubateurs, d'agences de développement, de chambres de commerce ou de\n"
        "    programmes (ex. Piemonte Innova, I3P, CCI, pépinières VDA, Interreg Alcotra)\n"
        "    sont des signaux de PREMIÈRE main, à forte valeur : retiens-les en priorité\n"
        "    quand ils portent une actualité économique concrète (appel à projets,\n"
        "    lancement, financement, implantation, partenariat).\n"
        "  - 'ponts' = 0 à 3 « ponts & connexions » : des actualités de l'espace sabaudo\n"
        "    qui ont un LIEN CONCRET avec l'extérieur (Grenoble, Lyon, Genève, la Suisse, le\n"
        "    reste de la France, le marché italien, l'international). Ex. : une entreprise\n"
        "    valdôtaine qui exporte en France, un projet Nice–Turin, un partenariat\n"
        "    Savoie–Genève, une PME qui attaque le marché italien. Le 'resume' EXPLICITE le\n"
        "    lien transfrontalier. N'y mets QUE des sujets à dimension extérieure réelle ;\n"
        "    si rien ne s'y prête, renvoie une liste vide. Même règle factuelle : un id réel,\n"
        "    pas de source = pas de pont. Un même sujet ne va PAS à la fois dans 'articles'\n"
        "    et dans 'ponts'.\n"
        "  - Ne retiens que les contenus à VALEUR ÉCONOMIQUE/ÉDITORIALE. Ignore les emails\n"
        "    de service (réponses automatiques, confirmations, fils internes) et les sujets\n"
        "    non économiques (faits divers, sport, météo). Si rien n'a de valeur,\n"
        "    renvoie des listes vides et 'une': null.\n"
        "  - Périmètre Nice : Nice, Menton, l'Éco-Vallée (Plaine du Var), Sophia-Antipolis,\n"
        "    l'Université Côte d'Azur et les pôles de compétitivité. Écarte Cannes\n"
        "    (cinéma/tourisme) et Grasse-ville (parfum), hors-sujet.\n"
        "  - ANGLE LOCAL D'ABORD : chaque 'resume' OUVRE sur le lien territorial (ce que ça\n"
        "    change pour la Savoie / le Piémont / Nice…), JAMAIS sur le contexte national.\n"
        "    Une actu nationale/internationale n'est retenue que si son impact territorial est\n"
        "    concret, et cet impact apparaît dès la 1re phrase (ex. : « Nice capte 7 projets\n"
        "    de Choose France… » plutôt que « Choose France bat un record national… »).\n\n"
        "PARTIE 2 — APRÈS le bloc JSON, une synthèse Markdown COURTE (archive interne) :\n"
        "  1. SIGNAUX FORTS (5 max) : titre + 1-2 phrases + territoire + source.\n"
        "  2. PAR TERRITOIRE : 1-2 lignes par territoire (Savoie, Piémont, Vallée d'Aoste,\n"
        "     Nice/Alpes-Maritimes, Alcotra). Sois concis.\n\n"
        "Tonalité : sérieux, B2B, sans buzzword. Chaque brève répond à « et alors ? »\n"
        "(l'implication concrète).\n"
        "LANGUE : français correct et idiomatique, relu. Garde les NOMS PROPRES italiens\n"
        "tels quels (Politecnico, Confindustria…) mais N'ITALIANISE PAS les mots courants :\n"
        "écris « Casino » (pas « Casinò »), « le mois de mai » (pas « mai » seul), « la Vallée\n"
        "d'Aoste ». Soigne grammaire, accords et tournures.\n"
        "PONCTUATION : n'utilise JAMAIS de tiret cadratin (—) ni demi-cadratin (–), "
        "dans aucun titre ni résumé. Emploie des virgules, des deux-points ou des points.\n"
        "Reste strictement factuel : pas de source = pas de brève.\n"
    )
    return (
        f"{instructions}\n"
        f"=== CONTENUS COLLECTÉS — semaine {target_week} ===\n"
        f"{corpus}\n"
    )


def split_markdown_json(text: str) -> tuple[str, dict | None]:
    """Sépare la synthèse Markdown du bloc JSON de la newsletter."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not match:
        match = re.search(r"(\{(?:[^{}]|\{[^{}]*\})*\})\s*$", text.strip(), re.S)
    if not match:
        return text.strip(), None
    raw = match.group(1)
    # Le JSON peut être en tête : on le retire d'où qu'il soit pour garder le Markdown.
    markdown = (text[: match.start()] + text[match.end():]).strip()
    try:
        return markdown, json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("Bloc JSON newsletter illisible : %s", exc)
        return markdown, None


def _enrich(entry: dict, registry: dict[int, dict], press: set[str],
            partners: set[str] | None = None) -> dict | None:
    """Complète une entrée {id,titre,resume,acteur} avec lien/source/image d'origine.

    Presse (press_domains.txt) → radar uniquement : NI lien, NI logo, NI image.
    Médias partenaires (partner_media.txt) → crédités et liés malgré leur nature
    éditoriale (ex. nosalpes.eu). Prioritaire sur is_press.
    Institutionnels → crédités et liés normalement.
    """
    from utils.sources import domain_of, is_partner, is_press, source_label

    rec = registry.get(int(entry.get("id", -1))) if str(entry.get("id", "")).strip().lstrip("-").isdigit() else None
    if rec is None:
        return None
    domain = domain_of(rec)
    base = {
        "title": entry.get("titre") or rec.get("title", ""),
        "summary": entry.get("resume", ""),
        "territory": rec.get("territoire", "Indetermine"),
    }
    if is_press(domain, press) and not is_partner(domain, partners or set()):
        # Radar : on garde l'info, on retire tout ce qui crédite/promeut le journal.
        base.update({"url": "", "image": "", "domain": "", "source": (entry.get("acteur") or "").strip()})
    else:
        base.update({
            "url": rec.get("link", ""),
            "image": rec.get("image", ""),
            "domain": domain,
            "source": entry.get("acteur") or source_label(rec),
        })
    return base


def _real_photo_for(it: dict, *, actor_images, api_key: str, model: str, allow_web: bool) -> str:
    """Vraie photo pour un article. Ordre : image native > override manuel > photo de
    l'ARTICLE lui-même (og:image de la page-source, déterministe) > recherche web.

    Ne renvoie JAMAIS une bannière de territoire générique. "" si rien de réel.
    """
    from utils.photo_finder import article_image
    from utils.sources import pick_actor_image
    if it.get("image"):                       # image native (source institutionnelle)
        return it["image"]
    override = pick_actor_image(it, actor_images)
    if override:                              # photo épinglée manuellement
        return override
    if it.get("url"):                         # photo publiée AVEC cet article (HTTP, pas d'IA)
        og = article_image(it["url"])
        if og:
            return og
    if allow_web and api_key:
        from utils.photo_finder import find_actor_photo
        return find_actor_photo(it.get("source", ""), it.get("territory", ""),
                                it.get("title", ""), api_key=api_key, model=model)
    return ""


def _has_manual_override(it: dict, actor_images) -> bool:
    from utils.sources import pick_actor_image
    return bool(pick_actor_image(it, actor_images))


def _select_hero_with_photo(hero, items):
    """Garantit que la une commence par un article avec une VRAIE photo, en SOBRIÉTÉ.

    Ordre conçu pour minimiser les appels web (cause des 429) :
      1. la une de l'IA a-t-elle déjà une photo GRATUITE (image native d'une source
         institutionnelle/partenaire, ou override manuel) ? → 0 appel ;
      2. sinon UN SEUL web search sur la une (article le plus important) ;
      3. sinon on promeut la 1re carte ayant une photo gratuite → 0 appel ;
      4. sinon, en dernier recours, quelques web searches sur les premières cartes.
    Si rien n'aboutit (rare), la une reste sans bannière. Désactivable via AUTO_PHOTO=0.
    """
    candidates = [c for c in [hero, *items] if c]
    if not candidates:
        return hero, items
    from utils.sources import load_actor_images
    actor_images = load_actor_images()
    allow_web = os.getenv("AUTO_PHOTO", "1").strip().lower() not in ("0", "false", "no", "off", "")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)

    def free_photo(it: dict) -> str:  # image native ou override manuel : aucun appel
        return _real_photo_for(it, actor_images=actor_images, api_key="", model="", allow_web=False)

    def web_photo(it: dict) -> str:
        try:
            return _real_photo_for(it, actor_images=actor_images, api_key=api_key,
                                   model=model, allow_web=True)
        except Exception as exc:  # robustesse : jamais bloquant en cron
            log.warning("Recherche photo échouée pour « %s » : %s", it.get("title", ""), exc)
            return ""

    def _promote(cand: dict, why: str):
        log.info("Une illustrée %s : %s", why, cand.get("title", ""))
        if cand is hero:
            return hero, items
        rest = ([hero] if hero else []) + [it for it in items if it is not cand]
        return cand, rest

    # 1) La une de l'IA a déjà une vraie photo gratuite ?
    if hero:
        p = free_photo(hero)
        if p:
            hero["image"] = p
            return hero, items
    # 2) Un seul web search sur la une (préserve l'article le plus important).
    if hero and allow_web and api_key:
        p = web_photo(hero)
        if p:
            hero["image"] = p
            return hero, items
    # 3) Une carte a-t-elle une photo gratuite ? (0 appel)
    for cand in items:
        p = free_photo(cand)
        if p:
            cand["image"] = p
            return _promote(cand, "(photo native)")
    # 4) Dernier recours : quelques web searches sur les premières cartes.
    if allow_web and api_key:
        budget = int(os.getenv("AUTO_PHOTO_MAX", "3") or 3)
        for cand in items[:budget]:
            p = web_photo(cand)
            if p:
                cand["image"] = p
                return _promote(cand, "(photo web)")

    log.warning("Aucune vraie photo trouvée pour la une — ouverture sans visuel "
                "(vérifier la recherche web : anthropic>=0.49.0 et AUTO_PHOTO).")
    return hero, items


_DASH_RE = re.compile(r"\s*[—–]\s*")


def _no_dash(text):
    """Neutralise les tirets cadratins/demi-cadratins (perçus comme un « tell » d'IA).

    Deux cas distincts pour ne pas dénaturer le sens :
      • tiret SERRÉ entre deux mots (ex. « Oulx–Modane », « Piémont–Savoie ») :
        c'est un trait d'union typographique (liaison/portée) → on met un vrai
        trait d'union « - » (surtout pas une virgule qui casserait le sens) ;
      • tiret ESPACÉ (ex. « … ressources internationales — centre … ») : c'est
        l'incise parenthétique caractéristique des textes d'IA → virgule.
    Préserve les retours à la ligne (ex. signature)."""
    if not isinstance(text, str) or ("—" not in text and "–" not in text):
        return text
    out = []
    for line in text.split("\n"):
        line = re.sub(r"(?<=\w)[—–](?=\w)", "-", line)  # compound serré → trait d'union
        line = _DASH_RE.sub(", ", line)                 # incise espacée → virgule
        line = re.sub(r"\s*,\s*,", ",", line)   # pas de double virgule
        line = re.sub(r"^\s*,\s*", "", line)     # pas de virgule en tête
        out.append(line)
    return "\n".join(out)


def _strip_dashes(data: dict) -> None:
    """Nettoie les tirets cadratins de tous les textes visibles de la newsletter."""
    for key in ("subject", "preheader", "signature"):
        if data.get(key):
            data[key] = _no_dash(data[key])
    blocks = [data.get("hero"), *data.get("items", []), *data.get("ponts", []), *data.get("signaux", [])]
    for it in blocks:
        if not it:
            continue
        for key in ("title", "summary"):
            if it.get(key):
                it[key] = _no_dash(it[key])


def _log_health(data: dict) -> None:
    """Bilan lisible de la newsletter générée : liens, photos, territoires, trous."""
    hero = data.get("hero")
    items = data.get("items", [])
    arts = [a for a in [hero, *items] if a]
    n = len(arts) or 1
    with_link = sum(1 for a in arts if a.get("url"))
    with_photo = sum(1 for a in arts if a.get("image") and not a.get("image_fallback"))
    terrs = sorted({a.get("territory") for a in [hero, *items, *data.get("signaux", []),
                                                 *data.get("ponts", [])] if a and a.get("territory")})
    hero_ok = bool(hero and hero.get("image") and not hero.get("image_fallback"))
    missing = [a.get("title", "")[:50] for a in arts if not a.get("url")]
    # Territoires de cœur attendus dans CHAQUE édition pan-sabaude (Alcotra est
    # transversal, pas un territoire d'ancrage). On compare en tolérant les
    # variantes d'écriture (accents/espaces) renvoyées par la collecte.
    _CORE = {"Savoie": ("savoie",), "Piémont": ("piemont", "piémont"),
             "Vallée d'Aoste": ("vallee", "vallée", "aoste", "aosta"),
             "Nice": ("nice", "nizza", "côte d'azur", "cote d'azur")}
    seen = " ".join(terrs).lower()
    absent = [label for label, keys in _CORE.items() if not any(k in seen for k in keys)]
    log.info("──────── BILAN NEWSLETTER ────────")
    log.info("Une avec vraie photo : %s", "OUI" if hero_ok else "NON (ouverture sans photo)")
    log.info("Articles avec lien   : %d/%d", with_link, len(arts))
    log.info("Articles avec photo  : %d/%d", with_photo, len(arts))
    log.info("Territoires couverts : %s", ", ".join(terrs) or "aucun")
    if absent:
        log.warning("⚠ TERRITOIRE(S) DE CŒUR ABSENT(S) : %s — vérifier la collecte de "
                    "la semaine ou la sélection (l'observatoire couvre TOUT l'espace "
                    "sabaudo).", ", ".join(absent))
    if missing:
        log.info("Sans lien (à vérifier) : %s", " | ".join(missing))
    log.info("──────────────────────────────────")


def _autofind_sources(items: list[dict], press: set[str]) -> None:
    """Complète le lien « Lire l'article » des items SANS lien (issus de la presse).

    Hiérarchie : Nos Alpes (partenaire) d'abord, sinon une source primaire/officielle
    (jamais un concurrent presse). Désactivable via AUTO_SOURCE=0. Plafonné pour
    borner le coût/la durée. Silencieux : un échec laisse le lien vide.
    """
    if os.getenv("AUTO_SOURCE", "1").strip().lower() in ("0", "false", "no", "off", ""):
        return
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return
    targets = [it for it in items if it and not it.get("url")]
    if not targets:
        return
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    budget = int(os.getenv("AUTO_SOURCE_MAX", "12") or 12)
    try:
        from utils.source_finder import find_canonical_link
    except Exception as exc:  # pragma: no cover
        log.warning("Module de recherche de source indisponible : %s", exc)
        return
    for it in targets:
        if budget <= 0:
            break
        budget -= 1
        try:
            found = find_canonical_link(
                it.get("title", ""), it.get("source", ""), it.get("territory", ""),
                press=press, api_key=api_key, model=model,
            )
        except Exception as exc:  # robustesse : jamais bloquant en cron
            log.warning("Recherche de source échouée pour « %s » : %s", it.get("title", ""), exc)
            continue
        if found:
            it["url"] = found["url"]
            it["domain"] = found["domain"]


def _localize_links(items: list[dict]) -> None:
    """Mémorise, pour chaque lien, ses variantes par langue (via hreflang).

    Stocke `url_by_lang = {"fr": …, "it": …}` sur l'item ; push_brevo choisira la
    bonne version selon l'édition (ex. lien Nos Alpes FR pour l'édition FR, IT pour
    l'IT). Déterministe (lecture des balises hreflang), sans appel IA. Si la page
    n'expose pas d'alternative, les deux langues pointent vers le lien d'origine.
    """
    from utils.source_finder import language_variants
    for it in items:
        url = it and it.get("url")
        if not url:
            continue
        try:
            variants = language_variants(url)
        except Exception:
            variants = {}
        it["url_by_lang"] = {"fr": variants.get("fr", url), "it": variants.get("it", url)}


def build_email_data(parsed: dict, registry: dict[int, dict], week_label: str,
                     logo_url: str, picto_url: str = "") -> dict | None:
    """Construit le dict attendu par variant_magazine à partir du JSON de Claude."""
    from utils.sources import apply_fallback_images, load_partner_media, load_press_domains
    press = load_press_domains()
    partners = load_partner_media()

    une = parsed.get("une") or {}
    hero = _enrich(une, registry, press, partners)
    items = [d for e in parsed.get("articles", []) if (d := _enrich(e, registry, press, partners))]
    ponts = [d for e in parsed.get("ponts", []) if (d := _enrich(e, registry, press, partners))]
    signaux = []
    for s in parsed.get("signaux", []):
        rec = registry.get(int(s["id"])) if str(s.get("id", "")).strip().isdigit() else None
        if rec is not None and s.get("titre"):
            signaux.append({"title": s["titre"], "territory": rec.get("territoire", "Indetermine")})
    if hero is None and not items:
        requested = [une.get("id")] + [a.get("id") for a in parsed.get("articles", [])]
        log.warning(
            "Newsletter vide : aucun id exploitable. Demandés=%s | disponibles=1..%d.",
            requested, len(registry),
        )
        return None
    if hero is None and items:  # repli : le 1er article devient la une
        hero = items.pop(0)

    # COOLDOWN : la grosse synthèse vient de consommer beaucoup de tokens ; on laisse
    # la fenêtre de débit (tokens/min) se vider avant la rafale de recherches web,
    # sinon les 1ers appels partent en 429. Un cron hebdo peut attendre 30 s.
    _web_enabled = (os.getenv("AUTO_SOURCE", "1").strip().lower() not in ("0", "false", "no", "off", "")
                    or os.getenv("AUTO_PHOTO", "1").strip().lower() not in ("0", "false", "no", "off", ""))
    if os.getenv("ANTHROPIC_API_KEY") and _web_enabled:
        cooldown = float(os.getenv("WEB_SEARCH_COOLDOWN", "30") or 30)
        if cooldown > 0:
            log.info("Pause %.0fs avant les recherches web (laisse le débit se rétablir)…", cooldown)
            time.sleep(cooldown)

    # LIEN « Lire l'article » : pour les sujets issus de la presse (lien retiré),
    # on cherche un lien légitime : Nos Alpes (partenaire) puis source primaire.
    _autofind_sources([hero, *items, *ponts], press)

    # RÈGLE D'OUVERTURE : la une DOIT être un article avec une vraie photo. On
    # sélectionne (et photographie) le 1er candidat qui en a une — quitte à promouvoir
    # une carte à la place de la une initiale. Jamais de bannière générique en tête.
    hero, items = _select_hero_with_photo(hero, items)

    # LIENS PAR LANGUE : on mémorise la version FR/IT de chaque lien (hreflang) pour
    # que chaque édition pointe vers la bonne langue (Nos Alpes notamment).
    _localize_links([hero, *items, *ponts])

    data = apply_fallback_images({
        "week_label": week_label,
        "logo_url": logo_url,
        "pictogram_url": picto_url,
        "preheader": parsed.get("preheader", ""),
        "subject": (parsed.get("objet") or f"Business Sabaudo · {week_label}")[:120],
        "hero": hero,
        "signaux": signaux,
        "items": items,
        "ponts": ponts,
        "signature": parsed.get("signature", "La rédaction, Cultura Sabauda"),
        "cta_url": "https://culturasabauda.eu",
    })
    _strip_dashes(data)  # aucun tiret cadratin (—) dans le rendu final
    _log_health(data)
    return data


def week_label_human(week_id: str) -> str:
    """'2026-W23' -> 'Semaine du 01/06 au 07/06/2026' (sans dépendance locale)."""
    try:
        year, wk = week_id.split("-W")
        monday = date.fromisocalendar(int(year), int(wk), 1)
        sunday = date.fromisocalendar(int(year), int(wk), 7)
        return f"Semaine du {monday:%d/%m} au {sunday:%d/%m/%Y}"
    except (ValueError, AttributeError):
        return f"Semaine {week_id}"


def call_anthropic(prompt: str, model: str) -> str | None:
    try:
        import anthropic
    except ImportError as exc:
        raise SystemExit(
            "Dépendance anthropic manquante. Exécuter : pip install -r requirements.txt"
        ) from exc

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY non définie. Arrêt.")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model=model,
            max_tokens=8192,
            system=(
                "Tu es l'assistant éditorial de Cultura Sabauda. Tu produis des "
                "synthèses économiques claires, factuelles et éditorialisées, en Markdown. "
                "Ton B2B, sérieux, sans buzzword."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIStatusError as exc:
        log.error("Erreur API Anthropic (%s) : %s", exc.status_code, exc)
        return None
    except anthropic.APIConnectionError as exc:
        log.error("Connexion à l'API Anthropic impossible : %s", exc)
        return None
    except Exception as exc:  # pragma: no cover
        log.error("Échec de l'appel Anthropic : %s", exc)
        return None

    return "".join(block.text for block in message.content if getattr(block, "type", "") == "text")


def write_markdown(target_week: str, content: str, total_items: int) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"{target_week}.md"
    header = (
        f"# Synthèse de veille — {target_week}\n\n"
        f"> Observatoire Économique de l'Espace Sabaudo\n"
        f"> Généré le {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} "
        f"à partir de {total_items} élément(s) de veille.\n"
        f"> **Brouillon — validation requise avant publication.**\n\n"
        "---\n\n"
    )
    out.write_text(header + content + "\n", encoding="utf-8")
    return out


def _log_version() -> None:
    """Affiche le commit git courant — permet de vérifier immédiatement quelle version tourne."""
    try:
        import subprocess
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
        branch = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
        log.info("▶ synthesize — commit %s (branche : %s)", commit, branch)
    except Exception:
        pass


def main() -> int:
    _log_version()
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Synthèse hebdomadaire de veille.")
    parser.add_argument(
        "--week",
        help="Semaine ISO cible au format AAAA-WNN (défaut : semaine courante).",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Téléverser la synthèse sur Google Drive après génération.",
    )
    parser.add_argument(
        "--brevo",
        action="store_true",
        help="Créer un BROUILLON de campagne Brevo à partir de la newsletter générée.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Créer le brouillon Brevo même si la sélection est courte (transmis à push_brevo).",
    )
    args = parser.parse_args()

    log.info("=== Démarrage synthèse hebdomadaire ===")
    all_weeks = load_all_records()
    target_week = select_week(all_weeks, args.week, datetime.now(timezone.utc))

    by_territory = all_weeks.get(target_week, {})
    counts = {t: len(v) for t, v in by_territory.items()}
    log.info("Semaine %s : %s", target_week, counts or "aucun élément")

    total_items = sum(len(v) for v in by_territory.values())
    if total_items == 0:
        log.warning("Aucun élément de veille pour la semaine %s. Pas de synthèse générée.", target_week)
        return 0

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    log.info("Appel Anthropic (%s) sur %d élément(s)…", model, total_items)
    registry = build_registry(by_territory)
    prompt = build_prompt(registry, target_week)
    content = call_anthropic(prompt, model)
    if not content:
        log.error("Synthèse non générée (erreur API). Arrêt.")
        return 1

    # Séparation : Markdown (archive Drive) + JSON structuré (newsletter)
    markdown, parsed = split_markdown_json(content)
    out = write_markdown(target_week, markdown, total_items)
    log.info("Synthèse écrite : %s", out)

    data = None
    if parsed:
        logo_url = os.getenv("BREVO_LOGO_URL", "")
        picto_url = os.getenv("BREVO_PICTO_URL", "")
        data = build_email_data(parsed, registry, week_label_human(target_week), logo_url, picto_url)
    if data:
        data_path = OUTPUT_DIR / f"{target_week}.json"
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Données newsletter écrites : %s", data_path)
    else:
        log.warning("Pas de données newsletter structurées (Brevo sera ignoré).")
    log.info("⚠ Validation de Franck requise avant toute publication.")

    if args.upload:
        from utils.drive_upload import upload_file

        subfolder = os.getenv("DRIVE_VEILLE_TRAITEE_SUBFOLDER", "02_Veille_traitee")
        file_id = upload_file(out, subfolder=subfolder)
        if file_id:
            log.info("Synthèse téléversée sur Drive (id=%s).", file_id)
        else:
            log.warning("Upload Drive échoué — le fichier local reste disponible.")

    if args.brevo and data:
        sys.path.insert(0, str(ROOT / "scripts"))
        from push_brevo import create_from_data

        create_from_data(data, force=args.force)
    elif args.brevo:
        log.warning("--brevo demandé mais aucune donnée structurée : brouillon non créé.")

    log.info("=== Fin synthèse hebdomadaire ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
