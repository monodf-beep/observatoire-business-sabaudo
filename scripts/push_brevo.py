#!/usr/bin/env python3
"""Crée un BROUILLON de campagne Brevo à partir des données structurées d'une semaine.

- Entrée : 02_Veille_traitee/Syntheses_hebdomadaires/AAAA-WNN.json (écrit par synthesize.py)
- Rendu : gabarit « magazine » (utils/newsletter_variants.variant_magazine)
- ⚠ N'ENVOIE JAMAIS : Franck relit dans Brevo puis déclenche l'envoi lui-même.

Personnalisation : un brouillon est créé par ÉDITION (langue, et territoire si
configuré). Le ciblage privilégie les SEGMENTS dynamiques (les contacts se rangent
seuls selon LANGUE/TERRITOIRE), avec repli sur des LISTES. Le contenu IT est
traduit via l'IA à partir de la même sélection éditoriale.

Configuration (.env) — pour chaque édition, SEGMENT prioritaire puis LISTE :
    BREVO_API_KEY        clé API Brevo
    BREVO_SENDER_NAME    nom de l'expéditeur (ex. Cultura Sabauda)
    BREVO_SENDER_EMAIL   email expéditeur VALIDÉ dans Brevo
    BREVO_SEGMENT_ID_FR / _IT            segment par langue (recommandé)
    BREVO_SEGMENT_ID_<LANG>_<TERR>       segment par territoire d'ancrage
    BREVO_LIST_ID_FR / _IT               (repli) liste par langue
    BREVO_LIST_ID_<LANG>_<TERR>          (repli) liste par territoire
    BREVO_LIST_ID                        (héritage) liste unique FR
        <TERR> ∈ SAVOIE, PIEMONTE, VALLEE_AOSTE, NICE → édition « Chez vous » en
        tête + une locale (les autres territoires restent visibles).
    BREVO_LOGO_URL       (option) URL du logo hébergé (bibliothèque média Brevo)

Usage :
    python scripts/push_brevo.py --week 2026-W24     # rend et crée le brouillon
    python scripts/push_brevo.py --file chemin.json
    python scripts/push_brevo.py --check             # liste expéditeurs + listes Brevo
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.brevo import (  # noqa: E402
    BrevoError,
    campaign_edit_url,
    create_draft_campaign,
    list_contact_lists,
    list_senders,
)
from utils.logger import get_logger  # noqa: E402
from utils.newsletter_variants import variant_magazine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SYNTH_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"

log = get_logger("push_brevo")


def find_data(week: str | None, file_arg: str | None) -> Path | None:
    if file_arg:
        path = Path(file_arg)
        return path if path.is_file() else None
    if week:
        path = SYNTH_DIR / f"{week}.json"
        return path if path.is_file() else None
    if not SYNTH_DIR.exists():
        return None
    candidates = sorted(SYNTH_DIR.glob("*.json"))
    return candidates[-1] if candidates else None


def _parse_ids(raw: str) -> list[int]:
    return [int(x) for x in re.split(r"[,;\s]+", raw or "") if x.strip().isdigit()]


# Libellé de langue pour les noms de campagne (le contenu, lui, est traduit).
_LANG_TAG = {"fr": "FR", "it": "IT"}

# Territoires d'ancrage : (clé interne, suffixe de variable .env, libellé court).
_TERRITORIES = [
    ("Savoie", "SAVOIE", "Savoie"),
    ("Piemonte", "PIEMONTE", "Piémont"),
    ("Vallee-Aoste", "VALLEE_AOSTE", "Vallée d'Aoste"),
    ("Nice", "NICE", "Nice"),
]


# Une édition = (anchor|None, kind, ids, libellé|None) avec kind ∈ {"segment","list"}.
Edition = tuple


def _resolve(seg_var: str, list_var: str) -> tuple[str, list[int]] | None:
    """Cible d'une édition : segment prioritaire, sinon liste, sinon rien."""
    seg = _parse_ids(os.getenv(seg_var, ""))
    if seg:
        return ("segment", seg)
    lst = _parse_ids(os.getenv(list_var, ""))
    if lst:
        return ("list", lst)
    return None


