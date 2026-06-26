"""CLI to sync on-call schedule and contacts from Google Sheets."""

import argparse
import json
import sys
from pathlib import Path

import dotenv
import gspread

from gwalert.config import DEFAULT_ENV_FILE, Settings
from gwalert.google_sheets import get_client, read_worksheet
from gwalert.schedule import parse_contacts_rows, parse_schedule_rows

DEFAULT_OUTPUT_PATH = "schedule.json"
SCHEDULE_WORKSHEET = "Schedule"
CONTACTS_WORKSHEET = "Contacts"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync on-call schedule and contacts from Google Sheets.",
    )
    parser.add_argument(
        "--spreadsheet-id",
        help="Spreadsheet ID from the sheet URL (overrides GWALERT_GOOGLE_SHEETS_SPREADSHEET_ID)",
    )
    parser.add_argument(
        "--credentials",
        help="Path to service account JSON (overrides GWALERT_GOOGLE_SHEETS_CREDENTIALS_PATH)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw worksheet rows instead of the parsed output",
    )
    return parser


def fetch_oncall_data(
    client: gspread.Client,
    spreadsheet_id: str,
) -> dict[str, object]:
    schedule_rows = read_worksheet(
        client,
        spreadsheet_id,
        worksheet=SCHEDULE_WORKSHEET,
    )
    contacts_rows = read_worksheet(
        client,
        spreadsheet_id,
        worksheet=CONTACTS_WORKSHEET,
    )
    return {
        "schedule": parse_schedule_rows(schedule_rows),
        "contacts": parse_contacts_rows(contacts_rows),
    }


def fetch_raw_oncall_data(
    client: gspread.Client,
    spreadsheet_id: str,
) -> dict[str, list[list[str]]]:
    return {
        SCHEDULE_WORKSHEET: read_worksheet(
            client,
            spreadsheet_id,
            worksheet=SCHEDULE_WORKSHEET,
        ),
        CONTACTS_WORKSHEET: read_worksheet(
            client,
            spreadsheet_id,
            worksheet=CONTACTS_WORKSHEET,
        ),
    }


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings(_env_file=dotenv.find_dotenv(DEFAULT_ENV_FILE))

    spreadsheet_id = args.spreadsheet_id or settings.google_sheets_spreadsheet_id
    if not spreadsheet_id:
        print(
            "Missing spreadsheet ID. Set GWALERT_GOOGLE_SHEETS_SPREADSHEET_ID "
            "or pass --spreadsheet-id.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    credentials_path = args.credentials or settings.google_sheets_credentials_path
    if not credentials_path:
        print(
            "Missing credentials path. Set GWALERT_GOOGLE_SHEETS_CREDENTIALS_PATH "
            "or pass --credentials.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    client = get_client(credentials_path)

    if args.raw:
        data = fetch_raw_oncall_data(client, spreadsheet_id)
        print(json.dumps(data, indent=2))
        return

    data = fetch_oncall_data(client, spreadsheet_id)
    output_path = Path(args.output or DEFAULT_OUTPUT_PATH)
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    contact_count = len(data["contacts"])
    print(f"Saved schedule and {contact_count} contacts to {output_path}")


if __name__ == "__main__":
    main()
