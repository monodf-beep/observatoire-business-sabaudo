#!/usr/bin/env python3
"""Génère une maquette de newsletter Business Sabaudo avec de FAUX articles.

Sert à travailler le design du brouillon sans attendre de vraies données.
Les images sont des placeholders (picsum.photos) ; les contenus sont fictifs.

Usage :
    python scripts/demo_newsletter.py                    # écrit /tmp/demo_business_sabaudo.html
    python scripts/demo_newsletter.py --out chemin.html  # fichier de sortie au choix
    python scripts/demo_newsletter.py --brevo            # crée aussi le BROUILLON dans Brevo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.newsletter_template import render_newsletter  # noqa: E402

# --- Faux articles (contenu illustratif, à remplacer par la vraie veille) ---
DEMO_ITEMS = [
    {
        "title": "I3P lance un appel à candidatures pour 10 startups deeptech",
        "summary": "L'incubateur du Politecnico di Torino ouvre son programme d'accélération. "
                   "Dotation, mentorat et accès au réseau d'investisseurs piémontais à la clé.",
        "url": "https://www.i3p.it/",
        "image": "https://picsum.photos/seed/i3p/600/300",
        "source": "I3P Torino",
        "territory": "Piemonte",
        "logo": None,
    },
    {
        "title": "La CCI Nice Côte d'Azur publie son baromètre de conjoncture",
        "summary": "Le moral des dirigeants azuréens repart à la hausse au 2ᵉ trimestre, "
                   "porté par le tourisme d'affaires et les services numériques.",
        "url": "https://www.cote-azur.cci.fr/",
        "image": "https://picsum.photos/seed/nice/600/300",
        "source": "CCI Nice Côte d'Azur",
        "territory": "Nice",
        "logo": None,
    },
    {
        "title": "French Tech in the Alps : soirée networking dans le Genevois",
        "summary": "Rendez-vous des startups et investisseurs du Genevois français. "
                   "Pitchs, retours d'expérience et mise en relation transfrontalière.",
        "url": "https://www.lafrenchtech.com/",
        "image": "https://picsum.photos/seed/frenchtech/600/300",
        "source": "French Tech Alpes",
        "territory": "Savoie",
        "logo": None,
    },
    {
        "title": "Vallée d'Aoste : 5 nouveaux projets entrent en pépinière",
        "summary": "Les pépinières d'entreprises de la Vallée d'Aoste accueillent cinq jeunes "
                   "sociétés, de l'agroalimentaire de montagne à la mobilité douce.",
        "url": "https://www.pepinieresvda.eu/",
        "image": "https://picsum.photos/seed/aoste/600/300",
        "source": "Pépinières VDA",
        "territory": "Vallee-Aoste",
        "logo": None,
    },
    {
        "title": "Alcotra : nouvel appel à projets de coopération France-Italie",
        "summary": "Le programme Interreg Alcotra prépare un appel dédié à la transition "
                   "écologique des territoires alpins transfrontaliers.",
        "url": "https://www.interreg-alcotra.eu/",
        "image": "https://picsum.photos/seed/alcotra/600/300",
        "source": "Interreg Alcotra",
        "territory": "Alcotra",
        "logo": None,
    },
]


def build_demo_html() -> str:
    return render_newsletter(
        title="Business Sabaudo",
        subtitle="La veille économique de l'espace sabaudo",
        week_label="Édition de démonstration",
        intro="Bonjour, voici votre rendez-vous hebdomadaire avec l'actualité économique de "
              "la Savoie, du Piémont, de la Vallée d'Aoste, de Nice et du périmètre Alcotra.",
        items=DEMO_ITEMS,
        signature="Bonne lecture,\nLa rédaction — Cultura Sabauda",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Maquette de newsletter avec faux articles.")
    parser.add_argument("--out", default="/tmp/demo_business_sabaudo.html", help="Fichier HTML de sortie.")
    parser.add_argument("--brevo", action="store_true", help="Créer aussi le brouillon dans Brevo.")
    args = parser.parse_args()

    html = build_demo_html()
    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"Maquette écrite : {out}")

    if args.brevo:
        import os

        from dotenv import load_dotenv

        from utils.brevo import BrevoError, campaign_edit_url, create_draft_campaign

        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        try:
            cid = create_draft_campaign(
                api_key=os.environ["BREVO_API_KEY"],
                name="Business Sabaudo — DÉMO (maquette)",
                subject="Business Sabaudo — édition de démonstration",
                sender_name=os.getenv("BREVO_SENDER_NAME", "Cultura Sabauda"),
                sender_email=os.environ["BREVO_SENDER_EMAIL"],
                list_ids=[int(x) for x in os.getenv("BREVO_LIST_ID", "2").split(",") if x.strip().isdigit()],
                html_content=html,
            )
            print(f"Brouillon Brevo créé (id={cid}) : {campaign_edit_url(cid)}")
        except (BrevoError, KeyError) as exc:
            print(f"Brevo : brouillon non créé ({exc})")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
