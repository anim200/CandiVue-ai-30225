"""Read-only access to the Google Form's answers and the uploaded CVs.

- Answers: the form's response Sheet (Google Sheets API).
- CV files: Google Drive (Drive API).
A service account is used: it can only see the folder and Sheet that were
shared with it, and only read them. Its key comes from .env (N7).
"""

import base64
import binascii
import json

import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]
SHEET_URL = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/A:Z"
SHEET_INFO_URL = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
FILE_URL = "https://www.googleapis.com/drive/v3/files/{file_id}"
TIMEOUT_SECONDS = 30


class GoogleSourceError(Exception):
    """Google could not be read; the message has no secrets or personal data."""


def load_key(raw: str) -> dict:
    """Read the service account key: the JSON itself or the JSON in base64."""
    text = raw.strip()
    try:
        if not text.startswith("{"):
            text = base64.b64decode(text).decode("utf-8")
        return json.loads(text)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise GoogleSourceError(
            "GOOGLE_SERVICE_ACCOUNT_KEY is not a valid key (JSON or base64 JSON)."
        ) from None


class GoogleSource:
    """Reads the response Sheet and downloads CV files with the service account."""

    def __init__(self, key: dict, sheet_id: str):
        """Sign in as the service account (read-only scopes)."""
        credentials = service_account.Credentials.from_service_account_info(
            key, scopes=SCOPES
        )
        self.session = AuthorizedSession(credentials)
        self.sheet_id = sheet_id

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        """One GET request to Google; any failure becomes GoogleSourceError."""
        try:
            response = self.session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        except GoogleAuthError:
            raise GoogleSourceError("Google sign-in failed: check the key.") from None
        except requests.RequestException:
            raise GoogleSourceError("Google could not be reached.") from None
        if response.status_code in (403, 404):
            raise GoogleSourceError(
                f"Google refused access (HTTP {response.status_code}): is it shared "
                "with the service account?"
            )
        if response.status_code >= 400:
            raise GoogleSourceError(f"Google answered HTTP {response.status_code}.")
        return response

    def response_rows(self) -> list[list]:
        """All rows of the response Sheet; the first row holds the questions.
        The submission time comes as a number (days since 30 Dec 1899 in the
        Sheet's time zone), so it never depends on the Sheet's date format."""
        url = SHEET_URL.format(sheet_id=self.sheet_id)
        params = {
            "valueRenderOption": "UNFORMATTED_VALUE",
            "dateTimeRenderOption": "SERIAL_NUMBER",
        }
        return self._get(url, params).json().get("values", [])

    def time_zone(self) -> str:
        """The Sheet's time zone, e.g. "Asia/Dhaka" (for the submission times)."""
        url = SHEET_INFO_URL.format(sheet_id=self.sheet_id)
        params = {"fields": "properties.timeZone"}
        return self._get(url, params).json()["properties"]["timeZone"]

    def file_info(self, file_id: str) -> dict:
        """A Drive file's name and size (checked before downloading it)."""
        params = {"fields": "name,size", "supportsAllDrives": "true"}
        return self._get(FILE_URL.format(file_id=file_id), params).json()

    def download(self, file_id: str) -> bytes:
        """The content of a Drive file."""
        params = {"alt": "media", "supportsAllDrives": "true"}
        return self._get(FILE_URL.format(file_id=file_id), params).content
