"""Read data from Google Sheets using a service account."""

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ("https://www.googleapis.com/auth/spreadsheets.readonly",)


def get_client(credentials_path: str | Path) -> gspread.Client:
    """Build an authorized gspread client from a service account JSON key file."""
    credentials = Credentials.from_service_account_file(
        str(credentials_path),
        scopes=SCOPES,
    )
    return gspread.authorize(credentials)


def read_worksheet(
    client: gspread.Client,
    spreadsheet_id: str,
    *,
    worksheet: str | None = None,
    cell_range: str | None = None,
) -> list[list[str]]:
    """Return worksheet values as rows of strings."""
    spreadsheet = client.open_by_key(spreadsheet_id)
    sheet = spreadsheet.worksheet(worksheet) if worksheet else spreadsheet.sheet1
    if cell_range:
        return sheet.get(cell_range)
    return sheet.get_all_values()
