"""Google Sheets integration — sync wrappers (run via asyncio.to_thread)."""
import re

import gspread
from google.oauth2.service_account import Credentials

from config import settings

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_HEADERS: dict[str, list[str]] = {
    "logs": [
        "log_id", "date", "start_at", "end_at",
        "duration_min", "category", "description", "status", "updated_at",
    ],
    "categories": ["category_id", "name", "is_active", "sort_order"],
    "settings": ["setting_name", "setting_value"],
    "daily_report": [
        "date", "total_minutes", "study_minutes",
        "rest_minutes", "hobby_minutes", "notes",
    ],
    "weekly_report": ["week_start", "total_minutes", "summary_text"],
}


def _client() -> gspread.Client:
    creds = Credentials.from_service_account_file(
        settings.google_service_account_json, scopes=_SCOPES
    )
    return gspread.authorize(creds)


def extract_spreadsheet_id(url: str) -> str | None:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


def init_spreadsheet(spreadsheet_id: str) -> None:
    """Create sheets with headers. Safe to call multiple times."""
    gc = _client()
    spreadsheet = gc.open_by_key(spreadsheet_id)
    existing = {ws.title for ws in spreadsheet.worksheets()}

    for sheet_name, headers in SHEET_HEADERS.items():
        if sheet_name not in existing:
            ws = spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=len(headers)
            )
        else:
            ws = spreadsheet.worksheet(sheet_name)
        if not ws.row_values(1):
            ws.update("A1", [headers])

    # Remove default empty Sheet1 if present
    if "Sheet1" in existing:
        try:
            ws = spreadsheet.worksheet("Sheet1")
            if not ws.get_all_values():
                spreadsheet.del_worksheet(ws)
        except gspread.exceptions.WorksheetNotFound:
            pass


def write_categories_to_sheet(
    spreadsheet_id: str, categories: list[tuple]
) -> None:
    """Write category rows starting from A2. categories: [(id, name, is_active, sort_order)]"""
    gc = _client()
    ws = gc.open_by_key(spreadsheet_id).worksheet("categories")
    if len(categories) > 0:
        ws.update("A2", [list(row) for row in categories])


def append_log_row(spreadsheet_id: str, row: list) -> None:
    gc = _client()
    ws = gc.open_by_key(spreadsheet_id).worksheet("logs")
    ws.append_row(row, value_input_option="USER_ENTERED")


def update_log_row(spreadsheet_id: str, log_id: int, row: list) -> None:
    """Find row by log_id in column A and overwrite it."""
    gc = _client()
    ws = gc.open_by_key(spreadsheet_id).worksheet("logs")
    cell = ws.find(str(log_id), in_column=1)
    if cell:
        ws.update(f"A{cell.row}", [row])
