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
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "01_Veille_brute"
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"
# Synthèse éditoriale (1 appel/sem, qualité critique) → modèle le plus capable.
DEFAULT_MODEL = "claude-opus-4-8"
# Recherche de liens officiels (≈10 appels/sem, tâche simple) → modèle économique.
DEFAULT_SEARCH_MODEL = "claude-haiku-4-5"

# Bornes pour rester dans une enveloppe de tokens raisonnable
MAX_BODY_CHARS = 1500
MAX_BODY_EMAIL_CHARS = 6000   # une newsletter est un digest long (plusieurs sujets)
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
            is_email = rec.get("source") == "gmail"
            # Une newsletter est un digest long (plusieurs sujets) : on lui laisse
            # beaucoup plus de place qu'à un item RSS mono-sujet.
            budget = MAX_BODY_EMAIL_CHARS if is_email else MAX_BODY_CHARS
            body = (rec.get("body") or "").strip()[:budget]
            link = rec.get("link", "")
            kind = "Newsletter (digest — peut contenir plusieurs sujets)" if is_email else "Flux"
            lines.append(f"\n### [#{rid}] {rec.get('title', '(sans titre)')}")
            lines.append(f"- Type : {kind} | Source : {origin} | Date : {date}")
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
        '    "signature": "Bonne lecture,\\nLa rédaction — Cultura Sabauda"\n'
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
        "  - NEWSLETTERS (éléments « Type : Newsletter ») : ce sont des DIGESTS qui\n"
        "    regroupent PLUSIEURS sujets distincts. Lis le contenu en entier et extrais\n"
        "    CHAQUE sujet à valeur économique comme une brève séparée — tu PEUX produire\n"
        "    plusieurs brèves à partir du même [#id] (une par sujet). N'en tire pas une\n"
        "    seule brève générique : ces emails sont la matière la plus riche de la semaine.\n"
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
            official: dict[str, str] | None = None) -> dict | None:
    """Complète une entrée {id,titre,resume,acteur} avec lien/source/image d'origine.

    Si la source est un média de presse (config/press_domains.txt), on n'expose
    NI lien, NI logo, NI image : on attribue à l'acteur primaire (pas de pub au
    journal). Si l'acteur figure dans l'annuaire des sites officiels (curé), on
    note son DOMAINE dans '_official_domain' ; l'article précis sera retrouvé plus
    tard (build_email_data). Sinon (source institutionnelle), on crédite/lie.
    """
    from utils.sources import domain_of, is_press, resolve_official, source_label

    rec = registry.get(int(entry.get("id", -1))) if str(entry.get("id", "")).strip().lstrip("-").isdigit() else None
    if rec is None:
        return None
    domain = domain_of(rec)
    actor = (entry.get("acteur") or "").strip()
    base = {
        "title": entry.get("titre") or rec.get("title", ""),
        "summary": entry.get("resume", ""),
        "territory": rec.get("territoire", "Indetermine"),
    }
    if is_press(domain, press):
        # Radar : on garde l'info, on retire tout ce qui crédite/promeut le journal.
        base.update({"url": "", "image": "", "domain": "", "source": actor})
        # Domaine officiel de l'acteur, si curé → l'article précis sera cherché après.
        off_domain = resolve_official(actor, base["title"], official or {})
        if off_domain:
            base["_official_domain"] = off_domain
    else:
        base.update({
            "url": rec.get("link", ""),
            "image": rec.get("image", ""),
            "domain": domain,
            "source": entry.get("acteur") or source_label(rec),
        })
    return base


# Motifs d'images « génériques » (logo / visuel social / placeholder) : acceptables
# en vignette de carte, mais à ÉVITER en une (on veut une vraie photo du sujet).
_GENERIC_IMAGE_TOKENS = (
    "social-image", "social_image", "/social/", "sharing", "share-image",
    "/logo", "logo.", "default", "placeholder", "fallback", "og-default", "generic",
)


def _is_generic_image(url: str) -> bool:
    u = (url or "").lower()
    return any(tok in u for tok in _GENERIC_IMAGE_TOKENS)


def _genuine_photo(entry: dict) -> bool:
    """Vrai si l'entrée porte une vraie photo du sujet (pas une image générique)."""
    img = entry.get("image") or ""
    return bool(img) and not _is_generic_image(img)


