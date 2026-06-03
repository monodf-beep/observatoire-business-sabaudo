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
_ACTOR_IMAGES_FILE = Path(__file__).resolve().parent.parent / "config" / "actor_images.txt"


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


def load_actor_images(path: Path | None = None) -> list[tuple[str, str]]:
    """Charge les photos par ACTEUR : [(mot-clé en minuscules, url), …].

    Format du fichier : `mot-clé;url`. Le mot-clé est cherché (insensible à la
    casse) dans le nom de l'acteur ou le titre d'un article : s'il correspond, la
    vraie photo de l'acteur remplace la bannière générique de territoire.
    Ordre conservé → la 1re correspondance gagne (mettre les plus spécifiques d'abord).
    """
    path = path or _ACTOR_IMAGES_FILE
    pairs: list[tuple[str, str]] = []
    if not path.exists():
        return pairs
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ";" not in line:
            continue
        keyword, url = (p.strip() for p in line.split(";", 1))
        if keyword and url:
            pairs.append((keyword.lower(), url))
    return pairs


def pick_actor_image(item: dict, actor_images: list[tuple[str, str]]) -> str:
    """Photo d'acteur si un mot-clé enregistré apparaît dans 'source' ou 'title'."""
    haystack = f"{item.get('source', '')} {item.get('title', '')}".lower()
    for keyword, url in actor_images:
        if keyword in haystack:
            return url
    return ""


def pick_image(territory: str, key: str, images: dict[str, list[str]]) -> str:
    """Choisit une image de substitution (déterministe par 'key', pour varier)."""
    import hashlib

    pool = images.get(territory) or images.get("default") or []
    if not pool:
        return ""
    idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(pool)
    return pool[idx]


def apply_fallback_images(data: dict, images: dict[str, list[str]] | None = None,
                          actor_images: list[tuple[str, str]] | None = None) -> dict:
    """Pose les images de substitution sur le héros et les cartes d'une newsletter.

    Priorité : image native > PHOTO D'ACTEUR enregistrée (config/actor_images.txt) >
    bannière de TERRITOIRE générique (config/territory_images.txt).
    Le HÉROS reçoit toujours une image s'il n'en a pas (impact AIDA en ouverture) ;
    une photo d'acteur s'applique aussi aux cartes dès qu'elle correspond. Les
    bannières génériques, elles, ne tombent qu'un article sur 3 (rythme sans
    saturation). Idempotent (n'écrase jamais une image native) et appliqué au rendu,
    donc il suit config/*.txt sans relancer la synthèse IA. Modifie et renvoie `data`.
    """
    if images is None:
        images = load_territory_images()
    if actor_images is None:
        actor_images = load_actor_images()
    if not images and not actor_images:
        return data
    hero = data.get("hero")
    if hero and not hero.get("image"):
        hero["image"] = (pick_actor_image(hero, actor_images)
                         or pick_image(hero.get("territory", ""), hero.get("title", ""), images))
    gap = 0
    for it in data.get("items", []):
        if it.get("image"):
            continue
        actor = pick_actor_image(it, actor_images)
        if actor:
            it["image"] = actor  # une vraie photo d'acteur passe toujours
            continue
        if gap == 0:
            it["image"] = pick_image(it.get("territory", ""), it.get("title", ""), images)
        gap = (gap + 1) % 3
    return data


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
