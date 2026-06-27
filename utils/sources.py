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


_BLOCKED_IMG_FILE = Path(__file__).resolve().parent.parent / "config" / "blocked_image_domains.txt"


def load_blocked_image_domains(path: Path | None = None) -> set[str]:
    """Charge les hôtes d'images PROSCRITS (CDN de presse, agrégateurs)."""
    path = path or _BLOCKED_IMG_FILE
    if not path.exists():
        return set()
    domains: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lower()
        if line and not line.startswith("#"):
            domains.add(line.lstrip("."))
    return domains


def is_blocked_image(url: str, blocked: set[str]) -> bool:
    """Vrai si l'URL d'image provient d'un hôte proscrit (presse/agrégateur).

    Empêche qu'une vignette tierce sans rapport (typiquement une photo de média
    récupérée par un agrégateur) ne s'affiche : on retombe sur la bannière.
    """
    if not url or not blocked:
        return False
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == b or host.endswith("." + b) for b in blocked)


# --------------------------------------------------------------------------- #
# Filtres de QUALITÉ des newsletters (anti-déchets + emails de bienvenue)
# --------------------------------------------------------------------------- #
# Sujets d'emails à IGNORER entièrement : confirmations d'abonnement, bienvenue,
# double opt-in… aucun contenu économique.
_WELCOME_SUBJECT = (
    "bienvenue", "benvenut", "welcome", "confirmez votre", "confirmer votre",
    "confirme votre", "votre inscription", "inscription est valid", "inscription valid",
    "confirm your subscription", "confirm your email", "conferma la tua",
    "conferma l'iscrizione", "grazie per esserti", "grazie per la tua iscrizione",
    "merci de votre inscription", "merci pour votre inscription",
    "merci de vous etre inscrit", "double opt", "opt-in", "veuillez confirmer",
)
# Réseaux sociaux / liens utilitaires (texte d'ancre exact ou inclus).
_NL_JUNK_SUBSTR = (
    "desabonn", "unsubscribe", "telecharg", "plus d'infos", "plus d infos",
    "en savoir plus", "voir en ligne", "voir dans le navigateur", "view online",
    "view in browser", "poll results", "follow us", "suivez ce lien", "suivez-nous",
    "lire la suite", "read more", "leggi tutto", "scopri di", "manage your",
    "gerer vos", "preferences", "privacy", "cookie", "facebook", "linkedin",
    "instagram", "twitter", "youtube", "tiktok", "whatsapp", "telegram",
    "je contacte", "je decouvre", "je participe", "je m'informe", "je m informe",
    "je me connecte", "je m'inscris", "nous contacter", "contactez", "mentions legales",
)
_NL_JUNK_EXACT = {"www", "x", "rss", "email", "e-mail", "contact", "menu", "+", "-"}


def is_welcome_subject(subject: str) -> bool:
    """Vrai si l'objet est un email de bienvenue/confirmation (à ignorer)."""
    s = _strip_accents(subject or "").lower()
    return any(w in s for w in _WELCOME_SUBJECT)


def is_newsletter_junk(text: str) -> bool:
    """Vrai si le texte d'un lien de newsletter est un DÉCHET (bouton, réseau social,
    fragment), pas un titre d'article. Élimine « >> Je découvre », « Facebook », « ai »…"""
    t = _strip_accents(text or "").lower().strip()
    if not t or t in _NL_JUNK_EXACT:
        return True
    if t[0] in ">•·|→#":                  # puces / flèches de bouton
        return True
    if t.startswith("je "):               # CTA français « Je découvre/participe… »
        return True
    if any(s in t for s in _NL_JUNK_SUBSTR):
        return True
    words = t.split()
    # Trop court → fragment de bannière / nom isolé sans contexte économique.
    if len(words) < 3 and len(t) < 18:
        return True
    return False


_NEWSLETTERS_FILE = Path(__file__).resolve().parent.parent / "config" / "newsletters.txt"


def load_newsletters(path: Path | None = None) -> list[dict]:
    """Charge le registre des newsletters suivies : [{nom, domaine, territoire, statut}]."""
    path = path or _NEWSLETTERS_FILE
    if not path.exists():
        return []
    out: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 4:
            continue
        nom, domaine, territoire, statut = parts[0], parts[1], parts[2], parts[3].lower()
        if nom and domaine:
            out.append({"nom": nom, "domaine": domaine.lower(),
                        "territoire": territoire, "statut": statut})
    return out


_OFFTOPIC_FILE = Path(__file__).resolve().parent.parent / "config" / "offtopic_keywords.txt"
_ECONOMIC_FILE = Path(__file__).resolve().parent.parent / "config" / "economic_keywords.txt"


def _load_keywords(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(_strip_accents(line).lower())
    return out


def _compile_keywords(words: list[str]):
    """Compile une alternation \\b(mot1|mot2|…)\\b (accents déjà retirés)."""
    if not words:
        return None
    # Tri par longueur décroissante pour que les expressions multi-mots priment.
    parts = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b")


def load_topic_filter(
    offtopic_path: Path | None = None, economic_path: Path | None = None
) -> tuple[object, object]:
    """Charge (regex hors-sujet, regex économique) pour filtrer le radar presse."""
    off = _compile_keywords(_load_keywords(offtopic_path or _OFFTOPIC_FILE))
    eco = _compile_keywords(_load_keywords(economic_path or _ECONOMIC_FILE))
    return off, eco


def is_offtopic(title: str, offtopic_re, economic_re) -> bool:
    """Vrai si le titre de presse est HORS-SUJET : il matche un mot hors-sujet
    ET ne contient aucun mot économique (filet de sécurité). Sert à élaguer le
    bruit du radar (sport, faits divers, météo…) sans jeter les vraies brèves éco.
    """
    if offtopic_re is None or not title:
        return False
    norm = _strip_accents(title).lower()
    if not offtopic_re.search(norm):
        return False
    if economic_re is not None and economic_re.search(norm):
        return False  # angle économique détecté → on garde
    return True


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


_OFFICIAL_FILE = Path(__file__).resolve().parent.parent / "config" / "official_links.txt"


def _strip_accents(text: str) -> str:
    import unicodedata

    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _normalize_domain(value: str) -> str:
    """Réduit une valeur (domaine ou URL) à un domaine nu, sans www ni chemin."""
    value = value.strip()
    if "//" in value:
        value = urlparse(value).netloc or value
    value = value.split("/", 1)[0].lower()
    if value.startswith("www."):
        value = value[4:]
    return value


def load_official_links(path: Path | None = None) -> dict[str, str]:
    """Charge l'annuaire des sites officiels : {motclé normalisé: domaine officiel}."""
    path = path or _OFFICIAL_FILE
    links: dict[str, str] = {}
    if not path.exists():
        return links
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ";" not in line:
            continue
        key, value = (p.strip() for p in line.split(";", 1))
        domain = _normalize_domain(value)
        if key and domain:
            links[_strip_accents(key).lower()] = domain
    return links


def resolve_official(actor: str, title: str, links: dict[str, str]) -> str:
    """Renvoie le DOMAINE officiel si un motclé curé apparaît dans l'acteur/le titre.

    En cas de correspondances multiples, le motclé le PLUS LONG (le plus précis)
    l'emporte. '' si aucune correspondance — la brève reste alors sans lien.
    """
    if not links:
        return ""
    haystack = _strip_accents(f"{actor} {title}").lower()
    best_key = ""
    for key in links:
        if key in haystack and len(key) > len(best_key):
            best_key = key
    return links.get(best_key, "")


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
