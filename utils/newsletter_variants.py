"""Trois variantes de gabarit pour la newsletter Business Sabaudo.

Chaque variante applique les codes d'une newsletter B2B efficace (cadre AIDA :
Attention / Intérêt / Désir / Action) avec une mise en page différente :

- variant_magazine : héros visuel + signaux + cartes (impact éditorial fort)
- variant_digest    : liste compacte scannable (lecture rapide, F-pattern)
- variant_editorial : éditorial + « signal de la semaine » + tour des territoires

Logos : favicons officiels via le service Google (hébergés, fiables en email).
Aucune dépendance externe.
"""
from __future__ import annotations

from html import escape

# Charte Cultura Sabauda (extraite du logo officiel).
LOGO_BLUE = "#6287b8"   # bleu de la marque
BRAND = "#3f5f96"       # bleu profond (bandeau, bon contraste avec le blanc)
ACCENT = "#df664f"      # orange du point (CTA, accents)
INK = "#16202c"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
BG = "#eef1f5"

_TERRITORY = {
    "Savoie": ("#e6effb", "#1a56b0", "Savoie"),
    "Piemonte": ("#fdeaea", "#b3261e", "Piémont"),
    "Vallee-Aoste": ("#e7f6ea", "#1e7d34", "Vallée d'Aoste"),
    "Nice": ("#fff1e0", "#b25e00", "Nice"),
    "Alcotra": ("#ece7f7", "#5a3aa5", "Alcotra"),
}

# Ordre de proximité géographique : pour chaque territoire d'ancrage, ordre dans
# lequel les autres territoires apparaissent sous « Dans l'espace sabaudo ».
# Logique : voisins alpins proches d'abord, Nice en dernier pour les lecteurs alpins.
_TERRITORY_PROXIMITY: dict[str, list[str]] = {
    "Savoie":       ["Vallee-Aoste", "Piemonte", "Nice"],
    "Vallee-Aoste": ["Piemonte", "Savoie", "Nice"],
    "Piemonte":     ["Vallee-Aoste", "Savoie", "Nice"],
    "Nice":         ["Piemonte", "Savoie", "Vallee-Aoste"],
}

# Libellés des pastilles de territoire par langue (les couleurs viennent de _TERRITORY).
_TERRITORY_LABELS = {
    "fr": {"Savoie": "Savoie", "Piemonte": "Piémont", "Vallee-Aoste": "Vallée d'Aoste",
           "Nice": "Nice", "Alcotra": "Alcotra"},
    "it": {"Savoie": "Savoia", "Piemonte": "Piemonte", "Vallee-Aoste": "Valle d'Aosta",
           "Nice": "Nizza", "Alcotra": "Alcotra"},
}

# Tous les libellés d'interface de l'email, par langue (le CONTENU éditorial, lui,
# est traduit séparément — voir utils/translate.py).
_LABELS = {
    "fr": {
        "html_lang": "fr",
        "surtitre": "Observatoire économique",
        "tagline_magazine": "Savoie · Piémont · Vallée d'Aoste · Nice · Alcotra",
        "a_la_une": "À la une",
        "signaux": "Les signaux de la semaine",
        "territoires": "Le tour des territoires",
        "chez_vous": "Chez vous",
        "autres_territoires": "Dans l'espace sabaudo",
        "ponts": "Ponts & connexions",
        "ponts_intro": "L'espace sabaudo relié à ses voisins — Grenoble, Lyon, "
                       "Genève, la Suisse, la France, l'international.",
        "lire_suite": "Lire la suite",
        "lire_article": "Lire l'article",
        "voir_en_ligne": "Voir en ligne",
        "desabonner": "Se désabonner",
        "footer_feedback": "💬 Une source à suggérer, une coquille repérée&nbsp;? "
                           "<strong>Répondez à cet email</strong>, on lit tout.",
        "footer_baseline": "Observatoire économique de l'espace sabaudo — "
                           "Savoie · Piémont · Vallée d'Aoste · Nice · Alcotra",
        "footer_ia": "Veille assistée par IA, sélectionnée et validée par la rédaction "
                     "de Cultura Sabauda.",
    },
    "it": {
        "html_lang": "it",
        "surtitre": "Osservatorio economico",
        "tagline_magazine": "Savoia · Piemonte · Valle d'Aosta · Nizza · Alcotra",
        "a_la_une": "In primo piano",
        "signaux": "I segnali della settimana",
        "territoires": "Il giro dei territori",
        "chez_vous": "Da voi",
        "autres_territoires": "Nello spazio sabaudo",
        "ponts": "Ponti e connessioni",
        "ponts_intro": "Lo spazio sabaudo in collegamento con i suoi vicini — Grenoble, "
                       "Lione, Ginevra, la Svizzera, la Francia, l'internazionale.",
        "lire_suite": "Continua a leggere",
        "lire_article": "Leggi l'articolo",
        "voir_en_ligne": "Visualizza online",
        "desabonner": "Annulla l'iscrizione",
        "footer_feedback": "💬 Una fonte da segnalare, un refuso&nbsp;? "
                           "<strong>Rispondi a questa email</strong>, leggiamo tutto.",
        "footer_baseline": "Osservatorio economico dello spazio sabaudo — "
                           "Savoia · Piemonte · Valle d'Aosta · Nizza · Alcotra",
        "footer_ia": "Monitoraggio assistito dall'IA, selezionato e validato dalla "
                     "redazione di Cultura Sabauda.",
    },
}


