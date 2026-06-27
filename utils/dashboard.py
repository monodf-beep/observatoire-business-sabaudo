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


# Feuille de style de la page « toute la veille » (page web autonome → on peut
# utiliser un <style> + media queries, contrairement à l'email). Couleurs en dur
# (mêmes que la charte) pour éviter le doublage d'accolades en f-string.
_VEILLE_CSS = (
    "*{box-sizing:border-box}"
    "body{margin:0;background:#eef1f5;color:#16202c;"
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
    ".wrap{max-width:1180px;margin:0 auto;padding:32px 18px 60px}"
    ".eyebrow{font-size:11px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase;color:#df664f}"
    ".brand{font-size:32px;font-weight:800;color:#3f5f96;line-height:1.05;margin:6px 0 2px}"
    ".brand span{color:#df664f}"
    ".sub{font-size:13px;color:#6b7280}"
    "h1{font-size:19px;font-weight:800;margin:22px 0 4px}"
    ".intro{font-size:13px;color:#6b7280;margin-bottom:6px}"
    ".filters{margin:10px 0 14px}"
    ".fbtn{font-size:13px;font-weight:700;cursor:pointer;border:1px solid #e5e7eb;border-radius:20px;"
    "padding:6px 13px;margin:0 7px 7px 0;background:#fff;color:#16202c}"
    ".fbtn.on{background:#16202c;color:#fff}"
    ".fbtn .c{opacity:.6;font-weight:600;margin-left:2px}"
    ".nav{position:sticky;top:0;z-index:20;background:#eef1f5;padding:10px 0 4px;margin:0 0 16px;"
    "border-bottom:1px solid #e5e7eb}"
    ".pill{display:inline-block;text-decoration:none;font-size:13px;font-weight:700;color:#16202c;"
    "background:#fff;border:1px solid #e5e7eb;border-radius:20px;padding:6px 13px;margin:0 7px 7px 0;white-space:nowrap}"
    ".pill .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:middle}"
    ".pill .c{color:#6b7280;font-weight:600}"
    ".board{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px;align-items:start}"
    ".col{background:#fff;border:1px solid #e5e7eb;border-top:3px solid #64748b;border-radius:12px;"
    "padding:12px 16px 14px;scroll-margin-top:64px}"
    ".col h2{font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px;"
    "padding-left:9px;border-left:4px solid #64748b}"
    ".col h2 .c{color:#6b7280;font-weight:600;margin-left:6px}"
    ".items{margin:0;padding:0;list-style:none}"
    ".item{padding:9px 0;border-bottom:1px solid #f0f2f5}"
    ".item:last-child{border-bottom:0}"
    ".item .t{font-size:14px;font-weight:600;line-height:1.35}"
    ".item .t a{color:#16202c;text-decoration:none;border-bottom:1px solid #df664f}"
    ".item .t span{color:#16202c}"
    ".item .m{font-size:12px;color:#6b7280;margin-top:3px}"
    ".empty{font-size:13px;color:#9aa3af;padding:6px 0 2px}"
    ".badge{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;"
    "border-radius:4px;padding:1px 6px;margin-right:7px}"
    ".bn{color:#3f5f96;background:#eef2fb;border:1px solid #c7d5ef}"
    ".br{color:#6b7280;background:#eef1f5;border:1px solid #e5e7eb}"
    "details.radar{margin-top:10px;border-top:1px dashed #e5e7eb;padding-top:4px}"
    "details.radar>summary{cursor:pointer;font-size:12px;font-weight:700;color:#6b7280;list-style:none;padding:6px 0}"
    "details.radar>summary::-webkit-details-marker{display:none}"
    "details.radar>summary .c{background:#eef1f5;border-radius:10px;padding:0 7px;margin-left:4px}"
    ".foot{border-top:1px solid #e5e7eb;padding-top:18px;margin-top:24px;font-size:12px;color:#6b7280}"
    ".foot a{color:#df664f}"
    "@media(max-width:640px){.board{grid-template-columns:1fr}.wrap{padding:24px 14px 50px}}"
)

