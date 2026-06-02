#!/usr/bin/env python3
"""Génère 3 variantes de maquette de la newsletter Business Sabaudo (faux articles).

Usage :
    python scripts/demo_variants.py            # écrit 3 fichiers dans /tmp
    python scripts/demo_variants.py --dir DOSSIER
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.newsletter_variants import (  # noqa: E402
    variant_digest,
    variant_editorial,
    variant_magazine,
)

# Domaines réels -> favicons officiels utilisés comme logos.
ITEMS = [
    {
        "title": "I3P ouvre son accélérateur à 10 startups deeptech",
        "summary": "L'incubateur du Politecnico di Torino lance son appel à candidatures : "
                   "dotation, mentorat et accès au réseau d'investisseurs piémontais.",
        "url": "https://www.i3p.it/", "image": "https://picsum.photos/seed/i3p/600/300",
        "source": "I3P Torino", "domain": "i3p.it", "territory": "Piemonte",
    },
    {
        "title": "CCI Nice : le moral des dirigeants azuréens repart à la hausse",
        "summary": "Le baromètre du 2ᵉ trimestre est porté par le tourisme d'affaires "
                   "et les services numériques sur la Côte d'Azur.",
        "url": "https://www.cote-azur.cci.fr/", "image": "https://picsum.photos/seed/nice/600/300",
        "source": "CCI Nice Côte d'Azur", "domain": "cote-azur.cci.fr", "territory": "Nice",
    },
    {
        "title": "French Tech in the Alps : soirée networking dans le Genevois",
        "summary": "Pitchs, retours d'expérience et mise en relation transfrontalière "
                   "entre startups et investisseurs du Genevois français.",
        "url": "https://www.lafrenchtech.com/", "image": "https://picsum.photos/seed/ft/600/300",
        "source": "French Tech Alpes", "domain": "lafrenchtech.com", "territory": "Savoie",
    },
    {
        "title": "Vallée d'Aoste : cinq projets entrent en pépinière",
        "summary": "De l'agroalimentaire de montagne à la mobilité douce, les pépinières "
                   "VDA accueillent une nouvelle promotion d'entrepreneurs.",
        "url": "https://www.pepinieresvda.eu/", "image": "https://picsum.photos/seed/ao/600/300",
        "source": "Pépinières VDA", "domain": "pepinieresvda.eu", "territory": "Vallee-Aoste",
    },
    {
        "title": "Alcotra prépare un appel à projets transition écologique",
        "summary": "Le programme Interreg France-Italie cible les territoires alpins "
                   "transfrontaliers pour son prochain appel.",
        "url": "https://www.interreg-alcotra.eu/", "image": "https://picsum.photos/seed/al/600/300",
        "source": "Interreg Alcotra", "domain": "interreg-alcotra.eu", "territory": "Alcotra",
    },
]

SIGNAUX = [
    {"title": "Turin accélère sur la deeptech (I3P)", "territory": "Piemonte"},
    {"title": "Conjoncture azuréenne en hausse au T2", "territory": "Nice"},
    {"title": "Nouvel appel à projets Alcotra en vue", "territory": "Alcotra"},
]

DATA = {
    "week_label": "Édition de démonstration",
    "preheader": "Turin accélère sur la deeptech, la Côte d'Azur rebondit, et un nouvel appel Alcotra arrive.",
    "intro": "Tour d'horizon de l'actualité économique de l'espace sabaudo : "
             "Savoie, Piémont, Vallée d'Aoste, Nice et périmètre Alcotra.",
    "edito": "Cette semaine, l'innovation tient le haut de l'affiche : Turin muscle son "
             "accélérateur, la Côte d'Azur retrouve le sourire et la coopération transfrontalière "
             "se prépare un nouveau rendez-vous. Notre sélection pour aller à l'essentiel.",
    "signature": "Bonne lecture,\nLa rédaction — Cultura Sabauda",
    "cta_url": "https://culturasabauda.eu",
    "hero": ITEMS[0],
    "signaux": SIGNAUX,
    "items": ITEMS[1:],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="3 variantes de maquette newsletter.")
    parser.add_argument("--dir", default="/tmp", help="Dossier de sortie.")
    args = parser.parse_args()

    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    variants = {
        "variante_1_magazine.html": variant_magazine,
        "variante_2_digest.html": variant_digest,
        "variante_3_editorial.html": variant_editorial,
    }
    for name, fn in variants.items():
        path = out / name
        path.write_text(fn(DATA), encoding="utf-8")
        print(f"Écrit : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
