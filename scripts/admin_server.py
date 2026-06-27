#!/usr/bin/env python3
"""Page admin privée « Business Sabaudo » : un bouton pour (re)lancer la newsletter
et un bouton pour rafraîchir la page de veille, sans toucher au terminal.

Sécurité — c'est une page qui DÉPENSE du crédit API, donc protégée :
- authentification HTTP Basic obligatoire (ADMIN_USER / ADMIN_PASS dans .env) ;
  sans identifiants configurés, le service REFUSE de démarrer (aucun mot de passe
  par défaut) ;
- aucune entrée utilisateur n'est injectée dans une commande (commandes figées) ;
- un seul run à la fois (verrou) pour éviter les doublons coûteux ;
- à exposer derrière HTTPS (Traefik) — voir deploy/observatoire-admin.service.

Usage local :
    ADMIN_USER=franck ADMIN_PASS=… python scripts/admin_server.py
    # puis http://127.0.0.1:8099/  (ou via tunnel SSH / Traefik)
"""
from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import Flask, Response, redirect, request, url_for

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
from utils.logger import get_logger  # noqa: E402

log = get_logger("admin_server")

STATE_DIR = ROOT / "logs"
STATE_FILE = STATE_DIR / "admin_runs.json"
PY = os.getenv("ADMIN_PYTHON") or sys.executable
# Préfixe d'URL quand la page est servie derrière un proxy sous un sous-chemin
# (ex. ADMIN_BASE_PATH=/admin → page sur https://…/admin). Vide = racine.
BASE = os.getenv("ADMIN_BASE_PATH", "").rstrip("/")

# Tâches déclenchables — commandes FIGÉES (aucune interpolation d'entrée).
TASKS = {
    "newsletter": {
        "label": "Générer la newsletter (brouillon Brevo)",
        "argv": ["bash", "-lc",
                 f"'{PY}' scripts/triage.py && '{PY}' scripts/synthesize.py --upload --brevo --force"],
        "note": "Tri IA (automatique) puis création d'un brouillon Brevo. Consomme du "
                "crédit API — aucun envoi automatique.",
    },
    "veille": {
        "label": "Rafraîchir la page « toute la veille »",
        "argv": ["bash", "-lc", f"'{PY}' scripts/triage.py && '{PY}' scripts/build_dashboard.py"],
        "note": "Tri IA (automatique) — pertinence + titres propres — puis republication. "
                "Les sujets déjà jugés sont en cache (gratuit) ; seuls les NOUVEAUX "
                "consomment un peu de crédit.",
    },
}

app = Flask(__name__)


def _credentials() -> tuple[str, str] | None:
    user = os.getenv("ADMIN_USER", "").strip()
    password = os.getenv("ADMIN_PASS", "")
    return (user, password) if user and password else None


def _check_auth(auth) -> bool:
    creds = _credentials()
    if not creds or auth is None:
        return False
    user_ok = hmac.compare_digest(auth.username or "", creds[0])
    pass_ok = hmac.compare_digest(auth.password or "", creds[1])
    return user_ok and pass_ok


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _check_auth(request.authorization):
            return Response(
                "Authentification requise.", 401,
                {"WWW-Authenticate": 'Basic realm="Business Sabaudo Admin"'},
            )
        return view(*args, **kwargs)

    return wrapped


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def _running_task() -> str | None:
    """Renvoie la clé de la tâche en cours d'exécution, ou None."""
    state = _load_state()
    for key, info in state.items():
        if info.get("status") == "running" and _pid_alive(info.get("pid", -1)):
            return key
    return None


