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


def _get_service():
    """Construit le service Drive (gère le jeton et son rafraîchissement)."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Dépendances Google manquantes. Exécuter : pip install -r requirements.txt"
        ) from exc

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            cred_file = _credentials_path()
            if not cred_file.exists():
                raise FileNotFoundError(
                    f"Fichier d'identifiants introuvable : {cred_file}. "
                    "Le déposer depuis Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_file), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_file(local_path: str | Path, folder_id: str | None = None) -> str | None:
    """Téléverse un fichier vers Drive. Retourne l'ID Drive, ou None en cas d'échec.

    Si un fichier du même nom existe déjà dans le dossier, son contenu est mis
    à jour (pas de doublon).
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
