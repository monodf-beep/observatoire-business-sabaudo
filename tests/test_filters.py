#!/usr/bin/env python3
"""Tests de régression des FILTRES de la veille « Business Sabaudo ».

Fige les comportements validés à la main au fil des itérations (anti-déchets,
hors-sujet, bienvenue, images, presse, périmètre, extraction d'articles, tirets).
Aucune dépendance externe : lancer simplement

    python tests/test_filters.py

Sortie : liste des cas, total réussis/échoués, code retour 0 (tout vert) ou 1.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.sources import (  # noqa: E402
    is_blocked_image,
    is_broad_source,
    is_newsletter_junk,
    is_offtopic,
    is_press,
    is_welcome_subject,
    load_blocked_image_domains,
    load_broad_sources,
    load_perimeter_filter,
    load_press_domains,
    load_topic_filter,
    mentions_perimeter,
)

_PASS = 0
_FAIL = 0


def check(label: str, got, want) -> None:
    global _PASS, _FAIL
    ok = got == want
    if ok:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  ✗ {label} : obtenu {got!r}, attendu {want!r}")


# --------------------------------------------------------------------------- #
def test_offtopic():
    off, eco = load_topic_filter()
    drop = [
        "Championnats de France de cyclisme 2026",
        "Noyade dans le lac d'Annecy",
        "Torino, previsioni meteo del 25 giugno",
        "Football. OL a Bourgoin-Jallieu",
    ]
    keep = [
        "Plan de sauvegarde de l'emploi chez Somfy",
        "Les soldes en pleine canicule, catastrophe pour certains",
        "Economia valdostana, crescita frenata nel 2025",
        "Nuove opportunita di lavoro nel centro Amazon",
    ]
    for t in drop:
        check(f"offtopic DROP «{t[:30]}»", is_offtopic(t, off, eco), True)
    for t in keep:
        check(f"offtopic KEEP «{t[:30]}»", is_offtopic(t, off, eco), False)


def test_newsletter_junk():
    junk = [">> Je découvre", "Plus d'infos", "Téléchargez les images - 0", "www",
            "Facebook", "Se désabonner", "Je contacte un conseiller", "ai", "power",
            "poll results", "Unsubscribe here", "Astral Systems"]
    keep = ["come e quando pivotare", "incentivi al 30%",
            "La facturation électronique obligatoire dès septembre 2026",
            "My Sun Bed, start-up azuréenne, sacrée lauréate nationale"]
    for t in junk:
        check(f"junk DROP «{t[:25]}»", is_newsletter_junk(t), True)
    for t in keep:
        check(f"junk KEEP «{t[:25]}»", is_newsletter_junk(t), False)


def test_welcome():
    welcome = ["Bienvenue dans la communauté des entreprises", "Votre inscription est validée !",
               "Veuillez confirmer l'abonnement", "Grazie per esserti registrato!"]
    real = ["Le news più calde della settimana", "CCI Savoie - Lettre d'information"]
    for s in welcome:
        check(f"welcome SKIP «{s[:25]}»", is_welcome_subject(s), True)
    for s in real:
        check(f"welcome KEEP «{s[:25]}»", is_welcome_subject(s), False)


def test_blocked_image():
    bl = load_blocked_image_domains()
    check("image bfmtv bloquée", is_blocked_image("https://images.bfmtv.com/x.jpg", bl), True)
    check("image propre OK", is_blocked_image("https://i3p.it/photo.jpg", bl), False)


def test_press():
    press = load_press_domains()
    check("ledauphine = presse", is_press("ledauphine.com", press), True)
    check("i3p.it != presse", is_press("i3p.it", press), False)


def test_perimeter():
    perim = load_perimeter_filter()
    broad = load_broad_sources()
    check("eu-startups = source large", is_broad_source("eu-startups.com", broad), True)
    check("i3p != source large", is_broad_source("i3p.it", broad), False)
    check("mention Torino", mentions_perimeter("Une startup de Torino lève des fonds", perim), True)
    check("mention Nice", mentions_perimeter("Sophia Antipolis accueille un campus", perim), True)
    check("hors périmètre (Berlin)", mentions_perimeter("Astral Systems raises in Berlin", perim), False)


def test_extract_articles():
    from scripts.gmail_collect import extract_articles
    html = (
        "<html><body>"
        "<a href='https://trk.4dem.it/x'>Voir en ligne</a>"
        "<h2>La facturation électronique obligatoire dès septembre 2026</h2>"
        "<p>Détails pratiques.</p>"
        "<a href='https://www.savoie.cci.fr/facture'>&gt;&gt; Je découvre</a>"
        "<a href='https://i3p.it/pivotare'>come e quando pivotare</a>"
        "<a href='https://facebook.com/cci'>Facebook</a>"
        "</body></html>"
    )
    payload = {"mimeType": "text/html",
               "body": {"data": base64.urlsafe_b64encode(html.encode()).decode()}}
    arts = extract_articles(payload, resolve=False)
    titles = [a["text"] for a in arts]
    check("article: titre apparié au heading",
          "La facturation électronique obligatoire dès septembre 2026" in titles, True)
    check("article: ancre explicite gardée", "come e quando pivotare" in titles, True)
    check("article: Facebook exclu", any("Facebook" in t for t in titles), False)
    check("article: 'Voir en ligne' exclu", any("Voir en ligne" in t for t in titles), False)

    # Cas CCI : masthead exclu + lien utilitaire qui ne vole pas le titre du bouton.
    html2 = (
        "<html><body>"
        "<h1>🚨 Les actus à ne pas manquer !</h1>"
        "<span style='font-size:18px'>La facturation électronique obligatoire dès septembre 2026</span>"
        "<a href='https://cdn.cci.fr/photo.jpg'>Téléchargez les images</a>"
        "<a href='https://www.savoie.cci.fr/facture-2026'>&gt;&gt; Je découvre</a>"
        "</body></html>"
    )
    p2 = {"mimeType": "text/html",
          "body": {"data": base64.urlsafe_b64encode(html2.encode()).decode()}}
    t2 = [a["text"] for a in extract_articles(p2, subject="🚨 Les actus à ne pas manquer !", resolve=False)]
    check("article: masthead exclu",
          "La facturation électronique obligatoire dès septembre 2026" in t2, True)
    check("article: objet d'email jamais pris pour un titre",
          any("ne pas manquer" in t for t in t2), False)


def test_no_emdash():
    from scripts.synthesize import _no_emdash
    check("tiret cadratin retiré", "—" in _no_emdash("Teva — premier fabricant"), False)
    check("tiret demi-cadratin retiré", "–" in _no_emdash("A – B"), False)


def test_triage():
    from utils.triage import item_key, _parse_json_array
    # Clé stable : pilotée par l'URL (titre ignoré si URL présente), insensible au "/".
    check("triage: clé stable sur URL",
          item_key("https://x.fr/a/", "Titre X") == item_key("https://x.fr/a", "Autre"), True)
    # Parsing JSON robuste (fences markdown + texte autour).
    arr = _parse_json_array('Voici:\n```json\n[{"i":0,"keep":true,"titre":"Net"}]\n```')
    check("triage: parse JSON tolérant", arr == [{"i": 0, "keep": True, "titre": "Net"}], True)
    check("triage: parse invalide -> None", _parse_json_array("pas de json"), None)


def test_images_and_dates():
    from utils.sources import is_logo_image
    from utils.newsletter_variants import _fmt_date
    check("logo: stemma écarté", is_logo_image("https://regione.vda.it/stemma.png"), True)
    check("logo: .svg écarté", is_logo_image("https://x.fr/pic.svg"), True)
    check("photo: vraie photo gardée", is_logo_image("https://news.fr/uploads/usine.jpg"), False)
    check("date: format jj/mm/aaaa", _fmt_date("2026-06-24"), "24/06/2026")
    check("date: vide si invalide", _fmt_date("xxx"), "")
    # Requête d'illustration : garde l'acteur + mots-clés forts, retire les mots vides.
    from utils.image_search import _query
    q = _query("Decathlon", "Chambéry : Decathlon ferme deux magasins du centre-ville").lower()
    check("illustration: acteur dans la requête", "decathlon" in q, True)
    check("illustration: mot vide retiré", " du " not in f" {q} ", True)


def test_synthese_block():
    from utils.dashboard import _synthese_block
    check("synthèse: vide si pas de données", _synthese_block(None), "")
    block = _synthese_block({"hero": {"title": "Sommet franco-italien", "summary": "...", "territory": "Nice"},
                             "signaux": [{"title": "273 M€ pour la VDA", "territory": "Vallee-Aoste", "url": ""}]})
    check("synthèse: une rendue", "Sommet franco-italien" in block, True)
    check("synthèse: signal rendu", "273 M€ pour la VDA" in block, True)
    check("synthèse: libellé section", "Synthèse de la semaine" in block, True)


def main() -> int:
    for fn in (test_offtopic, test_newsletter_junk, test_welcome, test_blocked_image,
               test_press, test_perimeter, test_extract_articles, test_no_emdash, test_triage,
               test_images_and_dates, test_synthese_block):
        print(f"• {fn.__name__}")
        fn()
    print(f"\n{_PASS} réussi(s), {_FAIL} échoué(s).")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
