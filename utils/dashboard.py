"""Tableau de bord visuel « Business Sabaudo » (page HTML autonome).

À partir des données de synthèse hebdomadaires (les JSON produits par
scripts/synthesize.py), produit une page HTML unique, sans dépendance externe
(CSS + SVG en ligne), qui donne une vue d'ensemble :

- indicateurs clés (semaines couvertes, signaux, territoires actifs) ;
- volume de brèves par semaine (histogramme) ;
- répartition des signaux par territoire ;
- la une et les signaux de la dernière semaine.

Aucune librairie graphique : tout est rendu en HTML/CSS/SVG pour rester portable
(ouvrable hors-ligne, déposable tel quel sur le Drive ou un hébergement statique).
"""
from __future__ import annotations

from html import escape

# Charte Cultura Sabauda (alignée sur la newsletter).
BRAND = "#3f5f96"
ACCENT = "#df664f"
INK = "#16202c"
MUTED = "#6b7280"
BORDER = "#e5e7eb"
BG = "#eef1f5"
CARD = "#ffffff"

# Couleur de pastille par territoire (réutilisée pour les barres).
_TERRITORY = {
    "Savoie": ("#1a56b0", "Savoie"),
    "Piemonte": ("#b3261e", "Piémont"),
    "Vallee-Aoste": ("#1e7d34", "Vallée d'Aoste"),
    "Nice": ("#b25e00", "Nice"),
    "Alcotra": ("#5a3aa5", "Alcotra"),
}
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _terr_color(territory: str) -> str:
    return _TERRITORY.get(territory, ("#64748b", territory))[0]


def _terr_label(territory: str) -> str:
    return _TERRITORY.get(territory, ("#64748b", territory or "—"))[1]


def _territory_counts(data: dict) -> dict[str, int]:
    """Compte les éléments (une + brèves + signaux) par territoire pour une semaine."""
    counts: dict[str, int] = {}
    entries = []
    if data.get("hero"):
        entries.append(data["hero"].get("territory"))
    for it in data.get("items", []):
        entries.append(it.get("territory"))
    for s in data.get("signaux", []):
        entries.append(s.get("territory"))
    for terr in entries:
        if terr:
            counts[terr] = counts.get(terr, 0) + 1
    return counts


def _kpi(value: str, label: str) -> str:
    return (
        '<div style="flex:1;min-width:140px;background:%s;border:1px solid %s;'
        'border-radius:12px;padding:18px 20px;">' % (CARD, BORDER)
        + f'<div style="font-size:30px;font-weight:800;color:{BRAND};line-height:1;">{value}</div>'
        + f'<div style="font-size:12px;font-weight:700;letter-spacing:.4px;'
          f'text-transform:uppercase;color:{MUTED};margin-top:7px;">{escape(label)}</div></div>'
    )


def _eyebrow(text: str) -> str:
    return (
        '<div style="margin:0 0 14px;">'
        f'<span style="display:inline-block;width:26px;height:3px;background:{ACCENT};'
        'vertical-align:middle;margin-right:9px;border-radius:2px;"></span>'
        f'<span style="font-size:12px;font-weight:800;letter-spacing:1.5px;'
        f'text-transform:uppercase;color:{BRAND};vertical-align:middle;">{escape(text)}</span></div>'
    )


def _bars_weekly(weeks: list[tuple[str, dict]]) -> str:
    """Histogramme du volume de brèves par semaine (barres verticales CSS)."""
    vols = [(wid, 1 + len(d.get("items", []))) for wid, d in weeks]  # une + brèves
    top = max((v for _, v in vols), default=1)
    cols = ""
    for wid, v in vols:
        h = max(6, round(100 * v / top))
        short = wid.split("-W")[-1].lstrip("0") or wid
        cols += (
            '<td valign="bottom" style="text-align:center;padding:0 4px;vertical-align:bottom;">'
            f'<div style="font-size:11px;color:{MUTED};margin-bottom:4px;">{v}</div>'
            f'<div style="width:26px;height:{h}px;background:{BRAND};border-radius:4px 4px 0 0;'
            'margin:0 auto;"></div>'
            f'<div style="font-size:10px;color:{MUTED};margin-top:5px;">S{escape(short)}</div></td>'
        )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">'
        f"<tr>{cols}</tr></table>"
    )


