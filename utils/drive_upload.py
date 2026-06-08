"""Upload de fichiers vers Google Drive (dossier « Observatoire Économique »).

Utilise OAuth2 avec le scope `drive.file` (l'application ne voit que les
fichiers qu'elle crée). Réutilise le `credentials.json` Gmail mais stocke
un jeton distinct (`config/token_drive.json`) car le scope diffère.

Usage CLI :
    python utils/drive_upload.py chemin/vers/fichier.md [DOSSIER_ID]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.logger import get_logger  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
TOKEN_PATH = CONFIG_DIR / "token_drive.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

log = get_logger("drive_upload")


def _credentials_path() -> Path:
    return Path(os.getenv("GMAIL_CREDENTIALS_PATH", CONFIG_DIR / "credentials.json"))


def _get_service(manual: bool = False):
    """Construit le service Drive (gère le jeton et son rafraîchissement)."""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Dépendances Google manquantes. Exécuter : pip install -r requirements.txt"
        ) from exc

    from utils.google_auth import load_credentials

    creds = load_credentials(SCOPES, TOKEN_PATH, _credentials_path(), manual=manual)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_or_create_subfolder(service, parent_id: str, name: str) -> str:
    """Retourne l'ID d'un sous-dossier (créé s'il n'existe pas) sous `parent_id`."""
    safe = name.replace("'", "\\'")
    query = (
        f"name = '{safe}' and '{parent_id}' in parents and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    found = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id)", pageSize=1)
        .execute()
        .get("files", [])
    )
    if found:
        return found[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=metadata, fields="id").execute()
    log.info("Sous-dossier Drive créé : %s (id=%s)", name, created["id"])
    return created["id"]


def upload_file(
    local_path: str | Path,
    folder_id: str | None = None,
    subfolder: str | None = None,
) -> str | None:
    """Téléverse un fichier vers Drive. Retourne l'ID Drive, ou None en cas d'échec.

    - `folder_id` : dossier racine (défaut : DRIVE_FOLDER_ID).
    - `subfolder` : nom d'un sous-dossier sous la racine (créé au besoin).
    Si un fichier du même nom existe déjà dans le dossier cible, son contenu est
    mis à jour (pas de doublon).
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    local_path = Path(local_path)
    if not local_path.exists():
        log.error("Fichier introuvable : %s", local_path)
        return None

    folder_id = folder_id or os.getenv("DRIVE_FOLDER_ID")
    if not folder_id:
        log.error("DRIVE_FOLDER_ID non défini (ni argument, ni variable d'environnement).")
        return None

    try:
        service = _get_service()
        if subfolder:
            folder_id = _find_or_create_subfolder(service, folder_id, subfolder)
        media = MediaFileUpload(str(local_path), resumable=True)

        # Recherche d'un fichier existant de même nom dans le dossier
        safe_name = local_path.name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and '{folder_id}' in parents and trashed = false"
        )
        existing = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id)", pageSize=1)
            .execute()
            .get("files", [])
        )

        if existing:
            file_id = existing[0]["id"]
            service.files().update(fileId=file_id, media_body=media).execute()
            log.info("Fichier mis à jour sur Drive : %s (id=%s)", local_path.name, file_id)
            return file_id

        metadata = {"name": local_path.name, "parents": [folder_id]}
        created = (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )
        file_id = created.get("id")
        log.info("Fichier téléversé sur Drive : %s (id=%s)", local_path.name, file_id)
        return file_id

    except HttpError as exc:
        log.error("Erreur API Drive lors de l'upload de %s : %s", local_path.name, exc)
    except Exception as exc:  # pragma: no cover
        log.error("Échec de l'upload de %s : %s", local_path.name, exc)
    return None


def _plain_html_document(fragment_html: str, title: str) -> str:
    """Page HTML minimale (sans style email) pour une conversion propre en Doc."""
    from html import escape

    return (
        "<!DOCTYPE html>\n<html lang=\"fr\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(title)}</title></head><body>\n{fragment_html}\n</body></html>"
    )


def upload_markdown_as_gdoc(
    local_md: str | Path,
    folder_id: str | None = None,
    subfolder: str | None = None,
    name: str | None = None,
) -> str | None:
    """Téléverse un fichier Markdown comme **Google Doc natif** (mise en forme).

    Drive convertit le HTML envoyé en document Google. Le titre du Doc est `name`
    (défaut : nom de fichier sans extension). Dédoublonnage : si un Doc du même
    titre existe déjà dans le dossier, son contenu est remplacé (pas de doublon).
    Retourne l'ID Drive, ou None en cas d'échec.
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaInMemoryUpload

    from utils.markdown_html import md_to_html_fragment

    local_md = Path(local_md)
    if not local_md.exists():
        log.error("Fichier introuvable : %s", local_md)
        return None

    folder_id = folder_id or os.getenv("DRIVE_FOLDER_ID")
    if not folder_id:
        log.error("DRIVE_FOLDER_ID non défini (ni argument, ni variable d'environnement).")
        return None

    doc_name = name or local_md.stem
    GDOC_MIME = "application/vnd.google-apps.document"
    try:
        fragment = md_to_html_fragment(local_md.read_text(encoding="utf-8"))
        html = _plain_html_document(fragment, doc_name)
        media = MediaInMemoryUpload(html.encode("utf-8"), mimetype="text/html", resumable=True)

        service = _get_service()
        if subfolder:
            folder_id = _find_or_create_subfolder(service, folder_id, subfolder)

        safe_name = doc_name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and '{folder_id}' in parents and "
            f"mimeType = '{GDOC_MIME}' and trashed = false"
        )
        existing = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id)", pageSize=1)
            .execute()
            .get("files", [])
        )
        if existing:
            file_id = existing[0]["id"]
            service.files().update(fileId=file_id, media_body=media).execute()
            log.info("Google Doc mis à jour : %s (id=%s)", doc_name, file_id)
            return file_id

        metadata = {"name": doc_name, "parents": [folder_id], "mimeType": GDOC_MIME}
        created = (
            service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )
        file_id = created.get("id")
        log.info("Google Doc créé : %s (id=%s)", doc_name, file_id)
        return file_id
    except HttpError as exc:
        log.error("Erreur API Drive (Doc %s) : %s", doc_name, exc)
    except Exception as exc:  # pragma: no cover
        log.error("Échec de la création du Google Doc %s : %s", doc_name, exc)
    return None


def main() -> int:
    load_dotenv(ROOT / ".env")
    if len(sys.argv) < 2:
        print("Usage : python utils/drive_upload.py <fichier> [DOSSIER_ID]")
        return 2
    path = sys.argv[1]
    folder = sys.argv[2] if len(sys.argv) > 2 else None
    file_id = upload_file(path, folder)
    return 0 if file_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
