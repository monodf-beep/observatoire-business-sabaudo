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
_PARTNER_FILE = Path(__file__).resolve().parent.parent / "config" / "partner_media.txt"


def _load_domain_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    domains: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lower()
        if line and not line.startswith("#"):
            domains.add(line.lstrip("."))
    return domains


def load_press_domains(path: Path | None = None) -> set[str]:
    """Charge l'ensemble des domaines de presse (radar uniquement)."""
    return _load_domain_file(path or _PRESS_FILE)


def load_partner_media(path: Path | None = None) -> set[str]:
    """Charge les médias partenaires (crédités et liés malgré leur nature éditoriale)."""
    return _load_domain_file(path or _PARTNER_FILE)


def _domain_matches(domain: str, domains: set[str]) -> bool:
    domain = (domain or "").lower()
    return any(domain == d or domain.endswith("." + d) for d in domains)


def is_press(domain: str, press: set[str]) -> bool:
    """Vrai si le domaine figure dans la liste de presse."""
    return _domain_matches(domain, press)


def is_partner(domain: str, partners: set[str]) -> bool:
    """Vrai si le domaine est un média partenaire crédité/lié (prioritaire sur is_press)."""
    return _domain_matches(domain, partners)


_IMAGES_FILE = Path(__file__).resolve().parent.parent / "config" / "territory_images.txt"


def load_territory_images(path: Path | None = None) -> dict[str, list[str]]:
    """Charge les images de substitution par territoire : {territoire: [url, ...]}."""
    path = path or _IMAGES_FILE
    images: dict[str, list[str]] = {}
    if not path.exists():
        return images
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ";" not in line:
            continue
        territory, url = (p.strip() for p in line.split(";", 1))
        if territory and url:
            images.setdefault(territory, []).append(url)
    return images


def pick_image(territory: str, key: str, images: dict[str, list[str]]) -> str:
    """Choisit une image de substitution (déterministe par 'key', pour varier)."""
    import hashlib

    pool = images.get(territory) or images.get("default") or []
    if not pool:
        return ""
    idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[idx]


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