def build_email_data(parsed: dict, registry: dict[int, dict], week_label: str,
                     logo_url: str, picto_url: str = "") -> dict | None:
    """Construit le dict attendu par variant_magazine à partir du JSON de Claude."""
    from utils.sources import load_official_links, load_press_domains
    press = load_press_domains()
    official = load_official_links()

    une = parsed.get("une") or {}
    hero = _enrich(une, registry, press, official)
    items = [d for e in parsed.get("articles", []) if (d := _enrich(e, registry, press, official))]
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

    # Lien « site officiel » pour les brèves radar (opt-in OFFICIAL_LINK_SEARCH) :
    # acteur curé → article PRÉCIS sur son domaine ; sinon → recherche généralisée
    # du site officiel de l'acteur (presse et réseaux sociaux exclus). On ne lie
    # JAMAIS un journal : on attribue et on lie l'acteur.
    from utils import official_search
    if official_search.is_enabled():
        # Tâche simple et répétée → modèle économique (surchargeable).
        model = os.getenv("OFFICIAL_SEARCH_MODEL", DEFAULT_SEARCH_MODEL)
        for entry in ([hero] if hero else []) + items:
            if entry.get("url"):
                continue  # déjà un lien (brève institutionnelle)
            actor = entry.get("source", "")
            if not actor:
                continue
            title, summary = entry.get("title", ""), entry.get("summary", "")
            dom = entry.get("_official_domain")
            url = ""
            if dom:  # acteur dans l'annuaire curé → article précis sur SON domaine
                url = official_search.find_article_url(actor, title, summary, dom, model)
            if not url:  # pas d'annuaire (ou rien trouvé) → site officiel de l'acteur
                url = official_search.find_actor_official_url(actor, title, summary, press, model)
            if not url:
                continue
            # On VALIDE le lien avant de l'attacher : un 404 (URL malformée renvoyée
            # par la recherche) est abandonné → la brève reste radar plutôt que de
            # porter un lien mort. Page accessible → on en tire aussi l'og:image.
            final_url, html, status = official_search.fetch_page(url)
            if status == "notfound":
                log.info("Lien officiel abandonné (page inexistante) : %s", url)
                continue
            link_domain = urlparse(final_url).netloc.lower().removeprefix("www.")
            entry.update({"url": final_url, "domain": link_domain, "cta_label": "Sur le site officiel"})
            log.info("Lien officiel trouvé : %s", final_url)
            # Vraie photo du sujet : og:image de la page (repli bannière plus bas).
            if html and not entry.get("image"):
                og = official_search.og_image_from_html(html, final_url)
                if og:
                    entry["image"] = og
                    log.info("Image officielle (og:image) : %s", og)
    # On retire le champ technique avant sérialisation/rendu.
    for entry in ([hero] if hero else []) + items:
        entry.pop("_official_domain", None)

    # Garde-fou QUALITÉ : la une doit porter une VRAIE photo du sujet (pas une
    # bannière, pas un visuel générique type logo/social). Si la une choisie par le
    # modèle n'en a pas, on promeut la meilleure brève qui en a une — en privilégiant
    # celle qui a AUSSI un lien (vraie photo + lien = la vitrine idéale). L'ancienne
    # une passe en tête des brèves : elle reste visible.
    if hero and not _genuine_photo(hero):
        best_i, best_rank = None, 0
        for i, it in enumerate(items):
            if not _genuine_photo(it):
                continue
            rank = 2 + (1 if it.get("url") else 0)  # 3 = photo+lien, 2 = photo seule
            if rank > best_rank:
                best_rank, best_i = rank, i
        if best_i is not None:
            promoted = items.pop(best_i)
            items.insert(0, hero)
            hero = promoted
            log.info("Une promue (vraie photo%s) : %s",
                     " + lien" if hero.get("url") else "", hero["title"])
        else:
            log.warning("Aucune brève avec vraie photo : la une restera en bannière.")

    # Images de substitution par territoire quand l'image d'origine manque
    # (presse sans image réutilisable, ou flux sans visuel).
    from utils.sources import load_territory_images, pick_image
    terr_images = load_territory_images()
    if hero and not hero.get("image"):
        hero["image"] = pick_image(hero["territory"], hero["title"], terr_images)
    for it in items:
        if not it.get("image"):
            it["image"] = pick_image(it["territory"], it["title"], terr_images)

    return {
        "week_label": week_label,
        "logo_url": logo_url,
        "pictogram_url": picto_url,
        "preheader": parsed.get("preheader", ""),
        "subject": (parsed.get("objet") or f"Business Sabaudo — {week_label}")[:120],
        "hero": hero,
        "signaux": signaux,
        "items": items,
        "signature": parsed.get("signature", "La rédaction — Cultura Sabauda"),
        "cta_url": "https://culturasabauda.eu",
    }


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


def main() -> int:
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
        from utils.drive_upload import upload_file, upload_markdown_as_gdoc

        subfolder = os.getenv("DRIVE_VEILLE_TRAITEE_SUBFOLDER", "02_Veille_traitee")
        # Archive Markdown (matière brute, réutilisable par le tableau de bord)
        file_id = upload_file(out, subfolder=subfolder)
        if file_id:
            log.info("Archive Markdown téléversée sur Drive (id=%s).", file_id)
        else:
            log.warning("Upload Drive échoué — le fichier local reste disponible.")
        # Version lisible : Google Doc natif mis en forme (titres, listes, liens)
        doc_name = f"Business Sabaudo — {week_label_human(target_week)}"
        doc_id = upload_markdown_as_gdoc(out, subfolder=subfolder, name=doc_name)
        if doc_id:
            log.info("Synthèse déposée en Google Doc : « %s » (id=%s).", doc_name, doc_id)
        else:
            log.warning("Création du Google Doc échouée — l'archive Markdown reste disponible.")

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