def _bars_territory(totals: dict[str, int]) -> str:
    """Barres horizontales : total de signaux/brèves par territoire."""
    if not totals:
        return f'<div style="color:{MUTED};font-size:14px;">Aucune donnée.</div>'
    top = max(totals.values())
    order = sorted(totals, key=lambda t: totals[t], reverse=True)
    rows = ""
    for terr in order:
        v = totals[terr]
        w = max(3, round(100 * v / top))
        color = _terr_color(terr)
        rows += (
            '<tr>'
            f'<td style="width:120px;font-size:13px;color:{INK};font-weight:600;padding:5px 10px 5px 0;'
            'white-space:nowrap;">'
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background:{color};margin-right:7px;"></span>{escape(_terr_label(terr))}</td>'
            f'<td style="padding:5px 0;"><span style="display:inline-block;height:14px;width:{w}%;'
            f'background:{color};border-radius:7px;vertical-align:middle;"></span>'
            f'<span style="font-size:12px;color:{MUTED};font-weight:700;margin-left:8px;">{v}</span></td>'
            '</tr>'
        )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


def _tag(territory: str) -> str:
    color = _terr_color(territory)
    return (
        '<span style="display:inline-block;background:#eef2f7;color:#42526b;font-size:11px;'
        'font-weight:700;letter-spacing:.4px;text-transform:uppercase;padding:3px 10px;'
        'border-radius:20px;">'
        f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
        f'background:{color};margin-right:6px;"></span>{escape(_terr_label(territory))}</span>'
    )


def _latest_block(week_id: str, data: dict) -> str:
    hero = data.get("hero") or {}
    sig = data.get("signaux", [])
    hero_html = ""
    if hero:
        link = hero.get("url", "")
        title = escape(hero.get("title", ""))
        title_html = f'<a href="{escape(link)}" style="color:{INK};text-decoration:none;">{title}</a>' if link else title
        hero_html = (
            f'<div style="margin-bottom:6px;">{_tag(hero.get("territory", ""))}</div>'
            f'<div style="font-size:20px;font-weight:800;color:{INK};line-height:1.3;margin-bottom:6px;">{title_html}</div>'
            f'<div style="font-size:14px;color:#374151;line-height:1.6;">{escape(hero.get("summary", ""))}</div>'
        )
    sig_html = ""
    for s in sig:
        sig_html += (
            f'<tr><td style="padding:8px 0;border-bottom:1px solid {BORDER};">'
            f'{_tag(s.get("territory", ""))}'
            f'<span style="font-size:14px;color:{INK};font-weight:600;margin-left:8px;">{escape(s.get("title", ""))}</span>'
            "</td></tr>"
        )
    return (
        f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:12px;padding:22px;">'
        f'{_eyebrow("À la une — " + escape(data.get("week_label", week_id)))}'
        f"{hero_html}"
        + (f'<div style="margin-top:18px;">{_eyebrow("Signaux de la semaine")}'
           f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{sig_html}</table></div>'
           if sig_html else "")
        + "</div>"
    )


_TERR_ORDER = ["Savoie", "Piemonte", "Vallee-Aoste", "Nice", "Alcotra"]

# Statuts des newsletters : libellé + couleur de pastille.
_NL_STATUS = {
    "actif": ("Abonné", "#15803d", "#dcfce7"),
    "attente": ("En attente du 1er envoi", "#b45309", "#fef3c7"),
    "inactif": ("Inactif", "#6b7280", "#f3f4f6"),
    "candidat": ("À souscrire", "#3f5f96", "#e8eefb"),
}


