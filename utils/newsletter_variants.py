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

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def favicon(domain: str, size: int = 64) -> str:
    return f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"


def _tag(territory: str) -> str:
    bg, fg, label = _TERRITORY.get(territory, ("#eceff3", "#374151", territory or "—"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};font-size:11px;'
        'font-weight:700;letter-spacing:.3px;text-transform:uppercase;padding:3px 10px;'
        f'border-radius:20px;">{escape(label)}</span>'
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


def _cta(url: str, label: str = "Lire la suite") -> str:
    if not url:
        return ""
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


def _header(week_label: str, tagline: str, logo_url: str | None = None) -> str:
    """Masthead éditorial sur fond blanc : éditeur (logo) + titre produit + date."""
    logo = ""
    if logo_url:
        logo = (
            '<tr><td style="padding:30px 36px 0;background:#fff;">'
            f'<img src="{logo_url}" alt="Cultura Sabauda" height="26" '
            'style="height:26px;border:0;display:block;"></td></tr>'
        )
    return (
        f"{logo}"
        '<tr><td style="padding:22px 36px 0;background:#fff;">'
        f'<div style="font-size:33px;font-weight:800;letter-spacing:-.5px;color:{BRAND};line-height:1;">'
        f'Business Sabaudo<span style="color:{ACCENT};">.</span></div>'
        f'<div style="font-size:14px;color:{MUTED};margin-top:9px;">{escape(tagline)}</div>'
        "</td></tr>"
        f'<tr><td style="padding:18px 36px 0;background:#fff;">'
        f'<div style="height:1px;background:{BORDER};line-height:1px;font-size:0;">&nbsp;</div></td></tr>'
        '<tr><td style="padding:12px 36px 22px;background:#fff;">'
        f'<span style="font-size:11px;font-weight:800;letter-spacing:1.6px;text-transform:uppercase;color:{ACCENT};">'
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


def _footer() -> str:
    return (
        f'<tr><td style="background:#f7f9fc;padding:22px 32px;border-top:1px solid {BORDER};">'
        f'<div style="color:{INK};font-size:13px;line-height:1.6;margin-bottom:10px;">'
        "💬 Une source à suggérer, une coquille repérée&nbsp;? "
        "<strong>Répondez à cet email</strong>, on lit tout."
        "</div>"
        f'<div style="color:{MUTED};font-size:12px;line-height:1.6;">'
        f'<strong style="color:{BRAND};">Cultura Sabauda</strong> — Observatoire économique de l\'espace sabaudo<br>'
        "Savoie · Piémont · Vallée d'Aoste · Nice · Alcotra<br>"
        "<em>Veille assistée par IA, sélectionnée et validée par la rédaction de Cultura Sabauda.</em><br>"
        f'<a href="https://culturasabauda.eu" style="color:{MUTED};">culturasabauda.eu</a> · '
        '<a href="{{ unsubscribe }}" style="color:#6b7280;">Se désabonner</a>'
        "</div></td></tr>"
    )


def _shell(inner: str, *, preheader: str) -> str:
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Business Sabaudo</title></head>"
        f'<body style="margin:0;padding:0;background:{BG};font-family:{_FONT};">'
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 12px;">'
        '<tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" '
        'style="width:600px;max-width:100%;background:#fff;border-radius:14px;overflow:hidden;">'
        '<tr><td style="padding:7px 32px;background:#fff;text-align:right;font-size:11px;color:#9aa3af;">'
        '<a href="{{ mirror }}" style="color:#9aa3af;text-decoration:none;">Voir en ligne</a></td></tr>'
        f"{inner}"
        "</table></td></tr></table></body></html>"
    )


# --------------------------------------------------------------------------- #
# Variante 1 — MAGAZINE (héros + signaux + cartes)                            #
# --------------------------------------------------------------------------- #
def variant_magazine(data: dict) -> str:
    hero = data["hero"]
    signaux = "".join(
        f'<tr><td style="padding:8px 0;border-bottom:1px solid {BORDER};font-size:14px;color:{INK};line-height:1.5;">'
        f'{_tag(s["territory"])}&nbsp;&nbsp;<strong>{escape(s["title"])}</strong></td></tr>'
        for s in data["signaux"]
    )
    cards = ""
    for it in data["items"]:
        cards += (
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-bottom:1px solid {BORDER};margin:0 0 22px;padding:0 0 18px;">'
            f'<tr><td style="padding:0 0 10px;"><img src="{escape(it["image"])}" width="528" alt="" '
            'style="width:100%;height:auto;display:block;border-radius:10px;border:0;"></td></tr>'
            f'<tr><td style="padding:0 0 7px;">{_tag(it["territory"])}&nbsp;&nbsp;{_source(it)}</td></tr>'
            f'<tr><td style="padding:0 0 6px;font-size:19px;font-weight:700;color:{INK};line-height:1.3;">'
            f'<a href="{escape(it["url"])}" style="color:{INK};text-decoration:none;">{escape(it["title"])}</a></td></tr>'
            f'<tr><td style="font-size:15px;color:#374151;line-height:1.6;">{escape(it["summary"])}</td></tr>'
            f'<tr><td style="padding:9px 0 0;">{_cta(it["url"])}</td></tr>'
            "</table>"
        )
    inner = (
        _header(data["week_label"], "La veille économique de l'espace sabaudo", data.get("logo_url"))
        # HÉROS (Attention)
        + f'<tr><td style="padding:0;"><img src="{escape(hero["image"])}" width="600" alt="" '
          'style="width:100%;height:auto;display:block;border:0;"></td></tr>'
        + f'<tr><td style="padding:24px 36px 6px;">{_tag(hero["territory"])}'
          f'<div style="font-size:24px;font-weight:800;color:{INK};line-height:1.25;margin:10px 0 8px;">{escape(hero["title"])}</div>'
          f'<div style="font-size:15px;color:#374151;line-height:1.6;">{escape(hero["summary"])}</div>'
          f'<div style="margin-top:14px;">{_button(hero["url"], "Lire l’article")}</div></td></tr>'
        # SIGNAUX (Intérêt)
        + f'<tr><td style="padding:28px 36px 4px;">{_eyebrow("Les signaux de la semaine")}'
          f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{signaux}</table></td></tr>'
        # CARTES (Désir + Action)
        + f'<tr><td style="padding:30px 36px 4px;">{_eyebrow("Le tour des territoires")}'
          f'{cards}</td></tr>'
        + _footer()
    )
    return _shell(inner, preheader=data["preheader"])


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
        + _footer()
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
        + _footer()
    )
    return _shell(inner, preheader=data["preheader"])
