#!/usr/bin/env python3
"""Maquette de la newsletter Business Sabaudo (gabarit magazine) avec FAUX articles.

Sert à voir le rendu (fichier HTML) ou à déposer un BROUILLON de démonstration
dans Brevo, sans attendre de vraie veille. Contenus fictifs, images placeholder.

Usage :
    python scripts/demo_newsletter.py                    # écrit /tmp/demo_business_sabaudo.html
    python scripts/demo_newsletter.py --out chemin.html
    python scripts/demo_newsletter.py --brevo            # crée le BROUILLON dans Brevo
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.newsletter_variants import variant_magazine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def demo_data() -> dict:
    hero = {
        "title": "I3P ouvre son accélérateur à 10 startups deeptech",
        "summary": "L'incubateur du Politecnico di Torino lance son appel à candidatures. "
                   "Et alors ? Une fenêtre d'entrée pour les jeunes pousses du périmètre transfrontalier.",
        "url": "https://www.i3p.it/", "image": "https://picsum.photos/seed/i3p/600/300",
        "source": "I3P Torino", "domain": "i3p.it", "territory": "Piemonte",
    }
    items = [
        {"title": "La Côte d'Azur retrouve le moral des affaires",
         "summary": "Le baromètre de la CCI Nice repart à la hausse au 2ᵉ trimestre, porté par le tourisme d'affaires.",
         "url": "https://www.cote-azur.cci.fr/", "image": "https://picsum.photos/seed/nice/600/300",
         "source": "CCI Nice Côte d'Azur", "domain": "cote-azur.cci.fr", "territory": "Nice"},
        {"title": "French Tech in the Alps fait son networking dans le Genevois",
         "summary": "Pitchs et mise en relation transfrontalière entre startups et investisseurs.",
         "url": "https://www.lafrenchtech.com/", "image": "",
         "source": "French Tech Alpes", "domain": "lafrenchtech.com", "territory": "Savoie"},
        {"title": "Cinq projets entrent en pépinière en Vallée d'Aoste",
         "summary": "De l'agroalimentaire de montagne à la mobilité douce, une nouvelle promotion accompagnée.",
         "url": "https://www.pepinieresvda.eu/", "image": "https://picsum.photos/seed/ao/600/300",
         "source": "Pépinières VDA", "domain": "pepinieresvda.eu", "territory": "Vallee-Aoste"},
        {"title": "Alcotra prépare un appel à projets transition écologique",
         "summary": "Le programme Interreg France-Italie cible les territoires alpins transfrontaliers.",
         "url": "https://www.interreg-alcotra.eu/", "image": "https://picsum.photos/seed/al/600/300",
         "source": "Interreg Alcotra", "domain": "interreg-alcotra.eu", "territory": "Alcotra"},
    ]
    signaux = [
        {"title": "Turin muscle la deeptech (I3P)", "territory": "Piemonte"},
        {"title": "Conjoncture azuréenne en hausse au 2ᵉ trimestre", "territory": "Nice"},
        {"title": "Nouvel appel à projets Alcotra en préparation", "territory": "Alcotra"},
    ]
    ponts = [
        {"title": "Une PME valdôtaine décroche un marché à Lyon",
         "summary": "Le fabricant aostois ouvre un bureau commercial dans la métropole lyonnaise : "
                    "un pont concret entre la Vallée d'Aoste et le marché rhônalpin.",
         "url": "https://www.pepinieresvda.eu/", "image": "",
         "source": "Pépinières VDA", "domain": "pepinieresvda.eu", "territory": "Vallee-Aoste"},
        {"title": "Un projet de R&D relie Sophia-Antipolis et l'EPFL",
         "summary": "Laboratoires niçois et lausannois s'associent sur l'IA embarquée — "
                    "une coopération Nice–Suisse romande qui dépasse l'espace sabaudo.",
         "url": "https://www.cote-azur.cci.fr/", "image": "",
         "source": "CCI Nice Côte d'Azur", "domain": "cote-azur.cci.fr", "territory": "Nice"},
    ]
    return {
        "week_label": "Édition de démonstration",
        "logo_url": os.getenv("BREVO_LOGO_URL", ""),
        "pictogram_url": os.getenv("BREVO_PICTO_URL", ""),
        "preheader": "Turin accélère sur la deeptech, la Côte d'Azur rebondit, un appel Alcotra arrive.",
        "subject": "Business Sabaudo — édition de démonstration",
        "hero": hero,
        "signaux": signaux,
        "items": items,
        "ponts": ponts,
        "signature": "Bonne lecture,\nLa rédaction — Cultura Sabauda",
        "cta_url": "https://culturasabauda.eu",
    }


def main() -> int:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Maquette de newsletter (gabarit magazine).")
    parser.add_argument("--out", default="/tmp/demo_business_sabaudo.html", help="Fichier HTML de sortie.")
    parser.add_argument("--lang", default="fr", choices=["fr", "it"], help="Langue d'interface (défaut fr).")
    parser.add_argument("--territory", default="", help="Territoire d'ancrage (« Chez vous » en tête) : "
                        "Savoie, Piemonte, Vallee-Aoste, Nice. Vide = édition générale.")
    parser.add_argument("--brevo", action="store_true", help="Créer le BROUILLON de démonstration dans Brevo.")
    args = parser.parse_args()

    data = demo_data()
    data["lang"] = args.lang
    if args.territory:
        data["anchor"] = args.territory
    Path(args.out).write_text(variant_magazine(data), encoding="utf-8")
    print(f"Maquette écrite : {args.out} (lang={args.lang}, territoire={args.territory or '—'})")

    if args.brevo:
        sys.path.insert(0, str(ROOT / "scripts"))
        from push_brevo import create_from_data

        ids = create_from_data(data, force=True)
        print(f"Brouillon(s) Brevo : {'créé(s) id=' + ','.join(map(str, ids)) if ids else 'non créé (voir logs)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
