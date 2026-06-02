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
OUTPUT_DIR = ROOT / "02_Veille_traitée" / "Synthèses_hebdomadaires"
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
    # Dossier au format AAAA-MM-Territoire
    parts = json_file.parent.name.split("-")
    return parts[-1] if len(parts) >= 3 else "Indetermine"


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

    return (
        "Tu es analyste pour l'Observatoire Économique de l'Espace Sabaudo "
        "(Savoie, Piémont, Vallée d'Aoste, Nice). À partir des éléments de veille "
        f"de la semaine {target_week} ci-dessous, rédige en français une synthèse "
        "structurée en Markdown comportant EXACTEMENT ces sections :\n\n"
        "1. `## Synthèse par territoire` — un paragraphe d'analyse par territoire "
        "présent (Savoie, Piémont, Vallée d'Aoste, Nice), mettant en avant les "
        "dynamiques économiques, dispositifs et acteurs clés.\n"
        "2. `## 5 signaux forts de la semaine` — liste numérotée des 5 signaux les "
        "plus significatifs (tendances, opportunités, alertes), chacun avec une "
        "phrase d'explication.\n"
        "3. `## Draft newsletter` — un brouillon de newsletter prêt à relire "
        "(titre accrocheur, chapô, 3 à 5 brèves), ton professionnel et accessible.\n\n"
        "Reste factuel, n'invente aucune information absente des sources. "
        "Si un territoire n'a aucun élément, indique-le brièvement.\n\n"
        "=== ÉLÉMENTS DE VEILLE ===\n"
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
                "Tu es un analyste économique territorial rigoureux. "
                "Tu produis des synthèses claires, factuelles, en Markdown."
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

        file_id = upload_file(out)
        if file_id:
            log.info("Synthèse téléversée sur Drive (id=%s).", file_id)
        else:
            log.warning("Upload Drive échoué — le fichier local reste disponible.")

    log.info("=== Fin synthèse hebdomadaire ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