def labels(lang: str) -> dict:
    """Renvoie le dictionnaire de libellés d'interface pour la langue (repli FR)."""
    return _LABELS.get(lang, _LABELS["fr"])


def _territory_label(territory: str, lang: str = "fr") -> str:
    _, _, default = _TERRITORY.get(territory, ("", "", territory or ""))
    return _TERRITORY_LABELS.get(lang, {}).get(territory, default)


_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def favicon(domain: str, size: int = 64) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"


def _tag(territory: str, lang: str = "fr") -> str:
    _, dotc, default_label = _TERRITORY.get(territory, ("", "#64748b", territory or "—"))
    label = _TERRITORY_LABELS.get(lang, {}).get(territory, default_label)
    dot = (
        f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
        f'background:{dotc};margin-right:6px;vertical-align:middle;"></span>'
    )
    return (
        '<span style="display:inline-block;background:#eef2f7;color:#42526b;font-size:11px;'
        'font-weight:700;letter-spacing:.4px;text-transform:uppercase;padding:4px 11px;'
        f'border-radius:20px;vertical-align:middle;">{dot}{escape(label)}</span>'
    )


def _source(item: dict, size: int = 18) -> str:
    name = escape(item.get("source", ""))
    dom = item.get("domain")
    icon = ""
    if dom:
        icon = (
            f'<img src="{favicon(dom)}" width="{size}" height="{size}" alt="" '
            f'style="border-radius:4px;vertical-align:middle;border:0;">&nbsp;'
        )
    return f'<span style="color:{MUTED};font-size:12px;font-weight:600;vertical-align:middle;">{icon}{name}</span>'


def _cta(url: str, label: str | None = None, lang: str = "fr") -> str:
    if not url:
        return ""
    label = label or labels(lang)["lire_suite"]
    return (
        f'<a href="{escape(url)}" style="color:{ACCENT};font-size:14px;font-weight:700;'
        f'text-decoration:none;">{escape(label)} &rarr;</a>'
    )


def _button(url: str, label: str) -> str:
    return (
        f'<a href="{escape(url)}" style="display:inline-block;background:{ACCENT};color:#fff;'
        'font-size:14px;font-weight:700;text-decoration:none;padding:11px 22px;border-radius:8px;">'
        f"{escape(label)}</a>"
    )