def _newsletters_table(newsletters: list) -> str:
    """Section repliable « Newsletters suivies » : à quoi on est abonné + reçu cette semaine."""
    if not newsletters:
        return ""
    order = {"actif": 0, "attente": 1, "candidat": 2, "inactif": 3}
    nls = sorted(newsletters, key=lambda n: (order.get(n.get("statut"), 9), n.get("nom", "")))
    n_actif = sum(1 for n in nls if n.get("statut") == "actif")
    n_attente = sum(1 for n in nls if n.get("statut") == "attente")
    rows = ""
    for nl in nls:
        statut = nl.get("statut", "")
        label, color, bg = _NL_STATUS.get(statut, ("—", MUTED, BG))
        terr = _terr_label(nl.get("territoire", ""))
        recue = nl.get("recue")
        if statut == "actif":
            week = ('<span style="color:#15803d;font-weight:700;">● reçue</span>'
                    if recue else '<span style="color:#9aa3af;">○ rien cette semaine</span>')
        else:
            week = f'<span style="color:#9aa3af;">—</span>'
        badge = (f'<span style="display:inline-block;font-size:11px;font-weight:700;color:{color};'
                 f'background:{bg};border-radius:20px;padding:2px 10px;white-space:nowrap;">{label}</span>')
        rows += (
            f'<tr style="border-bottom:1px solid {BORDER};">'
            f'<td style="padding:9px 12px 9px 0;font-weight:600;color:{INK};">{escape(nl.get("nom",""))}</td>'
            f'<td style="padding:9px 12px 9px 0;color:{MUTED};font-size:13px;white-space:nowrap;">{escape(terr)}</td>'
            f'<td style="padding:9px 12px 9px 0;">{badge}</td>'
            f'<td style="padding:9px 0;font-size:13px;">{week}</td>'
            "</tr>"
        )
    return (
        f'<details style="background:{CARD};border:1px solid {BORDER};border-radius:12px;'
        f'padding:6px 18px;margin:0 0 20px;">'
        f'<summary style="cursor:pointer;font-size:13px;font-weight:800;color:{BRAND};'
        f'padding:10px 0;list-style:none;">📬 Newsletters suivies '
        f'<span style="color:{MUTED};font-weight:600;">— {n_actif} abonné·e·s, {n_attente} en attente</span></summary>'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin:6px 0 12px;">{rows}</table>'
        f'<div style="font-size:12px;color:{MUTED};padding-bottom:8px;">« ● reçue » = au moins un email capté cette '
        "semaine. Pour ajouter une newsletter : s'abonner, puis l'inscrire dans la collecte.</div></details>"
    )


