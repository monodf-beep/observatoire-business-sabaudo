#!/usr/bin/env python3
"""Génère le tableau de bord visuel « Business Sabaudo » (page HTML autonome).

Agrège les données des synthèses hebdomadaires (02_Veille_traitee/
Syntheses_hebdomadaires/*.json) et produit une page HTML unique récapitulative.

Usage :
    python scripts/build_dashboard.py            # écrit dashboard.html en local
    python scripts/build_dashboard.py --upload   # + dépôt du fichier sur le Drive
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.dashboard import render_dashboard  # noqa: E402
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"

log = get_logger("build_dashboard")


def publish_ftp(local_path: Path) -> bool:
    """Publie le dashboard sur l'hébergement web (FTP) → page publique.

    Piloté par .env : DASHBOARD_FTP_HOST / _USER / _PASS / _DIR (défaut
    /public_html/observatoire) / _TLS (1 pour FTP over TLS). Déposé sous le nom
    index.html. Sans config FTP : on ne fait rien (silencieux). Tolérant aux pannes.
    """
    host = os.getenv("DASHBOARD_FTP_HOST", "").strip()
    user = os.getenv("DASHBOARD_FTP_USER", "").strip()
    password = os.getenv("DASHBOARD_FTP_PASS", "")
    if not (host and user and password):
        return False
    target_dir = os.getenv("DASHBOARD_FTP_DIR", "/public_html/observatoire").strip()
    use_tls = os.getenv("DASHBOARD_FTP_TLS", "").strip() in {"1", "true", "True", "yes"}

    import ftplib

    try:
        ftp = ftplib.FTP_TLS(timeout=30) if use_tls else ftplib.FTP(timeout=30)
        ftp.connect(host, 21)
        ftp.login(user, password)
        if use_tls:
            ftp.prot_p()
        # Crée l'arborescence cible si besoin, puis s'y place.
        for part in target_dir.strip("/").split("/"):
            if not part:
                continue
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                ftp.mkd(part)
                ftp.cwd(part)
        with open(local_path, "rb") as fh:
            ftp.storbinary("STOR index.html", fh)
        ftp.quit()
        log.info("Tableau de bord publié par FTP : %s → %s/index.html", host, target_dir)
        return True
    except Exception as exc:  # réseau, auth, perms… → on n'échoue jamais le run
        log.warning("Publication FTP du dashboard impossible : %s", exc)
        return False


def load_weeks() -> list[tuple[str, dict]]:
    """Charge les données de chaque semaine : [(week_id, data), ...]."""
    weeks: list[tuple[str, dict]] = []
    if not OUTPUT_DIR.exists():
        return weeks
    for jf in sorted(OUTPUT_DIR.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Synthèse illisible ignorée (%s) : %s", jf.name, exc)
            continue
        weeks.append((jf.stem, data))
    return weeks


def build(upload: bool = False) -> int:
    """Génère le tableau de bord (et le dépose sur le Drive si upload). Réutilisable
    depuis synthesize.py (mise à jour à chaque run)."""
    weeks = load_weeks()
    if not weeks:
        log.warning("Aucune donnée de synthèse (%s). Tableau de bord non généré.", OUTPUT_DIR)
        return 0

    generated = f"{datetime.now(timezone.utc):%d/%m/%Y}"
    html = render_dashboard(weeks, generated_at=generated)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    log.info("Tableau de bord écrit : %s (%d semaine(s)).", DASHBOARD_PATH, len(weeks))

    # Publication publique (FTP vers l'hébergement web) — page culturasabauda.eu.
    publish_ftp(DASHBOARD_PATH)

    if upload:
        from utils.drive_upload import upload_file

        subfolder = os.getenv("DRIVE_VEILLE_TRAITEE_SUBFOLDER", "02_Veille_traitee")
        file_id = upload_file(DASHBOARD_PATH, subfolder=subfolder)
        if file_id:
            log.info("Tableau de bord déposé sur le Drive (id=%s).", file_id)
        else:
            log.warning("Dépôt Drive échoué — le fichier local reste disponible.")

    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Tableau de bord Business Sabaudo.")
    parser.add_argument("--upload", action="store_true", help="Déposer la page sur le Drive.")
    args = parser.parse_args()
    return build(upload=args.upload)


if __name__ == "__main__":
    raise SystemExit(main())