def _header(week_label: str, tagline: str, logo_url: str | None = None, lang: str = "fr") -> str:
    """Masthead éditorial blanc : surtitre + logo éditeur (petit) + titre + date."""
    logo_cell = ""
    if logo_url:
        logo_cell = (
            f'<td align="right" valign="middle"><img src="{logo_url}" alt="Une publication Cultura Sabauda" '
            'height="24" style="height:24px;border:0;display:inline-block;"></td>'
        )
    return (
        '<tr><td style="padding:28px 36px 0;background:#fff;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        f'<td valign="middle" style="font-size:11px;font-weight:800;letter-spacing:1.8px;'
        f'text-transform:uppercase;color:{ACCENT};">{escape(labels(lang)["surtitre"])}</td>'
        f"{logo_cell}"
        "</tr></table></td></tr>"
        '<tr><td style="padding:14px 36px 0;background:#fff;">'
        f'<div style="font-size:34px;font-weight:800;letter-spacing:-.5px;color:{BRAND};line-height:1;">'
        f'Business Sabaudo<span style="color:{ACCENT};">.</span></div>'
        f'<div style="font-size:13px;color:{MUTED};margin-top:9px;letter-spacing:.2px;">{escape(tagline)}</div>'
        "</td></tr>"
        '<tr><td style="padding:18px 36px 0;background:#fff;">'
        f'<div style="height:1px;background:{BORDER};line-height:1px;font-size:0;">&nbsp;</div></td></tr>'
        '<tr><td style="padding:12px 36px 22px;background:#fff;">'
        f'<span style="font-size:11px;font-weight:700;letter-spacing:1.4px;text-transform:uppercase;color:{MUTED};">'
        f"{escape(week_label)}</span></td></tr>"
    )


def _eyebrow(text: str) -> str:
    """Intertitre de section : petit filet orange + libellé en capitales."""
    return (
        '<div style="margin-bottom:14px;">'
        f'<span style="display:inline-block;width:26px;height:3px;background:{ACCENT};'
        'vertical-align:middle;margin-right:9px;border-radius:2px;"></span>'
        f'<span style="font-size:12px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;'
        f'color:{BRAND};vertical-align:middle;">{escape(text)}</span></div>'
    )


def _footer(logo_url: str | None = None, lang: str = "fr") -> str:
    L = labels(lang)
    logo = ""
    if logo_url:
        logo = (
            f'<div style="margin-bottom:16px;"><img src="{logo_url}" alt="Cultura Sabauda" '
            'height="46" style="height:46px;border:0;display:block;"></div>'
        )
    return (
        f'<tr><td style="background:#f7f9fc;padding:26px 36px;border-top:1px solid {BORDER};">'
        f"{logo}"
        f'<div style="color:{INK};font-size:13px;line-height:1.6;margin-bottom:12px;">'
        f'{L["footer_feedback"]}'
        "</div>"
        f'<div style="color:{MUTED};font-size:12px;line-height:1.6;">'
        f'{escape(L["footer_baseline"])}<br>'
        f'<em>{escape(L["footer_ia"])}</em><br>'
        f'<a href="https://culturasabauda.eu" style="color:{MUTED};">culturasabauda.eu</a> · '
        f'<a href="{{{{ unsubscribe }}}}" style="color:#6b7280;">{escape(L["desabonner"])}</a>'
        "</div></td></tr>"
    )


def _shell(inner: str, *, preheader: str, lang: str = "fr") -> str:
    L = labels(lang)
    return (
        f'<!DOCTYPE html><html lang="{L["html_lang"]}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Business Sabaudo</title></head>"
        f'<body style="margin:0;padding:0;background:{BG};font-family:{_FONT};">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 12px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="width:600px;max-width:100%;background:#fff;border-radius:14px;overflow:hidden;">'
        '<tr><td style="padding:7px 32px;background:#fff;text-align:right;font-size:11px;color:#9aa3af;">'
        f'<a href="{{{{ mirror }}}}" style="color:#9aa3af;text-decoration:none;">{escape(L["voir_en_ligne"])}</a></td></tr>'
        f"{inner}"
        "</table></td></tr></table></body></html>"
    )


