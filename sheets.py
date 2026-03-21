import base64
import json
import os

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
GRID_TAB = os.environ.get("NCAA_GRID_TAB", "Sheet1")


def get_client():
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_B64", "")
    if creds_b64:
        creds_json = json.loads(base64.b64decode(creds_b64))
        creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    elif os.path.exists("credentials.json"):
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    else:
        raise RuntimeError("No credentials found. Set GOOGLE_CREDENTIALS_B64 or provide credentials.json.")
    return gspread.authorize(creds)


def load_picks(spreadsheet_id):
    """Load player picks from Google Sheet.

    Sheet format (column-oriented):
      Row 1:    "Name",  Player1,  Player2,  ...
      Row 2-9:  "Picks", pick1,    pick1,    ...

    Returns list of {"name": str, "picks": [str, ...]}
    """
    client = get_client()
    sheet = client.open_by_key(spreadsheet_id).worksheet(GRID_TAB)
    rows = sheet.get_all_values()

    if not rows:
        return []

    header_row = rows[0]
    players = []

    for col_idx in range(1, len(header_row)):
        name = header_row[col_idx].strip()
        if not name:
            continue

        picks = []
        for row in rows[1:]:
            if col_idx < len(row):
                pick = row[col_idx].strip()
                if pick and pick.lower() != "picks":
                    picks.append(pick)

        if picks:
            players.append({"name": name, "picks": picks})

    return players
