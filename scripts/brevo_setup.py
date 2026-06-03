#!/usr/bin/env python3
"""Configure Brevo pour la personnalisation de la newsletter Business Sabaudo.

Crée, de façon IDEMPOTENTE et NON DESTRUCTIVE (jamais de suppression) :

- les ATTRIBUTS de contact qui pilotent la personnalisation :
    · LANGUE      (texte)  -> FR / IT
    · TERRITOIRE  (texte)  -> Savoie / Piemonte / Vallee-Aoste / Nice
    · SECTEURS    (texte)  -> mots-clés libres (deeptech, industrie, tourisme…)
- un DOSSIER de listes « Business Sabaudo » et, dedans, les LISTES par langue
  (FR / IT) — point de départ recommandé (modèle A : une campagne par segment).

Ces attributs sont la fondation COMMUNE à tous les modèles de personnalisation
(segments, contenu conditionnel, page web) : on les crée sans présumer du choix.

Configuration (.env) : BREVO_API_KEY (indispensable).

Usage :
    python scripts/brevo_setup.py --check        # état actuel (attributs/listes), sans rien créer
    python scripts/brevo_setup.py --dry-run      # montre ce qui SERAIT créé, sans appeler l'API en écriture
    python scripts/brevo_setup.py                # applique (idempotent : ne recrée pas l'existant)
    python scripts/brevo_setup.py --no-lists     # n'agir que sur les attributs (pas de listes)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.brevo import (  # noqa: E402
    BrevoError,
    create_attribute,
    create_folder,
    create_list,
    list_attributes,
    list_contact_lists,
    list_folders,
)
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
log = get_logger("brevo_setup")

# Attributs de contact à garantir : nom -> (type Brevo, description, valeurs attendues).
ATTRIBUTES: dict[str, tuple[str, str, str]] = {
    "LANGUE": ("text", "Langue d'envoi de la newsletter", "FR | IT"),
    "TERRITOIRE": ("text", "Territoire d'ancrage du lecteur (remonte en tête)",
                   "Savoie | Piemonte | Vallee-Aoste | Nice"),
    "SECTEURS": ("text", "Centres d'intérêt (mots-clés libres, séparés par des virgules)",
                 "ex. deeptech,industrie,tourisme,agroalimentaire,finance"),
}

FOLDER_NAME = "Business Sabaudo"
# Listes par langue (modèle A). Le libellé sert de clé d'idempotence.
LANGUAGE_LISTS = [
    "Business Sabaudo — FR",
    "Business Sabaudo — IT",
]


def ensure_attributes(api_key: str, *, apply: bool) -> None:
    existing = {a.get("name", "").upper() for a in list_attributes(api_key)}
    for name, (attr_type, desc, values) in ATTRIBUTES.items():
        if name in existing:
            log.info("  [=] attribut %-10s déjà présent", name)
            continue
        if not apply:
            log.info("  [+] attribut %-10s (%s) À CRÉER — valeurs : %s", name, attr_type, values)
            continue
        try:
            create_attribute(api_key, name, attr_type=attr_type)
            log.info("  [✓] attribut %-10s créé (%s) — %s", name, attr_type, desc)
        except BrevoError as exc:
            log.error("  [x] attribut %s : %s", name, exc)


def ensure_lists(api_key: str, *, apply: bool) -> None:
    folders = {f.get("name", ""): f.get("id") for f in list_folders(api_key)}
    folder_id = folders.get(FOLDER_NAME)
    if folder_id is None:
        if not apply:
            log.info("  [+] dossier « %s » À CRÉER", FOLDER_NAME)
        else:
            try:
                folder_id = create_folder(api_key, FOLDER_NAME)
                log.info("  [✓] dossier « %s » créé (id=%s)", FOLDER_NAME, folder_id)
            except BrevoError as exc:
                log.error("  [x] dossier « %s » : %s", FOLDER_NAME, exc)
                return
    else:
        log.info("  [=] dossier « %s » déjà présent (id=%s)", FOLDER_NAME, folder_id)

    existing = {lst.get("name", "") for lst in list_contact_lists(api_key)}
    for name in LANGUAGE_LISTS:
        if name in existing:
            log.info("  [=] liste « %s » déjà présente", name)
            continue
        if not apply:
            log.info("  [+] liste « %s » À CRÉER (dossier %s)", name, FOLDER_NAME)
            continue
        if folder_id is None:
            log.warning("  [!] liste « %s » non créée (dossier indisponible)", name)
            continue
        try:
            lid = create_list(api_key, name, int(folder_id))
            log.info("  [✓] liste « %s » créée (id=%s) — à reporter dans BREVO_LIST_ID*", name, lid)
        except BrevoError as exc:
            log.error("  [x] liste « %s » : %s", name, exc)


def do_check(api_key: str) -> int:
    try:
        attrs = list_attributes(api_key)
        lists = list_contact_lists(api_key)
        folders = list_folders(api_key)
    except BrevoError as exc:
        log.error("Appel Brevo échoué : %s", exc)
        return 1
    log.info("=== Attributs de contact ===")
    for a in attrs:
        log.info("  %-14s (%s)", a.get("name", "?"), a.get("type", "?"))
    needed = [n for n in ATTRIBUTES if n not in {a.get("name", "").upper() for a in attrs}]
    log.info("  → manquants pour la perso : %s", ", ".join(needed) or "aucun ✅")
    log.info("=== Dossiers ===")
    for f in folders:
        log.info("  id=%s — %s", f.get("id"), f.get("name", "?"))
    log.info("=== Listes ===")
    for lst in lists:
        log.info("  id=%s — %s (%s abonnés)", lst.get("id"), lst.get("name", "?"),
                 lst.get("totalSubscribers", "?"))
    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Configuration Brevo pour la personnalisation.")
    parser.add_argument("--check", action="store_true", help="Afficher l'état actuel sans rien créer.")
    parser.add_argument("--dry-run", action="store_true", help="Montrer ce qui serait créé, sans écrire.")
    parser.add_argument("--no-lists", action="store_true", help="Ne configurer que les attributs.")
    args = parser.parse_args()

    api_key = os.getenv("BREVO_API_KEY")
    if not api_key:
        log.error("BREVO_API_KEY absente du .env. Configuration impossible.")
        return 1

    if args.check:
        return do_check(api_key)

    apply = not args.dry_run
    log.info("=== Configuration Brevo — personnalisation %s ===",
             "(DRY-RUN : aucune écriture)" if args.dry_run else "(application)")
    try:
        log.info("Attributs de contact :")
        ensure_attributes(api_key, apply=apply)
        if not args.no_lists:
            log.info("Dossier & listes par langue :")
            ensure_lists(api_key, apply=apply)
    except BrevoError as exc:
        log.error("Configuration interrompue : %s", exc)
        return 1
    log.info("=== Terminé. Lancer --check pour vérifier l'état. ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