_VEILLE_JS = (
    "<script>function vfilter(b){var f=b.getAttribute('data-f');"
    "document.querySelectorAll('.fbtn').forEach(function(x){x.className='fbtn'+(x===b?' on':'');});"
    "document.querySelectorAll('.item').forEach(function(li){"
    "var t=li.getAttribute('data-tier');var ok=(f==='all')||(t===f);li.style.display=ok?'':'none';});"
    "document.querySelectorAll('details.radar').forEach(function(d){d.open=(f==='radar');});"
    "document.querySelectorAll('.col').forEach(function(c){var vis=false;"
    "c.querySelectorAll('.item').forEach(function(li){if(li.style.display!=='none')vis=true;});"
    "c.style.display=vis?'':'none';});}</script>"
)


def _synthese_block(synthese: dict | None) -> str:
    """Encart éditorial « Synthèse de la semaine » : la une + les signaux que la
    newsletter a déjà rédigés (relus depuis son JSON — aucun appel IA en plus)."""
    if not synthese:
        return ""
    hero = synthese.get("hero") or {}
    signaux = synthese.get("signaux") or []
    if not hero and not signaux:
        return ""

    # Une.
    hero_html = ""
    if hero.get("title"):
        terr = hero.get("territory", "")
        title = escape(hero["title"])
        url = (hero.get("url") or "").strip()
        title_html = (f'<a href="{escape(url)}" target="_blank" rel="noopener" '
                      f'style="color:{INK};text-decoration:none;border-bottom:2px solid {ACCENT};">{title}</a>'
                      if url else title)
        hero_html = (
            (f'<div style="margin-bottom:8px;">{_tag(terr)}</div>' if terr else "")
            + f'<div style="font-size:19px;font-weight:800;line-height:1.3;color:{INK};margin-bottom:7px;">{title_html}</div>'
            + (f'<div style="font-size:14px;color:#374151;line-height:1.6;">{escape(hero.get("summary",""))}</div>'
               if hero.get("summary") else "")
        )

    # Signaux — on retire ceux qui répètent la une (même sujet).
    from utils.sources import same_story
    hero_title = hero.get("title", "")
    sig_rows = ""
    for s in signaux[:8]:
        if not s.get("title") or (hero_title and same_story(s["title"], hero_title)):
            continue
        terr = s.get("territory", "")
        color, label = _terr_color(terr), _terr_label(terr)
        url = (s.get("url") or "").strip()
        txt = escape(s["title"])
        txt = (f'<a href="{escape(url)}" target="_blank" rel="noopener" '
               f'style="color:{INK};text-decoration:none;border-bottom:1px solid {ACCENT};">{txt}</a>'
               if url else txt)
        sig_rows += (
            f'<tr><td style="padding:7px 0;border-bottom:1px solid {BORDER};">'
            f'<span style="font-size:11px;font-weight:700;color:{color};background:#eef2f7;'
            f'padding:2px 9px;border-radius:20px;margin-right:8px;white-space:nowrap;">{escape(label)}</span>{txt}</td></tr>'
        )
    sig_html = (
        f'<div style="font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;'
        f'color:{BRAND};margin:18px 0 8px;">Signaux de la semaine</div>'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;">{sig_rows}</table>'
        if sig_rows else ""
    )

    return (
        f'<div style="background:{CARD};border:1px solid {BORDER};border-left:4px solid {ACCENT};'
        f'border-radius:12px;padding:20px 22px;margin:0 0 22px;">'
        f'<div style="font-size:11px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;'
        f'color:{ACCENT};margin-bottom:10px;">Synthèse de la semaine</div>'
        f'{hero_html}{sig_html}</div>'
    )


