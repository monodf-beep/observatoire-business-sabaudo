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
    import socket
    transport = None
    try:
        sock = socket.create_connection((host, port or 22), timeout=30)
        transport = paramiko.Transport(sock)
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


def load_latest_week_items(apply_triage: bool = True) -> tuple[str, dict]:
    """Lit TOUTE la veille brute (01_Veille_brute), garde la semaine ISO la plus
    récente, et renvoie (libellé semaine, {territoire: [items]}). Items dédupliqués
    par URL/titre. C'est la matière de la page lecteur « toute la veille ».

    apply_triage : applique les verdicts du tri LLM (logs/triage_cache.json) — jette
    les éléments jugés hors-sujet et nettoie les titres. Fail-open (pas de verdict →
    on garde). Mettre False pour récupérer TOUS les items (utilisé par scripts/triage.py)."""
    from collections import defaultdict
    from urllib.parse import urlparse

    from utils.triage import item_key, load_cache

    triage_cache = load_cache() if apply_triage else {}

    from utils.sources import (
        domain_of,
        is_broad_source,
        is_newsletter_junk,
        is_offtopic,
        is_press,
        is_welcome_subject,
        load_broad_sources,
        load_perimeter_filter,
        load_press_domains,
        load_topic_filter,
        mentions_perimeter,
        strip_tracking,
    )

    import re
    import unicodedata

    def _norm_title(t: str) -> str:
        """Signature de titre (sans accents/ponctuation) pour dédupliquer inter-canaux."""
        t = unicodedata.normalize("NFD", t or "")
        t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
        t = re.sub(r"[^a-z0-9 ]", " ", t)
        return re.sub(r"\s+", " ", t).strip()[:80]

    press = load_press_domains()
    off_re, eco_re = load_topic_filter()
    perim_re = load_perimeter_filter()
    broad = load_broad_sources()
    weeks: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    # Domaines expéditeurs des newsletters reçues, par semaine (« reçue cette semaine »).
    news_by_week: dict[str, set] = defaultdict(set)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    if not INPUT_DIR.exists():
        return "", {}, set()
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
        is_gmail = rec.get("source") == "gmail"
        # « articles » (titre apparié au heading précédent) prime sur « links » brut.
        gmail_links = (rec.get("articles") or rec.get("links")) if is_gmail else None
        emitted: list[dict] = []
        if is_gmail:
            sender = _sender_label(rec.get("from", "")) or rec.get("title", "")
            subject = rec.get("title", "")
            # Emails de bienvenue / confirmation d'abonnement : aucun contenu éco → ignorés.
            if is_welcome_subject(subject):
                continue
            # Domaine expéditeur → marque la newsletter comme « reçue cette semaine ».
            m_dom = re.search(r"@([\w.-]+)", rec.get("from", ""))
            sender_dom = m_dom.group(1).lower() if m_dom else ""
            if sender_dom:
                news_by_week[wk].add(sender_dom)
            # Source LARGE (ex. EU-Startups) : on ne garde que les sujets du périmètre.
            broad_src = is_broad_source(sender_dom, broad)
            NL_CAP = 8  # au-delà, on déborde de déchets : on plafonne par newsletter.
            for ln in (gmail_links or []):
                if len(emitted) >= NL_CAP:
                    break
                u = (ln.get("url") or "").strip()
                if not u:
                    continue
                text = (ln.get("text") or "").strip()
                # Filtre anti-déchets : boutons, réseaux sociaux, fragments, « >> Je découvre ».
                if not text or is_newsletter_junk(text):
                    continue
                # Pertinence : on écarte le hors-sujet (sport, faits divers, météo…).
                if is_offtopic(text, off_re, eco_re):
                    continue
                # Source large : exiger une mention du périmètre (sinon hors-territoire).
                if broad_src and not mentions_perimeter(text, perim_re):
                    continue
                host = urlparse(u).netloc.lower()
                if host.startswith("www."):
                    host = host[4:]
                link_press = is_press(host, press)
                emitted.append({
                    "title": text[:200],
                    "url": "" if link_press else strip_tracking(u),
                    "source": sender,
                    "date": date,
                    "press": link_press,
                    "via": sender,
                    "newsletter": True,
                })
            # Pas de repli sur l'OBJET de l'email : « 🚨 Les actus à ne pas manquer »
            # n'apporte rien. Si on n'a pas su extraire d'article (titres en images,
            # structure illisible), la newsletter ne contribue rien à la liste — elle
            # reste tout de même marquée « reçue » dans le tableau des abonnements.
        else:
            # Presse = radar : on garde le sujet (voir si on est passé à côté) mais
            # on n'expose PAS le lien vers le journal. L'officiel reste cliquable.
            from_press = is_press(domain_of(rec), press)
            title = rec.get("title", "(sans titre)")
            # Élague le bruit du radar (sport, faits divers, météo…) : un titre de
            # presse hors-sujet sans angle éco est ignoré. L'officiel passe toujours.
            if from_press and is_offtopic(title, off_re, eco_re):
                continue
            emitted.append({
                "title": title,
                "url": "" if from_press else strip_tracking(rec.get("link", "")),
                "source": rec.get("feed_title") or rec.get("from", "") or "",
                "date": date,
                "press": from_press,
            })

        for item in emitted:
            # Tri LLM : verdict en cache (fail-open). Jette le hors-sujet, nettoie le titre.
            verdict = triage_cache.get(item_key(item.get("url", ""), item.get("title", "")))
            if verdict is not None:
                if not verdict.get("keep", True):
                    continue
                if verdict.get("title"):
                    item["title"] = verdict["title"]
            url_key = (item.get("url") or "").strip().lower().split("#")[0].rstrip("/")
            title_key = _norm_title(item.get("title", ""))
            if not (url_key or title_key):
                continue
            # Dédup INTER-CANAUX : même URL OU même titre (RSS + newsletter + scrape
            # peuvent pointer le même sujet sous des URL différentes).
            if (url_key and url_key in seen_urls) or (title_key and title_key in seen_titles):
                continue
            if url_key:
                seen_urls.add(url_key)
            if title_key:
                seen_titles.add(title_key)
            weeks[wk][terr].append(item)
    if not weeks:
        return "", {}, set()
    latest = sorted(weeks)[-1]
    return latest, weeks[latest], news_by_week[latest]


