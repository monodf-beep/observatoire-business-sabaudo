"""Conseiller « Franck, voici ce que TU dois faire » — version Observatoire.

Inspiré de l'advisor de l'agrégateur d'événements (monodf-beep/evenements). Traduit
l'état de la veille en ACTIONS HUMAINES prioritaires : on n'affiche QUE ce qui n'est
pas automatique (valider une source proposée, générer la newsletter manquante, sourcer
un territoire vide, relancer une collecte). Tout le reste se fait seul.

Aucune dépendance lourde : lit un résumé précalculé (logs/veille_summary.json, écrit
par build_dashboard), le registre des newsletters, la présence de la synthèse de la
semaine, et l'alerte crédit. Fail-safe : un fichier absent = un message en moins,
jamais une erreur.

Chaque message : {level, icon, title, detail}. level ∈ {valider, sourcer, lancer}.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_FILE = ROOT / "logs" / "veille_summary.json"
SYNTH_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"

# --- Seuils (recalibrables) ---
LOW_VOLUME = 40          # en dessous : trop peu de sujets captés cette semaine
_ORDER = {"valider": 0, "sourcer": 1, "lancer": 2}

_TERR_LABELS = {
    "Savoie": "Savoie", "Piemonte": "Piémont", "Vallee-Aoste": "Vallée d'Aoste",
    "Nice": "Nice", "Alcotra": "Alcotra",
}
_TERR_ORDER = ["Savoie", "Piemonte", "Vallee-Aoste", "Nice", "Alcotra"]


def _iso_week(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _load_summary() -> dict:
    try:
        return json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def advise(pending_suggestions: int = 0) -> list[dict]:
    """Liste ordonnée (plus urgent d'abord) des actions humaines pour l'Observatoire."""
    msgs: list[dict] = []
    summary = _load_summary()
    week = summary.get("week") or _iso_week(datetime.now(timezone.utc))

    # 1. VALIDER — des sources ont été proposées sur la page publique.
    if pending_suggestions:
        msgs.append({
            "level": "valider", "icon": "📥",
            "title": f"Valide {pending_suggestions} source(s) proposée(s).",
            "detail": "Des lecteurs ont suggéré des sources — accepte ou rejette dans « Sources proposées ».",
        })

    # 2. LANCER — aucune newsletter générée pour la semaine en cours.
    if not (SYNTH_DIR / f"{week}.json").exists():
        msgs.append({
            "level": "lancer", "icon": "✉",
            "title": "Aucune newsletter générée cette semaine.",
            "detail": "Clique « Générer la newsletter » pour produire le brouillon Brevo et l'encart de synthèse.",
        })

    # 3. SOURCER — un territoire n'a aucun sujet cette semaine.
    terr_counts = summary.get("terr_counts") or {}
    if terr_counts:  # on n'alerte que si on a un résumé fiable
        for terr in _TERR_ORDER:
            if terr_counts.get(terr, 0) == 0:
                label = _TERR_LABELS.get(terr, terr)
                msgs.append({
                    "level": "sourcer", "icon": "📍",
                    "title": f"Aucun sujet capté en {label} cette semaine.",
                    "detail": "La page montre les 5 territoires : un territoire vide se voit. Ajoute une source (RSS, newsletter, scraping).",
                })

    # (Les newsletters « muettes cette semaine » ne sont PAS une action — elles peuvent
    # avoir une cadence mensuelle. L'info « ○ rien cette semaine » figure déjà dans le
    # tableau des abonnements de la page publique. On ne pollue pas l'advisor avec ça.)

    # 4. LANCER — peu de sujets captés (fond de stock bas).
    total = summary.get("total")
    if isinstance(total, int) and total < LOW_VOLUME:
        msgs.append({
            "level": "lancer", "icon": "📡",
            "title": f"Peu de sujets captés cette semaine ({total}).",
            "detail": "Relance une collecte (RSS / scraping) ou ajoute des sources pour réalimenter la veille.",
        })

    msgs.sort(key=lambda m: _ORDER.get(m["level"], 9))
    return msgs
