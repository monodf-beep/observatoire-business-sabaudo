#!/usr/bin/env python3
"""Script 3 — Synthèse hebdomadaire via l'API Anthropic.

- Entrée : fichiers JSON de la semaine ISO courante dans 01_Veille_brute/
- Appel API Anthropic (modèle configurable, défaut claude-sonnet-4-20250514)
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
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "01_Veille_brute"
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Bornes pour rester dans une enveloppe de tokens raisonnable
MAX_BODY_CHARS = 1500
MAX_ITEMS_PER_TERRITORY = 40

log = get_logger("synthesize")


def iso_week_id(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def load_week_records(target_week: str) -> dict[str, list[dict]]:
    """Charge les enregistrements de la semaine cible, groupés par territoire."""
    by_territory: dict[str, list[dict]] = defaultdict(list)
    if not INPUT_DIR.exists():
        log.warning("Dossier de veille brute absent : %s", INPUT_DIR)
        return by_territory

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
        if iso_week_id(dt) != target_week:
            continue
        # Territoire : champ explicite (RSS) ou déduit du dossier parent (Gmail)
        territory = record.get("territoire") or _territory_from_path(json_file)
        by_territory[territory].append(record)

    counts = {t: len(v) for t, v in by_territory.items()}
    log.info("Semaine %s : %s", target_week, counts or "aucun élément")
    return by_territory


def _territory_from_path(json_file: Path) -> str:
    # Dossier au format AAAA-MM-Territoire (le territoire peut contenir un tiret,
    # ex. Vallee-Aoste) → on découpe seulement sur les deux premiers tirets.
    parts = json_file.parent.name.split("-", 2)
    return parts[2] if len(parts) == 3 else "Indetermine"


def build_prompt(by_territory: dict[str, list[dict]], target_week: str) -> str:
    lines: list[str] = []
    for territory in sorted(by_territory):
        items = by_territory[territory][:MAX_ITEMS_PER_TERRITORY]
        lines.append(f"\n## Territoire : {territory} ({len(items)} élément(s))")
        for i, rec in enumerate(items, 1):
            title = rec.get("title", "(sans titre)")
            origin = rec.get("from") or rec.get("feed_title") or rec.get("feed_url", "")
            date = rec.get("date", "")[:10]
            body = (rec.get("body") or "").strip()[:MAX_BODY_CHARS]
            link = rec.get("link", "")
            lines.append(f"\n### [{i}] {title}")
            lines.append(f"- Source : {origin} | Date : {date}")
            if link:
                lines.append(f"- Lien : {link}")
            if body:
                lines.append(f"- Contenu : {body}")
    corpus = "\n".join(lines)

    # Prompt issu du brief Sprint 1 (intégré dans le code, pas de fichier externe).
    instructions = (
        "Tu es l'assistant éditorial de Cultura Sabauda, média culturel et économique\n"
        "de l'espace sabaudo (Savoie, Piémont, Vallée d'Aoste, Nice).\n\n"
        "À partir des contenus collectés cette semaine (emails newsletters + flux RSS),\n"
        "produis une synthèse structurée en Markdown :\n\n"
        "1. SIGNAUX FORTS (5 maximum)\n"
        "   - Un titre accrocheur par signal\n"
        "   - 2-3 phrases de contexte\n"
        "   - Territoire concerné\n"
        "   - Source\n\n"
        "2. PAR TERRITOIRE\n"
        "   - Savoie (73+74)\n"
        "   - Piémont\n"
        "   - Vallée d'Aoste\n"
        "   - Nice / Alpes-Maritimes\n"
        "   - Périmètre Alcotra\n\n"
        "3. DRAFT NEWSLETTER \"Business Sabaudo\"\n"
        "   - Objet email (max 60 caractères)\n"
        "   - Intro (2 phrases, ton éditorial, pas communiqué de presse)\n"
        "   - 5 à 7 brèves éditorialisées (pas de copier-coller de titres)\n"
        "   - Signature\n\n"
        "Tonalité : sérieux, B2B, sans buzzword. Analyse, pas relation presse.\n"
        "Langue : français (avec termes italiens conservés quand pertinents).\n"
        "Reste factuel, n'invente aucune information absente des sources.\n"
    )
    return (
        f"{instructions}\n"
        f"=== CONTENUS COLLECTÉS — semaine {target_week} ===\n"
        f"{corpus}\n"
    )


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
            max_tokens=4096,
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
    args = parser.parse_args()

    log.info("=== Démarrage synthèse hebdomadaire ===")
    target_week = args.week or iso_week_id(datetime.now(timezone.utc))

    by_territory = load_week_records(target_week)
    total_items = sum(len(v) for v in by_territory.values())
    if total_items == 0:
        log.warning("Aucun élément de veille pour la semaine %s. Pas de synthèse générée.", target_week)
        return 0

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    log.info("Appel Anthropic (%s) sur %d élément(s)…", model, total_items)
    prompt = build_prompt(by_territory, target_week)
    content = call_anthropic(prompt, model)
    if not content:
        log.error("Synthèse non générée (erreur API). Arrêt.")
        return 1

    out = write_markdown(target_week, content, total_items)
    log.info("Synthèse écrite : %s", out)
    log.info("⚠ Validation de Franck requise avant toute publication.")

    if args.upload:
        from utils.drive_upload import upload_file

        subfolder = os.getenv("DRIVE_VEILLE_TRAITEE_SUBFOLDER", "02_Veille_traitee")
        file_id = upload_file(out, subfolder=subfolder)
        if file_id:
            log.info("Synthèse téléversée sur Drive (id=%s).", file_id)
        else:
            log.warning("Upload Drive échoué — le fichier local reste disponible.")

    log.info("=== Fin synthèse hebdomadaire ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
