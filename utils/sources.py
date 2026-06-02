"""Dérive le domaine et le libellé d'une source à partir d'un enregistrement de veille.

Sert à créditer les sources dans la newsletter (favicon + nom) sans rien inventer :
tout vient des champs réellement collectés (lien RSS, en-tête From d'un email…).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


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
