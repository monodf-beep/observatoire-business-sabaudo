#!/usr/bin/env python3
"""Diagnostic : la recherche web automatique (photo + lien) fonctionne-t-elle ?

À lancer sur le VPS pour vérifier que l'outil de recherche web d'Anthropic est
bien disponible (anthropic>=0.49.0, clé API, accès réseau). Affiche l'erreur
exacte en cas de problème — utile quand la une retombe sur une bannière ou qu'un
lien « Lire l'article » reste vide.

Exemples :
    python -m scripts.test_autofind \
        --titre "Universite Cote d'Azur structure son reseau pour financer l'innovation" \
        --acteur "Universite Cote d'Azur" --territoire Nice
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from utils.logger import get_logger  # noqa: E402

log = get_logger("test_autofind")
DEFAULT_MODEL = "claude-sonnet-4-6"


def main() -> int:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser(description="Teste la recherche web (photo + lien).")
    p.add_argument("--titre", required=True, help="Titre de l'article.")
    p.add_argument("--acteur", required=True, help="Acteur primaire (entreprise/institution).")
    p.add_argument("--territoire", default="", help="Savoie | Piemonte | Vallee-Aoste | Nice | Alcotra")
    args = p.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)

    print("=== Environnement ===")
    try:
        import anthropic
        print(f"anthropic         : {anthropic.__version__}")
    except ImportError:
        print("anthropic         : ABSENT (pip install -r requirements.txt)")
        return 1
    print(f"ANTHROPIC_API_KEY : {'présente' if api_key else 'ABSENTE'}")
    print(f"modèle            : {model}")
    print(f"AUTO_PHOTO        : {os.getenv('AUTO_PHOTO', '1')}")
    print(f"AUTO_SOURCE       : {os.getenv('AUTO_SOURCE', '1')}")
    if not api_key:
        print("\n⚠ Pas de clé API : la recherche web ne peut pas fonctionner.")
        return 1

    # 1) Test brut de l'outil de recherche web (révèle un SDK trop ancien / un refus API)
    print("\n=== Test direct de l'outil web_search ===")
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content":
                       f"Recherche le site officiel de « {args.acteur} ». "
                       "Donne juste l'URL trouvée."}],
        )
        txt = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        print("OK — réponse :", (txt[:300] or "(vide)"))
    except Exception as exc:
        print(f"ÉCHEC — {type(exc).__name__}: {exc}")
        print("\n→ Cause probable : anthropic trop ancien (besoin >=0.49.0) ou outil "
              "non activé sur le compte. Faire : pip install -U -r requirements.txt")
        return 1

    # 2) Chaîne complète photo
    print("\n=== Recherche PHOTO (photo_finder) ===")
    from utils.photo_finder import find_actor_photo
    photo = find_actor_photo(args.acteur, args.territoire, args.titre, api_key=api_key, model=model)
    print("photo :", photo or "(aucune)")

    # 3) Chaîne complète lien
    print("\n=== Recherche LIEN (source_finder) ===")
    from utils.sources import load_press_domains
    from utils.source_finder import find_canonical_link
    link = find_canonical_link(args.titre, args.acteur, args.territoire,
                               press=load_press_domains(), api_key=api_key, model=model)
    print("lien  :", link or "(aucun)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