# --------------------------------------------------------------------------- #
# Variante 1 — MAGAZINE (héros + signaux + cartes)                            #
# --------------------------------------------------------------------------- #
def variant_magazine(data: dict) -> str:
    lang = data.get("lang", "fr")
    L = labels(lang)
    hero = data["hero"]
    sig_list = data["signaux"]
    signaux = ""
    for i, s in enumerate(sig_list, 1):
        border = "" if i == len(sig_list) else f"border-bottom:1px solid {BORDER};"
        badge = (
            f'<span style="display:inline-block;width:24px;height:24px;border-radius:50%;'
            f'background:{BRAND};color:#fff;font-size:12px;font-weight:800;line-height:24px;'
            f'text-align:center;">{i}</span>'
        )
        signaux += (
            "<tr>"
            f'<td width="36" valign="top" style="padding:12px 0;{border}">{badge}</td>'
            f'<td valign="top" style="padding:12px 0;{border}">{_tag(s["territory"], lang)}'
            f'<div style="font-size:15px;color:{INK};font-weight:700;line-height:1.4;margin-top:5px;">'
            f'{escape(s["title"])}</div></td></tr>'
        )
    items = data["items"]
    anchor = data.get("anchor")

    # ANCRAGE DE LA UNE : pour une édition territoriale, la « une » doit être LOCALE.
    # Si la une n'est pas du territoire d'ancrage mais qu'une brève locale existe,
    # on promeut la 1re brève locale en une, et l'ancienne une redevient une carte.
    if anchor and (not hero or hero.get("territory") != anchor):
        local = [it for it in items if it.get("territory") == anchor]
        if local:
            new_hero = local[0]
            rest = [it for it in items if it is not new_hero]
            if hero:
                rest = [hero] + rest  # l'ancienne une rejoint les cartes
            hero, items = new_hero, rest

    def _cards_html(card_items: list[dict]) -> str:
        out = ""
        for idx, it in enumerate(card_items):
            wrap = (
                "margin:0;padding:0;" if idx == len(card_items) - 1
                else f"border-bottom:1px solid {BORDER};margin:0 0 24px;padding:0 0 22px;"
            )
            img = ""
            if it.get("image"):
                img = (
                    f'<tr><td style="padding:0 0 12px;"><img src="{escape(it["image"])}" width="528" alt="" '
                    'style="width:100%;height:auto;display:block;border-radius:10px;border:0;"></td></tr>'
                )
            out += (
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="{wrap}">'
                f"{img}"
                f'<tr><td style="padding:0 0 8px;">{_tag(it["territory"], lang)}&nbsp;&nbsp;{_source(it)}</td></tr>'
                f'<tr><td style="padding:0 0 6px;font-size:19px;font-weight:700;color:{INK};line-height:1.3;">'
                f'<a href="{escape(it["url"])}" style="color:{INK};text-decoration:none;">{escape(it["title"])}</a></td></tr>'
                f'<tr><td style="font-size:15px;color:#374151;line-height:1.6;">{escape(it["summary"])}</td></tr>'
                f'<tr><td style="padding:10px 0 0;">{_cta(it["url"], lang=lang)}</td></tr>'
                "</table>"
            )
        return out

    # PERSONNALISATION PAR TERRITOIRE : les brèves locales remontent sous « Chez
    # vous », les autres sous « Dans l'espace sabaudo ». Sans ancrage (ou si rien
    # n'est local) : un seul « Tour des territoires ». La une est déjà ancrée ci-dessus.
    home = [it for it in items if anchor and it.get("territory") == anchor]
    others = [it for it in items if not (anchor and it.get("territory") == anchor)]
    # Tri de proximité géographique : voisins alpins proches d'abord, Nice en
    # dernier pour les lecteurs alpins. Les items sans territoire connu restent
    # en fin (panneaux pan-sabaudo, Alcotra, etc. — rang = len de la liste).
    if anchor and anchor in _TERRITORY_PROXIMITY:
        _prox = _TERRITORY_PROXIMITY[anchor]
        others.sort(key=lambda it: _prox.index(it["territory"])
                    if it.get("territory") in _prox else len(_prox))
    # Édition « ancrée » dès que la une OU une carte relève du territoire.
    anchored = bool(anchor) and (bool(home) or (hero and hero.get("territory") == anchor))

    def _section(eyebrow_text: str, cards_html: str, pad: str) -> str:
        return f'<tr><td style="padding:{pad};">{_eyebrow(eyebrow_text)}{cards_html}</td></tr>'

    if home:
        territoires_html = _section(
            f'{L["chez_vous"]} — {_territory_label(anchor, lang)}',
            _cards_html(home),
            "30px 36px 4px" if others else "30px 36px 34px",
        )
        if others:
            territoires_html += _section(L["autres_territoires"], _cards_html(others), "24px 36px 34px")
    elif anchored:
        # La une porte déjà le territoire ; le reste va sous « Dans l'espace sabaudo ».
        territoires_html = _section(L["autres_territoires"], _cards_html(others), "30px 36px 34px")
    else:
        territoires_html = _section(L["territoires"], _cards_html(others), "30px 36px 34px")
    # PONTS & CONNEXIONS — la dimension transfrontalière (commune à tous les lecteurs).
    # Liste compacte sans image : l'espace sabaudo relié à ses voisins.
    ponts = data.get("ponts") or []
    ponts_rows = ""
    for p in ponts:
        ponts_rows += (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-bottom:1px solid {BORDER};margin:0 0 14px;padding:0 0 14px;"><tr>'
            f'<td valign="top">{_tag(p["territory"], lang)}&nbsp;&nbsp;{_source(p)}'
            f'<div style="font-size:16px;font-weight:700;color:{INK};line-height:1.3;margin:6px 0 4px;">'
            f'<a href="{escape(p["url"])}" style="color:{INK};text-decoration:none;">{escape(p["title"])}</a></div>'
            f'<div style="font-size:14px;color:#4b5563;line-height:1.6;">{escape(p["summary"])}</div>'
            + (f'<div style="margin-top:6px;">{_cta(p["url"], lang=lang)}</div>' if p.get("url") else "")
            + "</td></tr></table>"
        )
    ponts_section = (
        f'<tr><td style="padding:4px 36px 34px;">{_eyebrow(L["ponts"])}'
        f'<div style="font-size:13px;color:{MUTED};line-height:1.5;margin:-4px 0 16px;">'
        f'{escape(L["ponts_intro"])}</div>'
        f"{ponts_rows}</td></tr>"
    ) if ponts else ""
    inner = (
        _header(data["week_label"], L["tagline_magazine"], data.get("logo_url"), lang)
        # HÉROS / À LA UNE (Attention)
        + f'<tr><td style="padding:26px 36px 0;">{_eyebrow(L["a_la_une"])}</td></tr>'
        + (
            f'<tr><td style="padding:0 36px;"><img src="{escape(hero["image"])}" width="528" alt="" '
            'style="width:100%;height:auto;display:block;border-radius:10px;border:0;"></td></tr>'
            if hero.get("image") else ""
        )
        + f'<tr><td style="padding:14px 36px 6px;">{_tag(hero["territory"], lang)}&nbsp;&nbsp;{_source(hero)}'
          f'<div style="font-size:25px;font-weight:800;color:{INK};line-height:1.25;margin:11px 0 8px;">{escape(hero["title"])}</div>'
          f'<div style="font-size:15px;color:#374151;line-height:1.6;">{escape(hero["summary"])}</div>'
          + (f'<div style="margin-top:16px;">{_button(hero["url"], L["lire_article"])}</div>' if hero.get("url") else "")
          + "</td></tr>"
        # SIGNAUX (Intérêt)
        + f'<tr><td style="padding:30px 36px 4px;">{_eyebrow(L["signaux"])}'
          f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{signaux}</table></td></tr>'
        # CARTES (Désir + Action) — réordonnées par territoire d'ancrage si fourni
        + territoires_html
        # PONTS & CONNEXIONS (dimension transfrontalière)
        + ponts_section
        + _footer(data.get("pictogram_url") or data.get("logo_url"), lang)
    )
    return _shell(inner, preheader=data["preheader"], lang=lang)