def _suggest_form(suggest_url: str) -> str:
    """Formulaire public « Proposer une source » (POST vers l'admin, validé côté rédaction)."""
    if not suggest_url:
        return ""
    opts = '<option value="">Territoire…</option>' + "".join(
        f'<option value="{escape(t)}">{escape(_terr_label(t))}</option>' for t in _TERR_ORDER
    )
    inp = ("font-size:14px;padding:9px 11px;border:1px solid %s;border-radius:8px;"
           "background:#fff;color:%s;" % (BORDER, INK))
    return (
        f'<div style="background:#fbfcfe;border:1px solid {BORDER};border-left:4px solid {ACCENT};border-radius:12px;padding:22px 24px;margin:28px 0 0;">'
        f'<div style="font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:{ACCENT};margin-bottom:6px;">Construisons cette veille ensemble</div>'
        f'<div style="font-size:14px;color:{INK};line-height:1.6;margin-bottom:14px;">Cet observatoire est <strong>collaboratif</strong> : il se nourrit des sources que vous connaissez. '
        f'Un média, une institution, un acteur économique du territoire à suivre ? <strong>Proposez-le</strong> — la rédaction le vérifie et l\'ajoute à la veille.</div>'
        f'<form method="post" action="{escape(suggest_url)}">'
        f'<div style="display:flex;flex-wrap:wrap;gap:8px;">'
        f'<input type="url" name="url" required placeholder="https://… (lien de la source)" style="{inp}flex:2;min-width:220px;">'
        f'<select name="territoire" style="{inp}flex:1;min-width:140px;">{opts}</select>'
        f'<input type="text" name="nom" placeholder="Nom (optionnel)" style="{inp}flex:1;min-width:140px;">'
        f'</div>'
        f'<input type="text" name="note" placeholder="Pourquoi cette source ? (optionnel)" style="{inp}width:100%;margin-top:8px;">'
        f'<button type="submit" style="margin-top:10px;background:{ACCENT};color:#fff;border:0;border-radius:8px;'
        f'padding:10px 20px;font-size:14px;font-weight:700;cursor:pointer;">Proposer cette source</button>'
        f'</form></div>'
    )


