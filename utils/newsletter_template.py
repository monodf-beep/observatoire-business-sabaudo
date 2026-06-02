"""Gabarit HTML « riche » pour la newsletter Business Sabaudo.

Produit un email responsive (largeur 600px, styles en ligne, structure en
tableaux pour la compatibilité Outlook/Gmail) à partir de données structurées :
en-tête, intro, cartes d'articles (image + pastille territoire + logo/badge de
l'organisme + titre + résumé + lien), pied de page.

Aucune dépendance externe.
"""
from __future__ import annotations

from html import escape

# Identité Cultura Sabauda (bleu savoyard + rouge de Savoie).
BRAND = "#0b3b6f"
ACCENT = "#c8102e"
INK = "#1a1a1a"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
BG = "#eef1f5"

# Pastille par territoire : (fond, texte, libellé affiché).
_TERRITORY = {
    "Savoie": ("#e6effb", "#1a56b0", "Savoie"),
    "Piemonte": ("#fdeaea", "#b3261e", "Piémont"),
    "Vallee-Aoste": ("#e7f6ea", "#1e7d34", "Vallée d'Aoste"),
    "Nice": ("#fff1e0", "#b25e00", "Nice"),
    "Alcotra": ("#ece7f7", "#5a3aa5", "Alcotra"),
}


def _territory_tag(territory: str) -> str:
    bg, fg, label = _TERRITORY.get(territory, ("#eceff3", "#374151", territory or "—"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        'font-size:11px;font-weight:700;letter-spacing:.3px;text-transform:uppercase;'
        f'padding:3px 10px;border-radius:20px;">{escape(label)}</span>'
    )


def _source_badge(source: str, logo: str | None) -> str:
    """Logo de l'organisme si fourni, sinon un badge avec ses initiales."""
    if logo:
        return (
            f'<img src="{escape(logo)}" alt="{escape(source)}" height="22" '
            'style="max-height:22px;vertical-align:middle;border:0;">'
        )
    initials = "".join(w[0] for w in source.split()[:2]).upper() or "•"
    return (
        f'<span style="display:inline-block;background:{BRAND};color:#fff;font-size:11px;'
        'font-weight:700;width:24px;height:24px;line-height:24px;text-align:center;'
        f'border-radius:50%;vertical-align:middle;">{escape(initials)}</span>'
        f'<span style="color:{MUTED};font-size:12px;vertical-align:middle;">&nbsp;{escape(source)}</span>'
    )


def _card(item: dict) -> str:
    image = item.get("image")
    title = escape(item.get("title", ""))
    summary = escape(item.get("summary", ""))
    url = item.get("url", "")
    source = item.get("source", "")
    territory = item.get("territory", "")
    logo = item.get("logo")

    img_html = ""
    if image:
        img_html = (
            f'<tr><td style="padding:0 0 12px;"><img src="{escape(image)}" alt="" width="600" '
            'style="width:100%;max-width:600px;height:auto;display:block;border-radius:10px;border:0;"></td></tr>'
        )
    title_html = title
    if url:
        title_html = f'<a href="{escape(url)}" style="color:{INK};text-decoration:none;">{title}</a>'
    link_html = ""
    if url:
        link_html = (
            f'<tr><td style="padding:10px 0 0;"><a href="{escape(url)}" '
            f'style="color:{ACCENT};font-size:14px;font-weight:600;text-decoration:none;">'
            "Lire la suite &rarr;</a></td></tr>"
        )

    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-bottom:1px solid {BORDER};margin:0 0 24px;padding:0 0 20px;">'
        f"{img_html}"
        '<tr><td style="padding:0 0 8px;">'
        f"{_territory_tag(territory)}&nbsp;&nbsp;{_source_badge(source, logo)}"
        "</td></tr>"
        f'<tr><td style="padding:0 0 6px;"><span style="font-size:19px;font-weight:700;'
        f'color:{INK};line-height:1.3;">{title_html}</span></td></tr>'
        f'<tr><td style="font-size:15px;color:#374151;line-height:1.6;">{summary}</td></tr>'
        f"{link_html}"
        "</table>"
    )


def render_newsletter(
    *,
    title: str,
    subtitle: str,
    week_label: str,
    intro: str,
    items: list[dict],
    signature: str,
) -> str:
    """Assemble l'email complet et renvoie le HTML."""
    cards = "\n".join(_card(it) for it in items)
    intro_html = escape(intro)
    signature_html = escape(signature).replace("\n", "<br>")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}</title>
</head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background:#ffffff;border-radius:14px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <!-- En-tête -->
  <tr><td style="background:{BRAND};padding:28px 32px;">
    <div style="color:#ffffff;font-size:24px;font-weight:800;letter-spacing:.5px;">{escape(title)}</div>
    <div style="color:#aecbf0;font-size:14px;margin-top:4px;">{escape(subtitle)}</div>
    <div style="color:#ffffff;font-size:12px;margin-top:14px;text-transform:uppercase;letter-spacing:1px;border-top:2px solid {ACCENT};display:inline-block;padding-top:8px;">{escape(week_label)}</div>
  </td></tr>

  <!-- Intro -->
  <tr><td style="padding:26px 32px 8px;font-size:16px;color:{INK};line-height:1.6;">{intro_html}</td></tr>

  <!-- Articles -->
  <tr><td style="padding:20px 32px 4px;">
    {cards}
  </td></tr>

  <!-- Signature -->
  <tr><td style="padding:4px 32px 26px;font-size:15px;color:{INK};line-height:1.6;">{signature_html}</td></tr>

  <!-- Pied de page -->
  <tr><td style="background:#f7f9fc;padding:22px 32px;border-top:1px solid {BORDER};">
    <div style="color:{MUTED};font-size:12px;line-height:1.6;">
      <strong style="color:{BRAND};">Cultura Sabauda</strong> — Observatoire économique de l'espace sabaudo<br>
      Savoie · Piémont · Vallée d'Aoste · Nice · Alcotra<br>
      <a href="https://culturasabauda.eu" style="color:{MUTED};">culturasabauda.eu</a>
      &nbsp;·&nbsp; <a href="{{{{ unsubscribe }}}}" style="color:{MUTED};">Se désabonner</a>
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
"""