def render_veille_page(week_label: str, by_territory: dict, *, generated_at: str = "",
                       newsletters: list | None = None) -> str:
    """Page LECTEUR « toute la veille de la semaine » : la liste COMPLÈTE des sujets
    captés, organisée par territoire avec une navigation collante pour sauter d'un
    territoire à l'autre sans scroller. Les sujets de presse sont gardés en RADAR
    (texte simple, sans lien vers le journal) ; seules les sources officielles sont
    cliquables. Page de référence publique."""
    total = sum(len(v) for v in by_territory.values())
    ordered = [t for t in _TERR_ORDER if by_territory.get(t)]
    ordered += [t for t in by_territory if t not in _TERR_ORDER and by_territory.get(t)]

    # Barre de navigation collante : une pastille par territoire (ancre + compteur).
    nav_pills = ""
    for terr in ordered:
        color, label = _terr_color(terr), _terr_label(terr)
        nav_pills += (
            f'<a href="#t-{escape(terr)}" style="display:inline-block;text-decoration:none;'
            f'font-size:13px;font-weight:700;color:{INK};background:{CARD};border:1px solid {BORDER};'
            f'border-radius:20px;padding:6px 13px;margin:0 7px 7px 0;white-space:nowrap;">'
            f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
            f'background:{color};margin-right:7px;vertical-align:middle;"></span>{escape(label)}'
            f'<span style="color:{MUTED};font-weight:600;">&nbsp;{len(by_territory[terr])}</span></a>'
        )
    nav = (
        f'<div style="position:sticky;top:0;z-index:20;background:{BG};'
        f'padding:12px 0 5px;margin:0 0 18px;border-bottom:1px solid {BORDER};">{nav_pills}</div>'
    )

    # Filtre : Tout / Officiel / Newsletters / Radar presse (toggle JS navigateur).
    n_off = sum(1 for items in by_territory.values() for it in items if not it.get("press"))
    n_radar = total - n_off
    n_news = sum(1 for items in by_territory.values() for it in items if it.get("newsletter"))
    fbtns = ""
    for key, lbl, n in [("all", "Tout", total), ("officiel", "Sources officielles", n_off),
                        ("news", "Newsletters", n_news), ("radar", "Radar presse", n_radar)]:
        on = key == "all"
        fbtns += (
            f'<button type="button" data-f="{key}" onclick="vfilter(this)" '
            f'style="font-size:13px;font-weight:700;cursor:pointer;border:1px solid {BORDER};'
            f'border-radius:20px;padding:6px 13px;margin:0 7px 7px 0;'
            f'background:{INK if on else CARD};color:{"#fff" if on else INK};">'
            f'{escape(lbl)} <span style="opacity:.6;font-weight:600;">{n}</span></button>'
        )
    filterbar = f'<div style="margin:4px 0 14px;">{fbtns}</div>'
    filterjs = (
        "<script>function vfilter(b){var f=b.getAttribute('data-f');"
        "document.querySelectorAll('[data-f]').forEach(function(x){var on=x===b;"
        f"x.style.background=on?'{INK}':'{CARD}';x.style.color=on?'#fff':'{INK}';}});"
        "document.querySelectorAll('li[data-type]').forEach(function(li){"
        "var ok=(f==='all')||(f==='news'?li.getAttribute('data-news')==='1'"
        ":li.getAttribute('data-type')===f);li.style.display=ok?'':'none';});"
        "document.querySelectorAll('section[data-veille]').forEach(function(s){var vis=false;"
        "s.querySelectorAll('li[data-type]').forEach(function(li){"
        "if(li.style.display!=='none')vis=true;});s.style.display=vis?'':'none';});}</script>"
    )

    sections = ""
    for terr in ordered:
        items = by_territory[terr]
        color, label = _terr_color(terr), _terr_label(terr)
        rows = ""
        for it in items:
            title = escape(it.get("title", "(sans titre)"))
            url = (it.get("url") or "").strip()
            is_press_item = bool(it.get("press"))
            if url:
                title_html = (f'<a href="{escape(url)}" target="_blank" rel="noopener" '
                              f'style="color:{INK};text-decoration:none;border-bottom:1px solid {ACCENT};">{title}</a>')
            else:
                # Radar : texte simple, pas de lien vers le journal.
                title_html = f'<span style="color:{INK};">{title}</span>'
            src = escape(it.get("source", ""))
            is_newsletter = bool(it.get("newsletter"))
            if is_press_item:
                badge = (f'<span style="display:inline-block;font-size:10px;font-weight:700;letter-spacing:.4px;'
                         f'text-transform:uppercase;color:{MUTED};background:{BG};border:1px solid {BORDER};'
                         f'border-radius:4px;padding:1px 6px;margin-right:7px;">Radar</span>')
            elif is_newsletter:
                badge = (f'<span style="display:inline-block;font-size:10px;font-weight:700;letter-spacing:.4px;'
                         f'text-transform:uppercase;color:{BRAND};background:#eef2fb;border:1px solid #c7d5ef;'
                         f'border-radius:4px;padding:1px 6px;margin-right:7px;">Newsletter</span>')
            else:
                badge = ""
            meta = " · ".join(x for x in [src, it.get("date", "")] if x)
            dtype = "radar" if is_press_item else "officiel"
            news_attr = ' data-news="1"' if is_newsletter else ""
            rows += (
                f'<li data-type="{dtype}"{news_attr} style="padding:11px 0;border-bottom:1px solid {BORDER};list-style:none;">'
                f'<div style="font-size:15px;font-weight:600;line-height:1.4;">{title_html}</div>'
                + (f'<div style="font-size:12px;color:{MUTED};margin-top:3px;">{badge}{meta}</div>'
                   if (meta or badge) else "")
                + "</li>"
            )
        sections += (
            f'<section id="t-{escape(terr)}" data-veille="1" style="margin:0 0 30px;scroll-margin-top:64px;">'
            f'<h2 style="font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:1px;'
            f'color:{color};margin:0 0 4px;border-left:4px solid {color};padding-left:10px;">'
            f'{escape(label)} <span style="color:{MUTED};font-weight:600;">({len(items)})</span></h2>'
            f'<ul style="margin:0;padding:0;">{rows}</ul></section>'
        )
    gen = f" · mis à jour le {escape(generated_at)}" if generated_at else ""
    nl_table = _newsletters_table(newsletters or [])
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Business Sabaudo — Toute la veille</title></head>"
        f'<body style="margin:0;background:{BG};font-family:{_FONT};color:{INK};">'
        f'<div style="max-width:760px;margin:0 auto;padding:34px 18px 60px;">'
        f'<div style="font-size:11px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase;color:{ACCENT};">Observatoire économique</div>'
        f'<div style="font-size:32px;font-weight:800;color:{BRAND};line-height:1.05;margin:6px 0 2px;">Business Sabaudo<span style="color:{ACCENT};">.</span></div>'
        f'<div style="font-size:13px;color:{MUTED};">Savoie · Piémont · Vallée d\'Aoste · Nice · Alcotra</div>'
        f'<h1 style="font-size:19px;font-weight:800;margin:22px 0 4px;">Toute la veille — {escape(week_label)}</h1>'
        f'<div style="font-size:13px;color:{MUTED};margin-bottom:6px;">{total} sujets économiques captés sur l\'espace sabaudo cette semaine{gen}.</div>'
        f'<div style="font-size:12px;color:{MUTED};margin-bottom:4px;">Les sujets marqués <strong>Radar</strong> proviennent de la presse : ils servent à ne rien manquer, sans lien vers le journal.</div>'
        f"{filterbar}"
        f"{nl_table}"
        f"{nav}"
        f"{sections}"
        f'<div style="border-top:1px solid {BORDER};padding-top:18px;margin-top:10px;font-size:12px;color:{MUTED};">'
        "Veille collectée et traitée automatiquement par l'Observatoire économique de Cultura Sabauda. "
        f'<a href="https://culturasabauda.eu" style="color:{ACCENT};">culturasabauda.eu</a></div>'
        f"{filterjs}"
        "</div></body></html>"
    )