def _launch(task_key: str) -> tuple[bool, str]:
    task = TASKS[task_key]
    busy = _running_task()
    if busy:
        return False, f"Un traitement est déjà en cours ({TASKS[busy]['label']}). Réessaie après."

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logf = STATE_DIR / f"admin_{task_key}.log"
    started = datetime.now(timezone.utc)
    # On enchaîne la commande et l'écriture du code retour dans le MÊME process
    # détaché : le code retour permet d'afficher succès/échec ensuite.
    rc_file = STATE_DIR / f"admin_{task_key}.rc"
    rc_file.unlink(missing_ok=True)  # repart de zéro pour éviter le faux-positif PID réutilisé
    quoted = " ".join(_shquote(a) for a in task["argv"])
    shell_cmd = f'{quoted}; echo $? > {_shquote(str(rc_file))}'
    with open(logf, "ab") as fh:
        fh.write(f"\n\n===== {started.isoformat()} — {task['label']} =====\n".encode())
        proc = subprocess.Popen(
            ["bash", "-lc", shell_cmd], cwd=str(ROOT),
            stdout=fh, stderr=subprocess.STDOUT, start_new_session=True,
        )
    state = _load_state()
    state[task_key] = {
        "status": "running", "pid": proc.pid,
        "started": started.isoformat(), "label": task["label"],
    }
    _save_state(state)
    log.info("Tâche lancée : %s (pid=%s)", task_key, proc.pid)
    return True, f"« {task['label']} » lancé. Suis l'avancement ci-dessous."


def _shquote(s: str) -> str:
    import shlex

    return shlex.quote(s)


_ADMIN_CSS = (
    "*{box-sizing:border-box}"
    "body{margin:0;background:linear-gradient(180deg,#eef2f8,#e6eaf1);min-height:100vh;"
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#16202c}"
    ".wrap{max-width:780px;margin:0 auto;padding:42px 22px 64px}"
    ".eyebrow{font-size:11px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:#df664f}"
    ".h1{font-size:30px;font-weight:800;color:#2f4a78;letter-spacing:-.3px;margin:5px 0 26px}"
    ".h1 b{color:#df664f;font-weight:800}"
    ".card{background:#fff;border:1px solid #e9edf3;border-radius:16px;padding:24px;margin-bottom:18px;"
    "box-shadow:0 1px 2px rgba(20,32,44,.04),0 8px 24px rgba(20,32,44,.05)}"
    ".sec{font-size:11px;font-weight:800;letter-spacing:1.3px;text-transform:uppercase;color:#3f5f96;margin-bottom:14px}"
    ".flash{background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;border-radius:10px;padding:13px 16px;"
    "margin-bottom:18px;font-size:14px;font-weight:600}"
    ".flow{overflow-x:auto;white-space:nowrap;padding:4px 0 8px;margin:0 -4px}"
    ".node{display:inline-block;vertical-align:middle;width:114px;text-align:center;background:#fff;"
    "border:1px solid #e9edf3;border-radius:14px;padding:13px 8px;box-shadow:0 2px 10px rgba(20,32,44,.07)}"
    ".node .ic{font-size:22px;line-height:1}"
    ".node .nm{font-size:12px;font-weight:700;margin:7px 0 7px;color:#16202c}"
    ".node .st{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;"
    "border-radius:20px;padding:2px 10px}"
    ".node .wh{font-size:10px;color:#9aa3af;margin-top:6px}"
    ".arrow{display:inline-block;color:#cbd2dc;font-size:18px;font-weight:700;vertical-align:middle;padding:0 3px}"
    ".chip{display:inline-block;vertical-align:middle;background:#f4f6f9;border:1px dashed #cbd2dc;border-radius:20px;"
    "padding:10px 14px;margin:0 3px;font-size:12px;font-weight:700;color:#52607a}"
    ".legend{font-size:11px;color:#9aa3af;margin-top:14px;line-height:1.6}"
    ".btn{display:block;width:100%;border:0;border-radius:12px;padding:15px 22px;font-size:15px;font-weight:700;"
    "color:#fff;background:linear-gradient(135deg,#4a6aa5,#3f5f96);cursor:pointer;"
    "box-shadow:0 5px 16px rgba(63,95,150,.28);transition:transform .08s ease,box-shadow .08s ease}"
    ".btn:hover{transform:translateY(-1px);box-shadow:0 8px 20px rgba(63,95,150,.34)}"
    ".btn.alt{background:linear-gradient(135deg,#e3795f,#d4664c);box-shadow:0 5px 16px rgba(212,102,76,.28)}"
    ".btn.alt:hover{box-shadow:0 8px 20px rgba(212,102,76,.34)}"
    ".btn:disabled{background:#aeb6c2;box-shadow:none;cursor:not-allowed;transform:none}"
    ".note{font-size:12px;color:#6b7280;margin:8px 2px 18px;line-height:1.55}"
    ".busy{font-size:13px;color:#b45309;font-weight:700;margin-bottom:16px}"
    "table.t{width:100%;border-collapse:collapse;font-size:13px}"
    "table.t th{text-align:left;padding:7px 12px 7px 0;font-size:10px;text-transform:uppercase;"
    "letter-spacing:.6px;color:#9aa3af;border-bottom:1px solid #e9edf3;font-weight:800}"
    "table.t td{padding:8px 12px 8px 0;border-bottom:1px solid #f1f3f7}"
    "summary{cursor:pointer;list-style:none}summary::-webkit-details-marker{display:none}"
    "code{background:#f1f3f7;border-radius:5px;padding:1px 6px;font-size:12px}"
    ".sgr{border:1px solid #e9edf3;border-radius:12px;padding:13px 15px;margin-bottom:10px;background:#fcfdfe}"
    ".sgr .u{font-weight:700;font-size:14px;word-break:break-all;color:#2f4a78}"
    ".sgr .m{font-size:12px;color:#6b7280;margin-top:3px}"
    ".bsm{border:0;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:700;color:#fff;cursor:pointer}"
    ".bsm.ok{background:#15803d}.bsm.no{background:#b91c1c}.bsm:hover{opacity:.92}"
    "@media(max-width:560px){.wrap{padding:28px 14px 48px}.card{padding:18px}}"
)

