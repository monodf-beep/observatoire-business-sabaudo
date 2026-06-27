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
        "argv": [PY, "scripts/synthesize.py", "--upload", "--brevo", "--force"],
        "note": "Force la création d'un brouillon Brevo (même semaine creuse). "
                "Consomme du crédit API — aucun envoi automatique.",
    },
    "veille_ia": {
        "label": "Trier la veille par IA, puis rafraîchir",
        "argv": ["bash", "-lc", f"'{PY}' scripts/triage.py && '{PY}' scripts/build_dashboard.py"],
        "note": "Juge chaque sujet (pertinence économique) et nettoie les titres via IA, "
                "PUIS republie la page. Consomme du crédit API (seuls les NOUVEAUX sujets "
                "sont jugés — le reste est en cache).",
    },
    "veille": {
        "label": "Rafraîchir la page « toute la veille »",
        "argv": [PY, "scripts/build_dashboard.py"],
        "note": "Gratuit (pas d'IA) : republie la page à partir de la veille déjà triée. "
                "À utiliser après « Trier par IA » ou après un changement de configuration.",
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
            f'<tr><td style="padding:8px 14px 8px 0;font-weight:600;">{task["label"]}</td>'
            f'<td style="padding:8px 14px 8px 0;color:{color};font-weight:700;">{status}</td>'
            f'<td style="padding:8px 0;color:#6b7280;">{when}</td></tr>'
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
    return (
        '<div style="display:inline-block;vertical-align:middle;width:106px;text-align:center;'
        f'background:#fff;border:1px solid #e5e7eb;border-top:3px solid {color};border-radius:10px;'
        'padding:10px 6px;white-space:normal;">'
        f'<div style="font-size:20px;line-height:1;">{icon}</div>'
        f'<div style="font-size:12px;font-weight:700;margin:5px 0 3px;color:#16202c;">{label}</div>'
        f'<div style="font-size:10px;font-weight:800;letter-spacing:.3px;text-transform:uppercase;color:{color};">{status}</div>'
        f'<div style="font-size:10px;color:#9aa3af;margin-top:2px;">{when}</div></div>'
    )


def _arrow() -> str:
    return ('<span style="display:inline-block;color:#c3c9d2;font-size:20px;font-weight:700;'
            'vertical-align:middle;padding:0 1px;">→</span>')


def _pipeline_html() -> str:
    busy = _running_task()
    running = {"veille_ia": {"triage", "dashboard"}, "veille": {"dashboard"},
               "newsletter": {"newsletter"}}.get(busy, set())

    def state(key, logs):
        if key in running:
            return ("#b45309", "en cours", "…")
        when, color, st = _log_state(*logs)
        return (color, st, when)

    cells = []
    for key, label, icon, logs in _PIPELINE:
        color, st, when = state(key, logs)
        cells.append(_node(label, icon, color, st, when))
    chain = _arrow().join(cells)

    # Branche newsletter (part du tri / de la collecte → brouillon Brevo).
    ncolor, nst, nwhen = state("newsletter", ["admin_newsletter.log"])
    branch = (
        '<div style="margin:10px 0 0 350px;white-space:nowrap;">'
        '<span style="display:inline-block;color:#c3c9d2;font-size:18px;vertical-align:middle;">↳</span>'
        + _node("Newsletter (Brevo)", "✉", ncolor, nst, nwhen) + "</div>"
    )
    return (
        '<div style="font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#3f5f96;margin-bottom:12px;">Pipeline</div>'
        f'<div style="overflow-x:auto;white-space:nowrap;padding:4px 0 2px;">{chain}</div>'
        f'{branch}'
        '<div style="font-size:11px;color:#9aa3af;margin-top:12px;">Collecte (Gmail · RSS · scraping) → tri IA → page publique. '
        'La newsletter dérive du même flux. État dérivé des journaux ; « en cours » = traitement actif.</div>'
    )


PAGE = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Business Sabaudo — Admin</title></head>
<body style="margin:0;background:#eef1f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#16202c;">
<div style="max-width:720px;margin:0 auto;padding:38px 20px;">
  <div style="font-size:11px;font-weight:800;letter-spacing:1.8px;text-transform:uppercase;color:#df664f;">Espace privé</div>
  <div style="font-size:30px;font-weight:800;color:#3f5f96;margin:4px 0 22px;">Business Sabaudo<span style="color:#df664f;">.</span> Admin</div>
  {flash}
  <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:22px;margin-bottom:20px;">
    {pipeline}
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:22px;margin-bottom:20px;">
    {buttons}
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:22px;">
    <div style="font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:#3f5f96;margin-bottom:10px;">État des traitements</div>
    <table style="width:100%;font-size:14px;border-collapse:collapse;">{rows}</table>
    <div style="font-size:12px;color:#6b7280;margin-top:12px;">Recharge la page pour rafraîchir l'état. Les journaux détaillés sont dans <code>logs/admin_*.log</code>.</div>
  </div>
</div></body></html>"""


def _buttons() -> str:
    busy = _running_task()
    html = ""
    for key, task in TASKS.items():
        disabled = "disabled" if busy else ""
        bg = "#9aa3af" if busy else "#3f5f96"
        html += (
            f'<form method="post" action="{url_for("run", task_key=key)}" style="margin:0 0 14px;">'
            f'<button type="submit" {disabled} style="background:{bg};color:#fff;border:0;'
            f'border-radius:8px;padding:13px 22px;font-size:15px;font-weight:700;cursor:pointer;width:100%;">'
            f'{task["label"]}</button>'
            f'<div style="font-size:12px;color:#6b7280;margin-top:6px;">{task["note"]}</div></form>'
        )
    if busy:
        html = ('<div style="font-size:13px;color:#b45309;font-weight:700;margin-bottom:14px;">'
                'Un traitement est en cours — les boutons sont temporairement désactivés.</div>') + html
    return html


@app.route(BASE + "/")
@require_auth
def home():
    flash = request.args.get("msg", "")
    flash_html = (f'<div style="background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;'
                  f'border-radius:8px;padding:12px 16px;margin-bottom:18px;font-size:14px;">{_escape(flash)}</div>'
                  if flash else "")
    return PAGE.format(flash=flash_html, pipeline=_pipeline_html(),
                       buttons=_buttons(), rows=_status_rows())


@app.route(BASE + "/run/<task_key>", methods=["POST"])
@require_auth
def run(task_key: str):
    if task_key not in TASKS:
        return redirect(url_for("home", msg="Tâche inconnue."))
    _ok, message = _launch(task_key)
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