def render_dashboard(weeks: list[tuple[str, dict]], *, generated_at: str = "") -> str:
    """Assemble le tableau de bord. `weeks` = liste (week_id, data) triée croissant."""
    weeks = sorted(weeks, key=lambda wd: wd[0])
    # Agrégats
    totals: dict[str, int] = {}
    total_signaux = 0
    for _, d in weeks:
        for terr, n in _territory_counts(d).items():
            totals[terr] = totals.get(terr, 0) + n
        total_signaux += len(d.get("signaux", []))
    nb_weeks = len(weeks)
    nb_terr = len(totals)
    total_breves = sum(1 + len(d.get("items", [])) for _, d in weeks)

    kpis = (
        _kpi(str(nb_weeks), "semaines couvertes")
        + _kpi(str(total_breves), "brèves publiées")
        + _kpi(str(total_signaux), "signaux forts")
        + _kpi(str(nb_terr), "territoires actifs")
    )
    latest = _latest_block(*weeks[-1]) if weeks else (
        f'<div style="color:{MUTED};">Aucune synthèse disponible pour le moment.</div>'
    )
    footer_when = f" · généré le {escape(generated_at)}" if generated_at else ""

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Business Sabaudo — Tableau de bord</title></head>
<body style="margin:0;padding:0;background:{BG};font-family:{_FONT};color:{INK};">
<div style="max-width:920px;margin:0 auto;padding:28px 18px 48px;">

  <div style="margin-bottom:8px;">
    <span style="font-size:11px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase;color:{ACCENT};">Observatoire économique</span>
  </div>
  <div style="font-size:34px;font-weight:800;letter-spacing:-.5px;color:{BRAND};line-height:1;">
    Business Sabaudo<span style="color:{ACCENT};">.</span></div>
  <div style="font-size:13px;color:{MUTED};margin:9px 0 24px;">
    Savoie · Piémont · Vallée d'Aoste · Nice · Alcotra — tableau de bord de la veille{footer_when}</div>

  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:26px;">{kpis}</div>

  <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:26px;">
    <div style="flex:1;min-width:280px;background:{CARD};border:1px solid {BORDER};border-radius:12px;padding:22px;">
      {_eyebrow("Volume de brèves par semaine")}
      {_bars_weekly(weeks)}
    </div>
    <div style="flex:1;min-width:280px;background:{CARD};border:1px solid {BORDER};border-radius:12px;padding:22px;">
      {_eyebrow("Répartition par territoire")}
      {_bars_territory(totals)}
    </div>
  </div>

  {latest}

  <div style="color:{MUTED};font-size:12px;line-height:1.6;margin-top:30px;text-align:center;">
    <strong style="color:{BRAND};">Cultura Sabauda</strong> — Veille assistée par IA, sélectionnée et validée par la rédaction.<br>
    <a href="https://culturasabauda.eu" style="color:{MUTED};">culturasabauda.eu</a>
  </div>

</div></body></html>
"""