_TINT = {"#15803d": "#dcfce7", "#b91c1c": "#fee2e2", "#b45309": "#fef3c7", "#9aa3af": "#f1f3f7"}


def _status_rows() -> str:
    state = _load_state()
    rows = ""
    for key, task in TASKS.items():
        info = state.get(key, {})
        status = info.get("status", "—")
        # Réconcilie l'état « running » avec la réalité du process.
        # On considère le process terminé si le PID est mort OU si le fichier .rc
        # existe (signal fiable : évite le faux-positif quand le PID est réutilisé).
        rc_file = STATE_DIR / f"admin_{key}.rc"
        if status == "running" and (not _pid_alive(info.get("pid", -1)) or rc_file.exists()):
            try:
                rc = rc_file.read_text().strip()
                status = "succès" if rc == "0" else f"échec (code {rc})"
            except OSError:
                status = "terminé"
            info["status"] = status
            state[key] = info
            _save_state(state)
        started = info.get("started", "")
        when = ""
        if started:
            try:
                when = datetime.fromisoformat(started).strftime("%d/%m %H:%M UTC")
            except ValueError:
                when = started
        color = {"running": "#b45309", "succès": "#15803d"}.get(status, "#6b7280")
        if status.startswith("échec"):
            color = "#b91c1c"
        rows += (
            f'<tr><td style="font-weight:600;">{task["label"]}</td>'
            f'<td style="color:{color};font-weight:800;">{status}</td>'
            f'<td style="color:#9aa3af;">{when}</td></tr>'
        )
    return rows


def _log_state(*names: str) -> tuple[str, str, str]:
    """(quand, couleur, statut) d'une étape, d'après le plus récent de ses journaux."""
    best = None
    for n in names:
        p = STATE_DIR / n
        if p.exists():
            m = p.stat().st_mtime
            if best is None or m > best[1]:
                best = (p, m)
    if best is None:
        return ("jamais", "#9aa3af", "—")
    p, m = best
    when = datetime.fromtimestamp(m, timezone.utc).strftime("%d/%m %H:%M")
    try:
        tail = p.read_text(encoding="utf-8", errors="replace")[-3000:].lower()
    except OSError:
        tail = ""
    if "traceback (most recent call last)" in tail:
        return (when, "#b91c1c", "erreur")
    return (when, "#15803d", "ok")


# Étapes du pipeline (clé, libellé, icône, journaux candidats).
_PIPELINE = [
    ("gmail", "Collecte Gmail", "📥", ["cron_gmail.log", "admin_newsletter.log"]),
    ("rss", "Collecte RSS", "🗞", ["cron_rss.log"]),
    ("scrape", "Scraping HTML", "🌐", ["cron_scrape.log"]),
    ("triage", "Tri IA", "🧠", ["cron_triage.log", "admin_veille_ia.log"]),
    ("dashboard", "Page veille", "📊", ["cron_dashboard.log", "admin_veille.log", "admin_veille_ia.log"]),
]


