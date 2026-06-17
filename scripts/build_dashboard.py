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
from utils.dashboard import render_veille_page  # noqa: E402
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "01_Veille_brute"
OUTPUT_DIR = ROOT / "02_Veille_traitee" / "Syntheses_hebdomadaires"
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"

log = get_logger("build_dashboard")


def _publish_sftp(host, port, user, password, target_dir, local_path) -> bool:
    """Dépôt SFTP (ex. Gandi Simple Hosting). Nécessite paramiko."""
    try:
        import paramiko
    except ImportError:
        log.warning("paramiko absent — SFTP impossible (pip install paramiko).")
        return False
    transport = None
    try:
        transport = paramiko.Transport((host, port or 22))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        # Crée l'arborescence cible si besoin (chemin absolu), puis dépose index.html.
        path = ""
        for part in target_dir.strip("/").split("/"):
            if not part:
                continue
            path += "/" + part
            try:
                sftp.stat(path)
            except IOError:
                sftp.mkdir(path)
        sftp.put(str(local_path), target_dir.rstrip("/") + "/index.html")
        sftp.close()
        log.info("Tableau de bord publié (SFTP) : %s → %s/index.html", host, target_dir)
        return True
    except Exception as exc:
        log.warning("Publication SFTP du dashboard impossible : %s", exc)
        return False
    finally:
        if transport is not None:
            transport.close()


def _publish_ftp(host, port, user, password, target_dir, local_path, use_tls) -> bool:
    """Dépôt FTP/FTPS classique."""
    import ftplib

    try:
        ftp = ftplib.FTP_TLS(timeout=30) if use_tls else ftplib.FTP(timeout=30)
        ftp.connect(host, port or 21)
        ftp.login(user, password)
        if use_tls:
            ftp.prot_p()
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
        log.info("Tableau de bord publié (FTP) : %s → %s/index.html", host, target_dir)
        return True
    except Exception as exc:
        log.warning("Publication FTP du dashboard impossible : %s", exc)
        return False


def _publish_local(target_dir: str, local_path: Path) -> bool:
    """Copie locale (VPS) : dépose index.html dans le dossier servi par nginx."""
    import shutil

    try:
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, Path(target_dir) / "index.html")
        log.info("Tableau de bord copié (local) : %s/index.html", target_dir)
        return True
    except Exception as exc:
        log.warning("Copie locale du dashboard impossible : %s", exc)
        return False


def publish_ftp(local_path: Path) -> bool:
    """Publie le dashboard → page publique (index.html).

    DASHBOARD_FTP_PROTO = local (copie dans un dossier servi par nginx — défaut VPS)
    | sftp (Gandi…) | ftp | ftps. Selon le proto : DASHBOARD_FTP_DIR (+ HOST/USER/
    PASS/PORT pour les protos distants). Sans config utile : ne fait rien (silencieux).
    """
    proto = (os.getenv("DASHBOARD_FTP_PROTO", "local").strip().lower() or "local")
    target_dir = os.getenv("DASHBOARD_FTP_DIR", "").strip()

    if proto == "local":
        return _publish_local(target_dir, local_path) if target_dir else False

    host = os.getenv("DASHBOARD_FTP_HOST", "").strip()
    user = os.getenv("DASHBOARD_FTP_USER", "").strip()
    password = os.getenv("DASHBOARD_FTP_PASS", "")
    if not (host and user and password):
        return False
    target_dir = target_dir or "/observatoire"
    port = int(os.getenv("DASHBOARD_FTP_PORT", "0") or 0)

    if proto == "sftp":
        return _publish_sftp(host, port, user, password, target_dir, local_path)
    return _publish_ftp(host, port, user, password, target_dir, local_path,
                        use_tls=(proto == "ftps"))


def _sender_label(frm: str) -> str:
    """Nom lisible d'un expéditeur de newsletter (« I3P » plutôt que l'adresse)."""
    import re

    frm = (frm or "").strip()
    m = re.match(r'\s*"?([^"<]+?)"?\s*<', frm)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m2 = re.search(r"@([\w.-]+)", frm)
    return m2.group(1) if m2 else frm


def load_latest_week_items() -> tuple[str, dict]:
    """Lit TOUTE la veille brute (01_Veille_brute), garde la semaine ISO la plus
    récente, et renvoie (libellé semaine, {territoire: [items]}). Items dédupliqués
    par URL/titre. C'est la matière de la page lecteur « toute la veille »."""
    from collections import defaultdict
    from urllib.parse import urlparse

    from utils.sources import domain_of, is_press, load_press_domains

    press = load_press_domains()
    weeks: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    seen: set[str] = set()
    if not INPUT_DIR.exists():
        return "", {}
    for jf in INPUT_DIR.rglob("*.json"):
        try:
            rec = json.loads(jf.read_text(encoding="utf-8"))
            dt = datetime.fromisoformat(rec.get("date", ""))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        iso = dt.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        parts = jf.parent.name.split("-", 2)
        terr = rec.get("territoire") or (parts[2] if len(parts) == 3 else "Indetermine")
        date = rec.get("date", "")[:10]

        # Newsletters institutionnelles : on ÉCLATE l'email en autant de SOURCES
        # (les liens qu'il cite) au lieu d'un bloc opaque. C'est ce qui fait enfin
        # remonter l'info institutionnelle dans la veille (et pas que la presse RSS).
        gmail_links = rec.get("links") if rec.get("source") == "gmail" else None
        emitted: list[dict] = []
        if gmail_links:
            sender = _sender_label(rec.get("from", "")) or rec.get("title", "")
            subject = rec.get("title", "")
            for ln in gmail_links:
                u = (ln.get("url") or "").strip()
                if not u:
                    continue
                host = urlparse(u).netloc.lower()
                if host.startswith("www."):
                    host = host[4:]
                link_press = is_press(host, press)
                emitted.append({
                    "title": (ln.get("text") or subject or "(sans titre)")[:200],
                    "url": "" if link_press else u,
                    "source": sender,
                    "date": date,
                    "press": link_press,
                    "via": sender,
                })
        else:
            # Presse = radar : on garde le sujet (voir si on est passé à côté) mais
            # on n'expose PAS le lien vers le journal. L'officiel reste cliquable.
            from_press = is_press(domain_of(rec), press)
            emitted.append({
                "title": rec.get("title", "(sans titre)"),
                "url": "" if from_press else rec.get("link", ""),
                "source": rec.get("feed_title") or rec.get("from", "") or "",
                "date": date,
                "press": from_press,
            })

        for item in emitted:
            key = (item.get("url") or item.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            weeks[wk][terr].append(item)
    if not weeks:
        return "", {}
    latest = sorted(weeks)[-1]
    return latest, weeks[latest]


def build(upload: bool = False) -> int:
    """Génère la page « toute la veille » (et la dépose si upload). Réutilisable
    depuis synthesize.py (mise à jour à chaque run)."""
    week_id, by_territory = load_latest_week_items()
    if not by_territory:
        log.warning("Aucune donnée de veille (%s). Page non générée.", INPUT_DIR)
        return 0

    generated = f"{datetime.now(timezone.utc):%d/%m/%Y}"
    html = render_veille_page(week_id, by_territory, generated_at=generated)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    n = sum(len(v) for v in by_territory.values())
    log.info("Page « toute la veille » écrite : %s (%s, %d sujets).", DASHBOARD_PATH, week_id, n)

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
