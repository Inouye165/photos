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


def _save_verifier(state: str, verifier: str):
    ACTIVE_VERIFIERS[state] = verifier
    ACTIVE_VERIFIERS["latest"] = verifier
    try:
        data = {}
        if VERIFIER_FILE.exists():
            data = json.loads(VERIFIER_FILE.read_text(encoding="utf-8"))
        data[state] = verifier
        data["latest"] = verifier
        VERIFIER_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def _get_verifier(state: Optional[str] = None) -> Optional[str]:
    if state and state in ACTIVE_VERIFIERS:
        return ACTIVE_VERIFIERS[state]
    if "latest" in ACTIVE_VERIFIERS:
        return ACTIVE_VERIFIERS["latest"]
    try:
        if VERIFIER_FILE.exists():
            data = json.loads(VERIFIER_FILE.read_text(encoding="utf-8"))
            if state and state in data:
                return data[state]
            return data.get("latest")
    except Exception:
        pass
    return None


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
    if getattr(flow, 'code_verifier', None):
        _save_verifier(state, flow.code_verifier)
    return auth_url, state


def exchange_auth_code(
    code: str,
    state: Optional[str] = None,
    redirect_uri: str = "http://localhost:8500/api/backup/auth/callback"
) -> Credentials:
    """
    Exchanges an authorization code received from Google for tokens and saves token.json.
    Restores the PKCE code_verifier to satisfy Google's security check.
    """
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"Missing Google credentials file at {CREDENTIALS_FILE}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES,
        redirect_uri=redirect_uri
    )
    verifier = _get_verifier(state)
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