# --------------------------------------------------------------------------- #
# Variante 2 — DIGEST compact (liste scannable)                               #
# --------------------------------------------------------------------------- #
def variant_digest(data: dict) -> str:
    rows = ""
    for it in data["items"]:
        rows += (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-bottom:1px solid {BORDER};margin:0 0 14px;padding:0 0 14px;"><tr>'
            f'<td width="96" valign="top" style="padding-right:14px;">'
            f'<img src="{escape(it["image"])}" width="96" alt="" style="width:96px;height:72px;object-fit:cover;'
            'border-radius:8px;display:block;border:0;"></td>'
            f'<td valign="top">{_tag(it["territory"])}'
            f'<div style="font-size:16px;font-weight:700;color:{INK};line-height:1.3;margin:6px 0 4px;">'
            f'<a href="{escape(it["url"])}" style="color:{INK};text-decoration:none;">{escape(it["title"])}</a></div>'
            f'<div style="font-size:13px;color:#4b5563;line-height:1.5;">{escape(it["summary"])}</div>'
            f'<div style="margin-top:6px;">{_source(it, 16)}</div>'
            "</td></tr></table>"
        )
    inner = (
        _header(data["week_label"], "L'essentiel de la semaine, en 2 minutes", data.get("logo_url"))
        + f'<tr><td style="padding:24px 36px 8px;font-size:15px;color:{INK};line-height:1.6;">{escape(data["intro"])}</td></tr>'
        + f'<tr><td style="padding:8px 36px 4px;">{_eyebrow("Au sommaire")}{rows}</td></tr>'
        + f'<tr><td align="center" style="padding:8px 36px 30px;">{_button(data["cta_url"], "Voir toute la veille")}</td></tr>'
        + _footer(data.get("pictogram_url") or data.get("logo_url"))
    )
    return _shell(inner, preheader=data["preheader"])