def _editions() -> dict[str, list[Edition]]:
    """Éditions à produire, groupées par langue (pour ne traduire qu'une fois/langue).

    Cible, par ordre de priorité, un SEGMENT dynamique puis une LISTE :
      - territoire : BREVO_SEGMENT_ID_<LANG>_<TERR> ou BREVO_LIST_ID_<LANG>_<TERR>
        (anchor = territoire → « Chez vous » en tête, une locale) ;
      - général    : BREVO_SEGMENT_ID_<LANG> ou BREVO_LIST_ID_<LANG> (anchor=None).
    Repli : BREVO_LIST_ID (héritage) → une édition générale FR.
    Renvoie { lang: [(anchor|None, kind, ids, libellé|None), …] }.
    """
    result: dict[str, list[Edition]] = {}
    for lang in ("fr", "it"):
        U = lang.upper()
        eds: list[Edition] = []
        for terr_key, env_suffix, label in _TERRITORIES:
            tgt = _resolve(f"BREVO_SEGMENT_ID_{U}_{env_suffix}", f"BREVO_LIST_ID_{U}_{env_suffix}")
            if tgt:
                eds.append((terr_key, tgt[0], tgt[1], label))
        gen = _resolve(f"BREVO_SEGMENT_ID_{U}", f"BREVO_LIST_ID_{U}")
        if gen:
            eds.append((None, gen[0], gen[1], None))
        if eds:
            result[lang] = eds
    if not result:
        legacy = _parse_ids(os.getenv("BREVO_LIST_ID", ""))
        if legacy:
            result["fr"] = [(None, "list", legacy, None)]
    return result


def _apply_lang_links(data: dict, lang: str) -> None:
    """Réécrit le lien de chaque article dans la langue de l'édition (url_by_lang)."""
    for item in [data.get("hero"), *data.get("items", []), *data.get("ponts", [])]:
        by_lang = item and item.get("url_by_lang")
        if by_lang and by_lang.get(lang):
            item["url"] = by_lang[lang]


def create_from_data(data: dict, force: bool = False) -> list[int]:
    """Rend la newsletter et crée un BROUILLON Brevo PAR LANGUE configurée.

    Renvoie la liste des ids de campagnes créées (vide si rien).
    Ne lève jamais : journalise et continue (sans danger en cron).
    """
    api_key = os.getenv("BREVO_API_KEY")
    sender_name = os.getenv("BREVO_SENDER_NAME")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    editions = _editions()
    missing = [k for k, v in {
        "BREVO_API_KEY": api_key, "BREVO_SENDER_NAME": sender_name,
        "BREVO_SENDER_EMAIL": sender_email,
        "BREVO_SEGMENT_ID_* ou BREVO_LIST_ID_*": editions,
    }.items() if not v]
    if missing:
        log.warning("Configuration Brevo incomplète (%s). Brouillon non créé.", ", ".join(missing))
        return []

    if not data.get("hero") and not data.get("items") and not force:
        log.info("Semaine sans contenu newsletter — brouillon Brevo ignoré (--force pour forcer).")
        return []

    # Logo : on privilégie l'URL hébergée en .env (les data-URI ne passent pas en email)
    base = dict(data)
    if os.getenv("BREVO_LOGO_URL"):
        base["logo_url"] = os.getenv("BREVO_LOGO_URL")
    if os.getenv("BREVO_PICTO_URL"):
        base["pictogram_url"] = os.getenv("BREVO_PICTO_URL")
    # Images de substitution AU RENDU : le héros reçoit toujours un visuel (impact
    # AIDA), les cartes une image tous les 3 articles. Appliqué ici (et pas seulement
    # à la synthèse) pour que les JSON déjà générés profitent de config/territory_images.txt
    # sans relancer l'IA.
    from utils.sources import apply_fallback_images
    apply_fallback_images(base)

    created: list[int] = []
    for lang, lang_editions in editions.items():
        # Une seule sélection éditoriale (FR) ; on traduit le contenu UNE fois par langue.
        try:
            from utils.translate import translate_email_data
            data_lang = translate_email_data(base, lang)
        except Exception as exc:  # traduction indisponible/échouée → on saute cette langue
            log.error("Traduction %s échouée, brouillons %s ignorés : %s", lang, lang.upper(), exc)
            continue

        # LIENS DANS LA LANGUE DE L'ÉDITION : on choisit la variante FR/IT mémorisée
        # par synthesize (hreflang) — ex. lien Nos Alpes FR pour l'édition FR, IT pour l'IT.
        _apply_lang_links(data_lang, lang)

        week_label = data_lang.get("week_label", "")
        subject = data_lang.get("subject") or f"Business Sabaudo · {week_label}"
        for anchor, kind, ids, label in lang_editions:
            # Même contenu traduit ; on ne change QUE l'ordre (territoire d'ancrage).
            data_v = {**data_lang, "anchor": anchor}
            html = variant_magazine(data_v)
            tag = _LANG_TAG.get(lang, lang.upper())
            name = " ".join(filter(None, ["Business Sabaudo", tag, label]))
            name = f"{name} · {week_label}".strip(" ·")

            recipients = {"segment_ids": ids} if kind == "segment" else {"list_ids": ids}
            try:
                campaign_id = create_draft_campaign(
                    api_key=api_key, name=name, subject=subject,
                    sender_name=sender_name, sender_email=sender_email,
                    html_content=html, **recipients,
                )
            except BrevoError as exc:
                # Segment/liste sans destinataire : cas NORMAL (territoire pas
                # encore peuplé). Brevo refuse la campagne — on saute sans bruit.
                if exc.status == 400 and "no recipients" in (exc.body or "").lower():
                    log.info("Édition %s ignorée : aucun destinataire (segment/liste vide).", name)
                    continue
                log.error("Création du brouillon Brevo (%s) échouée : %s", name, exc)
                continue

            log.info("Brouillon Brevo créé (id=%s, %s) — %s", campaign_id, kind, name)
            log.info("À relire/envoyer ici : %s", campaign_edit_url(campaign_id))
            created.append(campaign_id)

    if created:
        log.info("⚠ Aucun envoi automatique — validation et envoi manuels par Franck.")
    return created


