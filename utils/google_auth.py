"""Authentification Google partagée (Gmail + Drive).

Centralise la logique OAuth2 et propose deux modes :

- mode normal (`manual=False`) : ouvre un navigateur local (machine de bureau) ;
- mode manuel (`manual=True`) : affiche une URL, l'utilisateur autorise dans
  SON navigateur puis recolle l'URL de redirection (contenant le code).
  Indispensable sur un serveur sans navigateur (VPS).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _extract_code(value: str) -> str:
    """Extrait le code OAuth d'une URL de redirection complète ou d'un code brut."""
    value = value.strip()
    if "code=" in value:
        parsed = parse_qs(urlparse(value).query)
        if "code" in parsed:
            return parsed["code"][0]
    return value


def _run_manual_flow(flow):
    """Flux OAuth sans navigateur local (copier/coller de l'URL de redirection)."""
    flow.redirect_uri = "http://localhost"
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    print("\n" + "=" * 70)
    print("1) Ouvre cette URL dans ton navigateur et autorise l'accès :\n")
    print(auth_url)
    print(
        "\n2) Après autorisation, le navigateur affichera une page d'erreur du type"
        "\n   « localhost a refusé la connexion » : c'est NORMAL."
        "\n   Copie l'URL COMPLÈTE depuis la barre d'adresse (elle contient ?code=...)."
    )
    print("=" * 70)
    redirected = input("3) Colle ici l'URL complète (ou juste le code) : ")
    flow.fetch_token(code=_extract_code(redirected))
    return flow.credentials


def load_credentials(
    scopes: list[str],
    token_path: Path,
    credentials_path: Path,
    manual: bool = False,
):
    """Retourne des identifiants Google valides, en (ré)autorisant si besoin.

    Le jeton est mis en cache dans `token_path` pour les exécutions suivantes.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Dépendances Google manquantes. Exécuter : pip install -r requirements.txt"
        ) from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Identifiants OAuth2 introuvables : {credentials_path}. "
            "Déposer credentials.json depuis Google Cloud Console."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
    creds = _run_manual_flow(flow) if manual else flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
