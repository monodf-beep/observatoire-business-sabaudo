"""Client minimal pour l'API Brevo (création de campagnes email en BROUILLON).

100 % bibliothèque standard (urllib) — pas de dépendance externe.

⚠ Aucune campagne n'est jamais envoyée : on crée un BROUILLON (pas de
`scheduledAt`). Franck relit dans Brevo puis déclenche l'envoi lui-même.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.brevo.com/v3"


class BrevoError(RuntimeError):
    """Erreur renvoyée par l'API Brevo ou la connexion réseau."""


def _request(method: str, path: str, api_key: str, payload: dict | None = None, timeout: int = 30) -> dict:
    url = f"{API_BASE}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("api-key", api_key)
    req.add_header("accept", "application/json")
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise BrevoError(f"HTTP {exc.code} sur {method} {path} : {detail}") from exc
    except urllib.error.URLError as exc:
        raise BrevoError(f"Connexion à Brevo impossible : {exc.reason}") from exc


def create_draft_campaign(
    *,
    api_key: str,
    name: str,
    subject: str,
    sender_name: str,
    sender_email: str,
    html_content: str,
    list_ids: list[int] | None = None,
    segment_ids: list[int] | None = None,
    timeout: int = 30,
) -> int:
    """Crée une campagne email « classic » en BROUILLON et renvoie son id.

    Destinataires : `segment_ids` (ciblage dynamique par attribut) s'il est fourni,
    sinon `list_ids`. L'absence de `scheduledAt` garantit que la campagne reste un
    BROUILLON : rien n'est envoyé tant que Franck ne le décide pas depuis Brevo.
    """
    if segment_ids:
        recipients: dict = {"segmentIds": segment_ids}
    elif list_ids:
        recipients = {"listIds": list_ids}
    else:
        raise BrevoError("Aucun destinataire : fournir list_ids ou segment_ids.")
    payload = {
        "name": name,
        "subject": subject,
        "sender": {"name": sender_name, "email": sender_email},
        "type": "classic",
        "htmlContent": html_content,
        "recipients": recipients,
    }
    result = _request("POST", "/emailCampaigns", api_key, payload, timeout)
    campaign_id = result.get("id")
    if not campaign_id:
        raise BrevoError(f"Réponse inattendue de Brevo (pas d'id) : {result}")
    return int(campaign_id)


def list_senders(api_key: str, timeout: int = 30) -> list[dict]:
    """Liste les expéditeurs validés du compte (name + email)."""
    return _request("GET", "/senders", api_key, None, timeout).get("senders", [])


def list_contact_lists(api_key: str, timeout: int = 30) -> list[dict]:
    """Liste les listes de contacts (id + name + nombre d'abonnés)."""
    query = urllib.parse.urlencode({"limit": 50, "sort": "desc"})
    return _request("GET", f"/contacts/lists?{query}", api_key, None, timeout).get("lists", [])


def list_segments(api_key: str, timeout: int = 30) -> list[dict]:
    """Liste les segments de contacts (id + segmentName) pour le ciblage dynamique."""
    query = urllib.parse.urlencode({"limit": 50})
    return _request("GET", f"/contacts/segments?{query}", api_key, None, timeout).get("segments", [])


def list_attributes(api_key: str, timeout: int = 30) -> list[dict]:
    """Liste les attributs de contact du compte (LANGUE, TERRITOIRE…)."""
    return _request("GET", "/contacts/attributes", api_key, None, timeout).get("attributes", [])


def create_attribute(
    api_key: str,
    name: str,
    *,
    attr_type: str = "text",
    category: str = "normal",
    timeout: int = 30,
) -> None:
    """Crée un attribut de contact (idempotence à gérer par l'appelant).

    `category` = 'normal' pour un champ de contact classique ; `attr_type` = 'text',
    'date', 'float', 'boolean'… Brevo répond 400 si l'attribut existe déjà.
    """
    path = f"/contacts/attributes/{category}/{urllib.parse.quote(name)}"
    _request("POST", path, api_key, {"type": attr_type}, timeout)


def list_folders(api_key: str, timeout: int = 30) -> list[dict]:
    """Liste les dossiers de listes de contacts."""
    query = urllib.parse.urlencode({"limit": 50})
    return _request("GET", f"/contacts/folders?{query}", api_key, None, timeout).get("folders", [])


def create_folder(api_key: str, name: str, timeout: int = 30) -> int:
    """Crée un dossier de listes et renvoie son id."""
    result = _request("POST", "/contacts/folders", api_key, {"name": name}, timeout)
    folder_id = result.get("id")
    if not folder_id:
        raise BrevoError(f"Réponse inattendue de Brevo (pas d'id de dossier) : {result}")
    return int(folder_id)


def create_list(api_key: str, name: str, folder_id: int, timeout: int = 30) -> int:
    """Crée une liste de contacts dans un dossier et renvoie son id."""
    payload = {"name": name, "folderId": folder_id}
    result = _request("POST", "/contacts/lists", api_key, payload, timeout)
    list_id = result.get("id")
    if not list_id:
        raise BrevoError(f"Réponse inattendue de Brevo (pas d'id de liste) : {result}")
    return int(list_id)


def campaign_edit_url(campaign_id: int) -> str:
    """URL d'édition du brouillon dans l'interface Brevo."""
    return f"https://app.brevo.com/camp/template/{campaign_id}/message-setup"