def _do_check(api_key: str) -> int:
    try:
        senders = list_senders(api_key)
        lists = list_contact_lists(api_key)
    except BrevoError as exc:
        log.error("Appel Brevo échoué : %s", exc)
        return 1
    log.info("=== Expéditeurs validés (BREVO_SENDER_EMAIL) ===")
    for s in senders:
        flag = "✅" if s.get("active") else "⏳ (à valider)"
        log.info("  %s — %s  %s", s.get("name", "?"), s.get("email", "?"), flag)
    if not senders:
        log.info("  (aucun expéditeur — à créer dans Brevo > Expéditeurs)")
    log.info("=== Listes de contacts (BREVO_LIST_ID) ===")
    for lst in lists:
        log.info("  id=%s — %s (%s abonnés)", lst.get("id"), lst.get("name", "?"), lst.get("totalSubscribers", "?"))
    if not lists:
        log.info("  (aucune liste — à créer dans Brevo > Contacts > Listes)")
    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Brouillon de campagne Brevo (gabarit magazine).")
    parser.add_argument("--week", help="Semaine ISO cible (AAAA-WNN).")
    parser.add_argument("--file", help="Chemin explicite d'un fichier de données .json.")
    parser.add_argument("--check", action="store_true", help="Lister expéditeurs et listes Brevo, puis quitter.")
    parser.add_argument("--force", action="store_true", help="Créer le brouillon même si la semaine est creuse.")
    args = parser.parse_args()

    if args.check:
        api_key = os.getenv("BREVO_API_KEY")
        if not api_key:
            log.error("BREVO_API_KEY absente du .env.")
            return 1
        return _do_check(api_key)

    path = find_data(args.week, args.file)
    if not path:
        log.error("Aucune donnée newsletter trouvée (week=%s, file=%s). Lancer synthesize.py d'abord.",
                  args.week, args.file)
        return 1
    log.info("Données source : %s", path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Fichier de données illisible (%s) : %s", path, exc)
        return 1

    created = create_from_data(data, force=args.force)
    return 0 if created else 1


if __name__ == "__main__":
    raise SystemExit(main())