def _node(label: str, icon: str, color: str, status: str, when: str) -> str:
    tint = _TINT.get(color, "#f1f3f7")
    return (
        f'<div class="node"><div class="ic">{icon}</div><div class="nm">{label}</div>'
        f'<div class="st" style="color:{color};background:{tint};">{status}</div>'
        f'<div class="wh">{when}</div></div>'
    )


def _arrow() -> str:
    return '<span class="arrow">→</span>'


def _chip(label: str, icon: str) -> str:
    """Pastille « sortie » (Site public, Brevo, Drive) — sans état, juste une cible."""
    return f'<span class="chip">{icon}&nbsp;{label}</span>'


# Tableau « Comment ça marche » affiché (replié) dans l'admin.
_ARCHI_STEPS = [
    ("1", "Collecte Gmail", "Lundi 7h", "—", "Articles des newsletters (titre + lien)"),
    ("2", "Collecte RSS", "Quotidien 8h", "—", "Presse régionale + sources officielles"),
    ("3", "Scraping HTML", "Quotidien 8h15", "—", "Sites sans flux RSS"),
    ("4", "Tri IA", "Quotidien 8h30", "Haiku 4.5", "Garde/jette + réécrit les titres (caché)"),
    ("5", "Page veille", "Mar/Jeu/Sam 9h", "—", "Publie la page publique"),
    ("6", "Newsletter", "Vendredi 15h", "Opus + Sonnet + Haiku", "Rédige, photos, Brevo, Drive"),
]
_ARCHI_LLM = [
    ("Rédaction (une, brèves)", "claude-opus-4-8", "1×/sem."),
    ("Tri pertinence + titres", "claude-haiku-4-5", "~400/sem. · caché"),
    ("Lien officiel + photo", "claude-sonnet-4-6", "par brève"),
    ("Validation photo (vision)", "claude-haiku-4-5", "par photo · caché"),
]


def _archi_html() -> str:
    steps = "".join(
        f'<tr><td><b>{n}</b></td><td>{lbl}</td><td>{cron}</td><td>{llm}</td><td>{role}</td></tr>'
        for n, lbl, cron, llm, role in _ARCHI_STEPS
    )
    llms = "".join(
        f'<tr><td>{role}</td><td><code>{model}</code></td><td>{freq}</td></tr>'
        for role, model, freq in _ARCHI_LLM
    )
    return (
        '<details><summary class="sec">📖 Comment ça marche</summary>'
        '<div style="font-size:13px;color:#374151;line-height:1.65;margin:12px 0;">'
        'Collecte multi-sources → <b>tri par IA</b> (pertinence + titres propres) → deux sorties : '
        'la <b>page publique</b> (veille exhaustive) et la <b>newsletter</b> (sélection rédigée, '
        'brouillon Brevo + archive Drive). Le VPS exécute le cron et héberge cette page ; '
        'l\'envoi de la newsletter reste <b>manuel</b>.</div>'
        '<div class="sec" style="margin:14px 0 8px;">Étapes</div>'
        f'<table class="t"><tr><th>#</th><th>Étape</th><th>Quand</th><th>LLM</th><th>Rôle</th></tr>{steps}</table>'
        '<div class="sec" style="margin:18px 0 8px;">Les 4 LLM</div>'
        f'<table class="t"><tr><th>Rôle</th><th>Modèle</th><th>Fréquence</th></tr>{llms}</table>'
        '<div style="font-size:12px;color:#9aa3af;margin-top:12px;">Détail complet : '
        '<code>docs/ARCHITECTURE.md</code> dans le dépôt.</div></details>'
    )


def _pipeline_html() -> str:
    busy = _running_task()
    running = {"veille": {"triage", "dashboard"},
               "newsletter": {"triage", "newsletter"}}.get(busy, set())

    def state(key, logs):
        if key in running:
            return ("#b45309", "en cours", "…")
        when, color, st = _log_state(*logs)
        return (color, st, when)

    cells = []
    for key, label, icon, logs in _PIPELINE:
        color, st, when = state(key, logs)
        cells.append(_node(label, icon, color, st, when))
    # Sortie de la chaîne principale : la page publique.
    chain = _arrow().join(cells) + _arrow() + _chip("Site public", "🌍")

    # Branche newsletter (part du tri → brouillon Brevo + archive Drive).
    ncolor, nst, nwhen = state("newsletter", ["admin_newsletter.log"])
    branch = (
        '<div class="flow" style="margin-top:10px;padding-left:356px;">'
        '<span class="arrow">↳</span>'
        + _node("Newsletter", "✉", ncolor, nst, nwhen)
        + _arrow() + _chip("Brevo (brouillon)", "📧") + _chip("Drive (GDoc)", "📁") + "</div>"
    )
    return (
        '<div class="sec">Pipeline</div>'
        f'<div class="flow">{chain}</div>'
        f'{branch}'
        '<div class="legend">Collecte (Gmail · RSS · scraping) → tri IA → page publique. '
        'La newsletter dérive du même flux : brouillon Brevo + archive Drive. '
        '« en cours » = traitement actif. Détails ci-dessous.</div>'
    )