def render_veille_page(week_label: str, by_territory: dict, *, generated_at: str = "",
                       newsletters: list | None = None, synthese: dict | None = None,
                       suggest_url: str = "") -> str:
    """Page LECTEUR « toute la veille de la semaine » : la liste COMPLÈTE des sujets
    captés, organisée par territoire avec une navigation collante pour sauter d'un
    territoire à l'autre sans scroller. Les sujets de presse sont gardés en RADAR
    (texte simple, sans lien vers le journal) ; seules les sources officielles sont
    cliquables. Page de référence publique."""
    total = sum(len(v) for v in by_territory.values())
    ordered = [t for t in _TERR_ORDER if by_territory.get(t)]
    ordered += [t for t in by_territory if t not in _TERR_ORDER and by_territory.get(t)]

    def _tier(it: dict) -> str:
        """Priorité d'affichage : newsletter > officiel (RSS) > radar (presse)."""
        if it.get("press"):
            return "radar"
        if it.get("newsletter"):
            return "news"
        return "officiel"

    def _by_date(seq: list) -> list:
        """Plus récent en haut (date ISO AAAA-MM-JJ triée à l'envers)."""
        return sorted(seq, key=lambda it: (it.get("date") or ""), reverse=True)

    def _li(it: dict, tier: str) -> str:
        title = escape(it.get("title", "(sans titre)"))
        url = (it.get("url") or "").strip()
        t_html = (f'<a href="{escape(url)}" target="_blank" rel="noopener">{title}</a>'
                  if url else f"<span>{title}</span>")
        badge = {"news": '<span class="badge bn">Newsletter</span>',
                 "radar": '<span class="badge br">Radar</span>'}.get(tier, "")
        meta = " · ".join(x for x in [escape(it.get("source", "")), it.get("date", "")] if x)
        return (
            f'<li class="item" data-tier="{tier}">'
            f'<div class="t">{t_html}</div>'
            + (f'<div class="m">{badge}{meta}</div>' if (meta or badge) else "")
            + "</li>"
        )

    # Compteurs par tier (pour les boutons de filtre).
    n_news = sum(1 for v in by_territory.values() for it in v if _tier(it) == "news")
    n_off = sum(1 for v in by_territory.values() for it in v if _tier(it) == "officiel")
    n_radar = sum(1 for v in by_territory.values() for it in v if _tier(it) == "radar")

    # Navigation collante (utile surtout en 1 colonne / mobile).
    nav_pills = ""
    for terr in ordered:
        color, label = _terr_color(terr), _terr_label(terr)
        nav_pills += (
            f'<a class="pill" href="#t-{escape(terr)}">'
            f'<span class="dot" style="background:{color};"></span>{escape(label)}'
            f'<span class="c">&nbsp;{len(by_territory[terr])}</span></a>'
        )
    nav = f'<div class="nav">{nav_pills}</div>'

    # Filtres.
    fbtns = ""
    for key, lbl, n in [("all", "Tout", total), ("officiel", "Sources officielles", n_off),
                        ("news", "Newsletters", n_news), ("radar", "Radar presse", n_radar)]:
        fbtns += (f'<button type="button" class="fbtn{" on" if key == "all" else ""}" '
                  f'data-f="{key}" onclick="vfilter(this)">{escape(lbl)} '
                  f'<span class="c">{n}</span></button>')
    filterbar = f'<div class="filters">{fbtns}</div>'

    # Colonnes (board) : une carte par territoire, tiers ordonnés, radar en accordéon.
    cols = ""
    for terr in ordered:
        items = by_territory[terr]
        color, label = _terr_color(terr), _terr_label(terr)
        news = _by_date([it for it in items if _tier(it) == "news"])
        offi = _by_date([it for it in items if _tier(it) == "officiel"])
        radar = _by_date([it for it in items if _tier(it) == "radar"])
        top = "".join(_li(it, "news") for it in news) + "".join(_li(it, "officiel") for it in offi)
        top_html = (f'<ul class="items">{top}</ul>' if top
                    else '<div class="empty">Aucune source officielle ni newsletter cette semaine.</div>')
        radar_block = ""
        if radar:
            radar_html = "".join(_li(it, "radar") for it in radar)
            radar_block = (f'<details class="radar"><summary>Radar presse '
                           f'<span class="c">{len(radar)}</span></summary>'
                           f'<ul class="items">{radar_html}</ul></details>')
        cols += (
            f'<section class="col" id="t-{escape(terr)}" style="border-top-color:{color};">'
            f'<h2 style="color:{color};border-color:{color};">{escape(label)}'
            f'<span class="c">{len(items)}</span></h2>'
            f"{top_html}{radar_block}</section>"
        )
    board = f'<div class="board">{cols}</div>'

    gen = f" · mis à jour le {escape(generated_at)}" if generated_at else ""
    nl_table = _newsletters_table(newsletters or [])
    synthese_block = _synthese_block(synthese)
    return (
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Business Sabaudo — Toute la veille</title>"
        f"<style>{_VEILLE_CSS}</style></head>"
        '<body><div class="wrap">'
        '<div class="eyebrow">Observatoire économique</div>'
        '<div class="brand">Business Sabaudo<span>.</span></div>'
        '<div class="sub">Savoie · Piémont · Vallée d\'Aoste · Nice · Alcotra</div>'
        f'<h1>Toute la veille — {escape(week_label)}</h1>'
        f'<div class="intro">{total} sujets économiques captés sur l\'espace sabaudo cette semaine{gen}.</div>'
        '<div class="intro">En tête : <strong>newsletters</strong> et <strong>sources officielles</strong>. '
        'La presse (<strong>Radar</strong>) est repliée par territoire : elle sert à ne rien manquer.</div>'
        f"{synthese_block}{filterbar}{nl_table}{nav}{board}"
        f"{_suggest_form(suggest_url)}"
        '<div class="foot">Veille collectée et traitée automatiquement par l\'Observatoire économique '
        'de Cultura Sabauda. <a href="https://culturasabauda.eu">culturasabauda.eu</a></div>'
        f"{_VEILLE_JS}</div></body></html>"
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
