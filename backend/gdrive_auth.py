"""
Google Drive OAuth 2.0 authentication manager.
Handles credentials loading, interactive authorization flow, and token refresh.
"""

import os
import json
from pathlib import Path
from typing import Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Scopes needed for LuminaPhoto backup:
# drive.file allows full management of files/folders created by this app (upload, trash, delete, organize)
SCOPES = ['https://www.googleapis.com/auth/drive.file']

BACKEND_DIR = Path(__file__).parent
CREDENTIALS_FILE = BACKEND_DIR / "credentials.json"
TOKEN_FILE = BACKEND_DIR / "token.json"


def get_credentials_path() -> Path:
    return CREDENTIALS_FILE


def get_token_path() -> Path:
    return TOKEN_FILE


def is_configured() -> bool:
    """Returns True if credentials.json is present."""
    return CREDENTIALS_FILE.exists()


def save_credentials_json(raw_json: str) -> dict:
    """
    Validates and saves a Google Cloud OAuth 2.0 Client ID JSON file to backend/credentials.json.
    Accepts either 'installed' (Desktop app) or 'web' client secret formats.
    """
    try:
        parsed = json.loads(raw_json)
    except Exception as exc:
        raise ValueError(f"Invalid JSON file: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Credentials JSON must be a JSON object.")

    client_config = parsed.get("installed") or parsed.get("web")
    if not isinstance(client_config, dict):
        raise ValueError(
            "Invalid Google OAuth credentials file: missing 'installed' or 'web' configuration block."
        )

    client_id = str(client_config.get("client_id") or "").strip()
    client_secret = str(client_config.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise ValueError(
            "Invalid Google OAuth credentials file: missing 'client_id' or 'client_secret'."
        )

    CREDENTIALS_FILE.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return {
        "configured": True,
        "client_type": "installed" if "installed" in parsed else "web",
        "project_id": client_config.get("project_id", ""),
    }


def is_authenticated() -> bool:
    """Returns True if a valid or refreshable token is present."""
    if not TOKEN_FILE.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        return bool(creds and (creds.valid or (creds.expired and creds.refresh_token)))
    except Exception:
        return False


def get_credentials() -> Optional[Credentials]:
    """
    Loads saved credentials, refreshing if expired.
    Returns None if no token or credentials exist.
    """
    if not TOKEN_FILE.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed credentials
            TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')
        return creds if creds.valid else None
    except Exception as e:
        print(f"[GDrive Auth] Error loading/refreshing credentials: {e}")
        return None


def run_local_auth_flow(port: int = 0) -> Credentials:
    """
    Launches the local browser OAuth 2.0 consent flow.
    Saves the acquired token to token.json.
    """
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"Missing Google credentials file at {CREDENTIALS_FILE}")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    # run_local_server will spin up a temporary local server and open the user's default browser
    creds = flow.run_local_server(port=port, prompt='consent', access_type='offline')

    # Save the credentials for future runs
    TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')
    return creds


VERIFIER_FILE = BACKEND_DIR / ".oauth_verifier.json"
ACTIVE_VERIFIERS = {}


def _save_verifier(state: str, verifier: Optional[str]):
    if not state:
        return
    entry = verifier or ""
    ACTIVE_VERIFIERS[state] = entry
    try:
        data = {}
        if VERIFIER_FILE.exists():
            data = json.loads(VERIFIER_FILE.read_text(encoding="utf-8"))
            data.pop("latest", None)
        data[state] = entry
        VERIFIER_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _consume_verifier(state: Optional[str] = None) -> str:
    if not state or state == "latest":
        raise ValueError("Missing or invalid OAuth state parameter")
    if state in ACTIVE_VERIFIERS:
        verifier = ACTIVE_VERIFIERS.pop(state)
        try:
            if VERIFIER_FILE.exists():
                data = json.loads(VERIFIER_FILE.read_text(encoding="utf-8"))
                data.pop(state, None)
                data.pop("latest", None)
                VERIFIER_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass
        return verifier
    try:
        if VERIFIER_FILE.exists():
            data = json.loads(VERIFIER_FILE.read_text(encoding="utf-8"))
            if state in data:
                verifier = data.pop(state)
                data.pop("latest", None)
                VERIFIER_FILE.write_text(json.dumps(data), encoding="utf-8")
                return verifier
    except Exception:
        pass
    raise ValueError("Invalid or expired OAuth state parameter")


def create_auth_url(redirect_uri: str = "http://localhost:8500/api/backup/auth/callback"):
    """
    Generates an OAuth authorization URL for the user to open in their browser.
    Stores the PKCE code_verifier so it matches when Google returns the code.
    """
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"Missing Google credentials file at {CREDENTIALS_FILE}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES,
        redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        prompt='consent',
        access_type='offline',
        include_granted_scopes='true'
    )
    _save_verifier(state, getattr(flow, 'code_verifier', None))
    return auth_url, state


def exchange_auth_code(
    code: str,
    state: Optional[str] = None,
    redirect_uri: str = "http://localhost:8500/api/backup/auth/callback"
) -> Credentials:
    """
    Exchanges an authorization code received from Google for tokens and saves token.json.
    Validates OAuth state and restores the PKCE code_verifier to satisfy Google's security check.
    """
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"Missing Google credentials file at {CREDENTIALS_FILE}")

    verifier = _consume_verifier(state)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES,
        redirect_uri=redirect_uri
    )
    if verifier:
        flow.code_verifier = verifier

    flow.fetch_token(code=code)
    creds = flow.credentials
    TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')
    return creds


def disconnect():
    """Removes the stored token to disconnect the Google account."""
    if TOKEN_FILE.exists():
        try:
            TOKEN_FILE.unlink()
        except Exception as e:
            print(f"[GDrive Auth] Error removing token file: {e}")