# --------------------------------------------------------------------------- #
# Variante 3 — ÉDITORIAL (signal de la semaine + tour des territoires)        #
# --------------------------------------------------------------------------- #
def variant_editorial(data: dict) -> str:
    hero = data["hero"]
    blocks = ""
    for it in data["items"]:
        blocks += (
            f'<tr><td style="padding:16px 0 14px;border-bottom:1px solid {BORDER};">'
            f'{_tag(it["territory"])}&nbsp;&nbsp;{_source(it)}'
            f'<div style="font-size:17px;font-weight:700;color:{INK};line-height:1.3;margin:8px 0 5px;">'
            f'<a href="{escape(it["url"])}" style="color:{INK};text-decoration:none;">{escape(it["title"])}</a></div>'
            f'<div style="font-size:14px;color:#4b5563;line-height:1.6;">{escape(it["summary"])} {_cta(it["url"], "lire")}</div>'
            "</td></tr>"
        )
    sig = (
        f'<tr><td style="padding:8px 36px 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:#f3f7fc;border-left:4px solid {ACCENT};border-radius:8px;"><tr><td style="padding:18px 20px;">'
        f'<div style="font-size:12px;font-weight:800;color:{ACCENT};text-transform:uppercase;letter-spacing:1px;">Le signal de la semaine</div>'
        f'<div style="font-size:20px;font-weight:800;color:{INK};line-height:1.3;margin:8px 0 6px;">{escape(hero["title"])}</div>'
        f'<div style="font-size:15px;color:#374151;line-height:1.6;">{escape(hero["summary"])}</div>'
        f'<div style="margin-top:12px;">{_tag(hero["territory"])}&nbsp;&nbsp;{_source(hero)}&nbsp;&nbsp;{_cta(hero["url"])}</div>'
        "</td></tr></table></td></tr>"
    )
    inner = (
        _header(data["week_label"], "La lettre économique de l'espace sabaudo", data.get("logo_url"))
        + f'<tr><td style="padding:26px 36px 12px;font-size:16px;color:{INK};line-height:1.65;">{escape(data["edito"])}</td></tr>'
        + sig
        + f'<tr><td style="padding:26px 36px 2px;">{_eyebrow("Le tour des territoires")}'
          f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{blocks}</table></td></tr>'
        + f'<tr><td style="padding:20px 36px 28px;font-size:14px;color:{INK};line-height:1.6;">{escape(data["signature"]).replace(chr(10), "<br>")}</td></tr>'
        + _footer(data.get("pictogram_url") or data.get("logo_url"))
    )
    return _shell(inner, preheader=data["preheader"])