SUGG_FILE = STATE_DIR / "suggestions.json"


def _load_suggestions() -> list:
    try:
        return json.loads(SUGG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_suggestions(items: list) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SUGG_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def _clean_field(value: str, limit: int = 200) -> str:
    """Nettoie un champ proposé : retire ce qui casserait le format config (; \\n)."""
    value = value or ""
    for ch in (";", "\r", "\n", "\t"):
        value = value.replace(ch, " ")
    return value.strip()[:limit]


def _append_source(item: dict) -> None:
    """Approbation → ajoute la source au scraping (config/sources_a_scraper.txt)."""
    nom = item.get("nom") or (urlparse(item["url"]).netloc.replace("www.", "") or "Source proposée")
    terr = item.get("territoire") or "Indetermine"
    line = f'{_clean_field(nom, 80)};{item["url"]};{_clean_field(terr, 20)};html\n'
    with open(ROOT / "config" / "sources_a_scraper.txt", "a", encoding="utf-8") as fh:
        fh.write(line)


def _suggestions_html() -> str:
    pending = [it for it in _load_suggestions() if it.get("status") == "pending"]
    head = '<div class="sec">Sources proposées</div>'
    if not pending:
        return head + '<div class="note" style="margin:0;">Aucune proposition en attente.</div>'
    rows = ""
    for it in pending:
        meta = " · ".join(x for x in [it.get("nom", ""), it.get("territoire", ""), it.get("note", "")] if x)
        rows += (
            '<div class="sgr">'
            f'<div class="u">{_escape(it.get("url", ""))}</div>'
            + (f'<div class="m">{_escape(meta)}</div>' if meta else "")
            + '<div style="margin-top:10px;">'
            f'<form method="post" action="{url_for("suggest_action", sid=it["id"], action="approve")}" style="display:inline;margin-right:8px;">'
            '<button class="bsm ok" type="submit">✓ Valider</button></form>'
            f'<form method="post" action="{url_for("suggest_action", sid=it["id"], action="reject")}" style="display:inline;">'
            '<button class="bsm no" type="submit">✕ Rejeter</button></form>'
            '</div></div>'
        )
    return head + rows


_THANKS = ("<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
           "<title>Merci</title></head><body style=\"margin:0;background:#eef2f8;"
           "font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#16202c;\">"
           "<div style=\"max-width:520px;margin:0 auto;padding:80px 22px;text-align:center;\">"
           "<div style=\"font-size:30px;font-weight:800;color:#2f4a78;\">Business Sabaudo<span style=\"color:#df664f;\">.</span></div>"
           "<div style=\"font-size:17px;margin:20px 0;line-height:1.6;\">{msg}</div>"
           "{back}</div></body></html>")


def _thanks(msg: str) -> str:
    dash = os.getenv("DASHBOARD_URL", "")
    back = (f'<a href="{dash}" style="color:#df664f;font-weight:700;text-decoration:none;">← Retour à la veille</a>'
            if dash else "")
    return _THANKS.format(msg=_escape(msg), back=back)


PAGE = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Business Sabaudo — Admin</title><style>{css}</style></head>
<body><div class="wrap">
  <div class="eyebrow">Espace privé</div>
  <div class="h1">Business Sabaudo<b>.</b> Admin</div>
  {flash}
  <div class="card">{pipeline}</div>
  <div class="card">{archi}</div>
  <div class="card">{buttons}</div>
  <div class="card">{suggest}</div>
  <div class="card">
    <div class="sec">État des traitements</div>
    <table class="t">{rows}</table>
    <div class="note" style="margin:12px 0 0;">Recharge la page pour rafraîchir l'état. Journaux : <code>logs/admin_*.log</code>.</div>
  </div>
</div></body></html>"""


def _buttons() -> str:
    busy = _running_task()
    html = ""
    for key, task in TASKS.items():
        disabled = "disabled" if busy else ""
        cls = "btn alt" if key == "newsletter" else "btn"
        html += (
            f'<form method="post" action="{url_for("run", task_key=key)}" style="margin:0;">'
            f'<button type="submit" class="{cls}" {disabled}>{task["label"]}</button>'
            f'<div class="note">{task["note"]}</div></form>'
        )
    if busy:
        html = ('<div class="busy">Un traitement est en cours — les boutons sont '
                'temporairement désactivés.</div>') + html
    return html


@app.route(BASE + "/")
@require_auth
def home():
    flash = request.args.get("msg", "")
    flash_html = f'<div class="flash">{_escape(flash)}</div>' if flash else ""
    # _status_rows() réconcilie l'état des tâches terminées (running → succès/échec).
    # On l'évalue EN PREMIER pour que le pipeline et les boutons lisent un état à jour
    # (sinon : « en cours » dans le pipeline alors que le tableau affiche « succès »).
    rows = _status_rows()
    pipeline = _pipeline_html()
    buttons = _buttons()
    return PAGE.format(css=_ADMIN_CSS, flash=flash_html, pipeline=pipeline,
                       archi=_archi_html(), buttons=buttons, suggest=_suggestions_html(), rows=rows)


@app.route(BASE + "/run/<task_key>", methods=["POST"])
@require_auth
def run(task_key: str):
    if task_key not in TASKS:
        return redirect(url_for("home", msg="Tâche inconnue."))
    _ok, message = _launch(task_key)
    return redirect(url_for("home", msg=message))


@app.route(BASE + "/suggest", methods=["POST"])
def suggest():
    """PUBLIC (sans auth) : reçoit une proposition de source depuis la page veille."""
    url = _clean_field(request.form.get("url", ""), 300)
    if not url.lower().startswith("http"):
        return _thanks("Lien invalide : il doit commencer par http(s)://."), 400
    items = _load_suggestions()
    pending = sum(1 for it in items if it.get("status") == "pending")
    if pending >= 300:  # garde-fou anti-spam
        return _thanks("Merci ! Trop de propositions en attente pour le moment.")
    if any(it.get("url") == url and it.get("status") == "pending" for it in items):
        return _thanks("Cette source a déjà été proposée — merci !")
    items.append({
        "id": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "url": url,
        "nom": _clean_field(request.form.get("nom", ""), 80),
        "territoire": _clean_field(request.form.get("territoire", ""), 20),
        "note": _clean_field(request.form.get("note", ""), 300),
        "status": "pending",
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    _save_suggestions(items)
    log.info("Source proposée : %s", url)
    return _thanks("Merci ! Votre proposition a été transmise à la rédaction.")


@app.route(BASE + "/suggest/<sid>/<action>", methods=["POST"])
@require_auth
def suggest_action(sid: str, action: str):
    items = _load_suggestions()
    message = "Proposition introuvable."
    for it in items:
        if it.get("id") == sid and it.get("status") == "pending":
            if action == "approve":
                try:
                    _append_source(it)
                    it["status"] = "approuvée"
                    message = f"Source ajoutée au scraping : {it['url']}"
                except OSError as exc:
                    message = f"Ajout impossible : {exc}"
            else:
                it["status"] = "rejetée"
                message = "Proposition rejetée."
            break
    _save_suggestions(items)
    return redirect(url_for("home", msg=message))


@app.route(BASE + "/healthz")
def healthz():
    return "ok", 200


def _escape(text: str) -> str:
    from html import escape

    return escape(text)


def main() -> int:
    if not _credentials():
        log.error("ADMIN_USER / ADMIN_PASS absents du .env — démarrage refusé "
                  "(pas de mot de passe par défaut, par sécurité).")
        return 2
    host = os.getenv("ADMIN_HOST", "127.0.0.1")
    port = int(os.getenv("ADMIN_PORT", "8099"))
    log.info("Page admin sur http://%s:%s (auth Basic).", host, port)
    app.run(host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
