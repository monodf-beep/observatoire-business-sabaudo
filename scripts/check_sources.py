#!/usr/bin/env python3
"""Revue de santé du registre des sources (config/sources_registry.csv).

Doctrine § 7.4 : on vérifie régulièrement que chaque source répond encore et que son
point d'accès machine (flux RSS/Atom, API) renvoie bien ce qu'il promet. Pur code,
aucun appel IA : un test HTTP et quelques motifs suffisent (cf. LLM_OU_CODE.md).

Pour chaque ligne :
  - url         → doit aboutir (HTTP 2xx/3xx après redirections) ;
  - acces_url   → si format RSS/Atom : le contenu doit contenir <rss, <feed ou <rdf ;
                  si format API      : la réponse doit être du JSON ou du XML.
Un 403 / 429 est classé « bloqué » (anti-robot), pas « mort » : à vérifier à la main.
Un délai dépassé / erreur réseau est classé « injoignable » (retenté une fois) : souvent
passager ou propre au réseau d'où l'on teste. Seul un vrai refus HTTP (404, 410…) = « mort ».

Sortie : rapport lisible + logs/sources_health.json (lu par l'admin plus tard).
Code retour 0 si aucune source morte, 1 sinon.

Usage :
    python scripts/check_sources.py              # tout le registre
    python scripts/check_sources.py --only-actifs
    python scripts/check_sources.py --registry chemin.csv --workers 12
"""
from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "config" / "sources_registry.csv"
HEALTH_FILE = ROOT / "logs" / "sources_health.json"
_UA = "Mozilla/5.0 (compatible; ObservatoireBusinessSabaudo/1.0; +https://culturasabauda.eu)"
_TIMEOUT = 20
_READ = 60_000  # octets lus : assez pour reconnaître un flux ou du JSON

_FEED_MARKERS = (b"<rss", b"<feed", b"<rdf:rdf", b"<rdf")


def load_registry(path: Path = REGISTRY) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [row for row in csv.DictReader(fh) if (row.get("id") or "").strip()]


def _fetch(url: str) -> tuple[str, int, bytes, str]:
    """Renvoie (statut, code HTTP, début du contenu, content-type).
    statut ∈ {ok, bloque, mort, injoignable}."""
    for attempt in (1, 2):
        res = _fetch_once(url)
        if res[0] != "injoignable":
            break
    return res


def _fetch_once(url: str) -> tuple[str, int, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ssl.create_default_context()) as r:
            return "ok", r.status, r.read(_READ), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 405:  # « méthode non permise » : l'adresse existe (ex. API TED, en POST)
            return "ok", 405, b"{}", "application/json"
        status = "bloque" if exc.code in (401, 403, 429, 503) else "mort"
        return status, exc.code, b"", ""
    except Exception as exc:  # DNS, TLS, délai…
        return "injoignable", 0, str(exc).encode()[:200], ""


def _looks_feed(body: bytes) -> bool:
    head = body[:4000].lower()
    return any(m in head for m in _FEED_MARKERS)


def _looks_api(body: bytes, ctype: str) -> bool:
    ctype = ctype.lower()
    if "json" in ctype or "xml" in ctype:
        return True
    head = body.lstrip()[:1]
    return head in (b"{", b"[", b"<")


def check_row(row: dict) -> dict:
    url = (row.get("url") or "").strip()
    acces = (row.get("acces_url") or "").strip()
    fmt = (row.get("format") or "").strip()
    res = {"id": row.get("id"), "nom": row.get("nom"), "format": fmt}

    st, code, _, _ = _fetch(url) if url else ("mort", 0, b"", "")
    res["url_statut"], res["url_code"] = st, code

    res["acces_statut"] = ""
    if acces and acces != url and fmt in ("RSS/Atom", "API", "Open data (fichiers)"):
        ast, acode, body, ctype = _fetch(acces)
        if ast == "ok" and fmt == "RSS/Atom" and not _looks_feed(body):
            ast = "invalide"  # répond, mais ce n'est pas un flux
        elif ast == "ok" and fmt == "API" and not _looks_api(body, ctype):
            ast = "invalide"
        res["acces_statut"], res["acces_code"] = ast, acode

    # Verdict global : la source est utilisable si son point d'accès (ou, à défaut,
    # sa page) répond correctement.
    key = res["acces_statut"] or res["url_statut"]
    res["verdict"] = {"ok": "ok", "bloque": "bloque", "invalide": "a_corriger",
                      "injoignable": "injoignable"}.get(key, "mort")
    if res["acces_statut"] in ("mort", "invalide") and res["url_statut"] == "ok":
        res["verdict"] = "a_corriger"  # le site vit, le flux/l'API a bougé
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--only-actifs", action="store_true", help="ne contrôle que statut=actif")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--no-write", action="store_true", help="n'écrit pas logs/sources_health.json")
    args = ap.parse_args()

    rows = load_registry(args.registry)
    if args.only_actifs:
        rows = [r for r in rows if (r.get("statut") or "").strip() == "actif"]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(check_row, rows))

    by = {}
    for r in results:
        by.setdefault(r["verdict"], []).append(r)
    print(f"Registre : {len(results)} sources contrôlées")
    for verdict, label in (("ok", "✅ OK"), ("bloque", "🛡  Bloqué (anti-robot, à vérifier à la main)"),
                           ("injoignable", "⏳ Injoignable (délai / réseau, à retester)"),
                           ("a_corriger", "🔧 À corriger (site vivant, accès cassé)"), ("mort", "❌ Mort")):
        items = by.get(verdict, [])
        print(f"\n{label} : {len(items)}")
        if verdict != "ok":
            for r in items:
                extra = f" accès={r.get('acces_statut')}({r.get('acces_code', '')})" if r.get("acces_statut") else ""
                print(f"  - [{r['id']}] {r['nom']} — page={r['url_statut']}({r['url_code']}){extra}")

    if not args.no_write:
        HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_FILE.write_text(json.dumps({
            "checked": datetime.now(timezone.utc).isoformat(),
            "counts": {k: len(v) for k, v in by.items()},
            "results": results,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if by.get("mort") else 0


if __name__ == "__main__":
    sys.exit(main())
