"""Dérive le domaine et le libellé d'une source à partir d'un enregistrement de veille.

Sert à créditer les sources dans la newsletter (favicon + nom) sans rien inventer :
tout vient des champs réellement collectés (lien RSS, en-tête From d'un email…).

Gère aussi les domaines de PRESSE (config/press_domains.txt) : ces sources servent
de radar mais ne sont jamais créditées/liées dans la newsletter (pas de pub aux
journaux concurrents) — l'info est attribuée à l'acteur primaire.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

_PRESS_FILE = Path(__file__).resolve().parent.parent / "config" / "press_domains.txt"


def load_press_domains(path: Path | None = None) -> set[str]:
    """Charge l'ensemble des domaines de presse (radar uniquement)."""
    path = path or _PRESS_FILE
    if not path.exists():
        return set()
    domains: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lower()
        if line and not line.startswith("#"):
            domains.add(line.lstrip("."))
    return domains


def is_press(domain: str, press: set[str]) -> bool:
    """Vrai si le domaine (ou son domaine parent) figure dans la liste de presse."""
    domain = (domain or "").lower()
    return any(domain == p or domain.endswith("." + p) for p in press)


def domain_of(record: dict) -> str:
    """Domaine de la source (sans www), pour le favicon. '' si introuvable."""
    link = record.get("link") or record.get("feed_url") or ""
    if link:
        host = urlparse(link).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host
    match = re.search(r"@([\w.-]+)", record.get("from", ""))
    return match.group(1).lower() if match else ""


def source_label(record: dict) -> str:
    """Nom lisible de la source (titre du flux, nom de l'expéditeur, ou domaine)."""
    if record.get("feed_title"):
        return record["feed_title"]
    sender = record.get("from", "")
    match = re.match(r'\s*"?([^"<]+?)"?\s*<', sender)
    if match:
        return match.group(1).strip()
    return domain_of(record) or "Source"