def build(upload: bool = False) -> int:
    """Génère la page « toute la veille » (et la dépose si upload). Réutilisable
    depuis synthesize.py (mise à jour à chaque run)."""
    week_id, by_territory, news_hits = load_latest_week_items()
    if not by_territory:
        log.warning("Aucune donnée de veille (%s). Page non générée.", INPUT_DIR)
        return 0

    from utils.sources import load_newsletters
    newsletters = load_newsletters()
    # « reçue cette semaine » si un domaine reçu correspond au domaine du registre.
    for nl in newsletters:
        dom = nl["domaine"]
        nl["recue"] = any(dom in h or h in dom for h in news_hits)

    # Encart « Synthèse de la semaine » : relit la une + signaux que la newsletter a
    # rédigés pour CETTE semaine (aucun appel IA en plus). Absent si pas de synthèse.
    synthese = None
    synth_path = OUTPUT_DIR / f"{week_id}.json"
    if synth_path.exists():
        try:
            synthese = json.loads(synth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            synthese = None

    # Formulaire « proposer une source » → endpoint public de l'admin (si configuré).
    admin_url = os.getenv("ADMIN_PUBLIC_URL", "").rstrip("/")
    suggest_url = f"{admin_url}/suggest" if admin_url else ""

    generated = f"{datetime.now(timezone.utc):%d/%m/%Y}"
    html = render_veille_page(week_id, by_territory, generated_at=generated,
                              newsletters=newsletters, synthese=synthese, suggest_url=suggest_url)
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
