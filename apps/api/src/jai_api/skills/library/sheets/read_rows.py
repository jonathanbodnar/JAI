"""Read rows from a Google Sheets tab.

Unlike `drive.read_doc` (which only exports the first tab as CSV),
this skill uses the Sheets API directly so you can:
  - Target a specific tab by name ("New Creator Links")
  - Restrict to an A1 range ("A2:D200")
  - Get rows back as structured dicts using the header row as keys

Designed for "fill out this template using my sheet" workflows —
the rows live in skill_output so the next turn's responder can
render the template against them without re-fetching.
"""

KEY = "sheets.read_rows"
TITLE = "Read Google Sheets rows"
DESCRIPTION = (
    "Read rows from a Google Sheets tab. Inputs: url (full Sheets "
    "URL — preferred — we extract the spreadsheet ID from it), OR "
    "spreadsheet_id directly; sheet_name (the tab name, e.g. 'New "
    "Creator Links' — defaults to the first visible tab); range "
    "(optional A1 range like 'A1:E500' to restrict the read); "
    "header_row (default true — treat the first row as column "
    "headers and emit each subsequent row as a dict). Returns "
    "{tab, header, rows: [dict, ...], rows_raw: [[cells]], "
    "row_count}. Use for any 'read my <sheet> spreadsheet', 'fill "
    "out this template using my <sheet>', 'how many rows are in <X> "
    "tab', 'list everyone in my outreach sheet'."
)
LANGUAGE = "python"
USES_CREDENTIALS: list[str] = []
REQUIRED_TOOLS = ["drive", "sheets"]

SOURCE = r"""
import os, json, re
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

inputs = json.loads(os.environ.get("JAI_SKILL_INPUTS_JSON") or "{}")
intent = (os.environ.get("JAI_USER_INTENT") or "").strip()

# --- Resolve spreadsheet_id. ---
def _extract_sheet_id(text):
    if not text:
        return None
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9\-_]{20,})", text)
    return m.group(1) if m else None

url = (inputs.get("url") or "").strip()
spreadsheet_id = (inputs.get("spreadsheet_id") or "").strip()
if not spreadsheet_id:
    spreadsheet_id = _extract_sheet_id(url) or _extract_sheet_id(intent) or ""

if not spreadsheet_id:
    print(json.dumps({"status": "error", "error":
        "Need a spreadsheet — paste the Google Sheets URL or pass spreadsheet_id."}))
    raise SystemExit(0)

# Optional `gid=…` in the URL tells us which tab — Sheets calls these
# `sheetId` (integers). The user-facing `sheet_name` always wins.
url_gid = None
gid_match = re.search(r"[#&]gid=(\d+)", url or intent or "")
if gid_match:
    try:
        url_gid = int(gid_match.group(1))
    except Exception:
        url_gid = None

sheet_name = (inputs.get("sheet_name") or inputs.get("tab") or "").strip()
range_a1 = (inputs.get("range") or "").strip()
header_row = inputs.get("header_row")
if header_row is None:
    header_row = True

def _service(token_json, api, version):
    info = dict(token_json)
    info["token"] = info.get("token") or info.get("access_token")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build(api, version, credentials=creds, cache_discovery=False)

accounts = json.loads(os.environ.get("DRIVE_ACCOUNTS_JSON") or "[]")
if not accounts and os.environ.get("DRIVE_OAUTH_JSON"):
    accounts = [{"email": "default",
                 "token_json": json.loads(os.environ["DRIVE_OAUTH_JSON"])}]
if not accounts:
    print(json.dumps({"status": "error", "error":
        "No Drive/Sheets account connected. Open Settings → Connections "
        "to link one (Drive scope covers Sheets read access)."}))
    raise SystemExit(0)

last_err = None
for acc in accounts:
    try:
        sheets = _service(acc["token_json"], "sheets", "v4")

        # 1. Fetch tab metadata so we can resolve the right tab + know
        #    the visible row/col bounds for the default range.
        meta = sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            includeGridData=False,
        ).execute()
        tabs = meta.get("sheets", [])
        if not tabs:
            last_err = "Spreadsheet has no tabs (or is empty)."
            continue

        chosen = None
        if sheet_name:
            chosen = next(
                (t for t in tabs
                 if (t.get("properties", {}).get("title") or "").strip().lower()
                 == sheet_name.lower()),
                None,
            )
            if chosen is None:
                last_err = (
                    f"Tab '{sheet_name}' not found. Available tabs: "
                    + ", ".join(t["properties"]["title"] for t in tabs)
                )
                continue
        elif url_gid is not None:
            chosen = next(
                (t for t in tabs
                 if t.get("properties", {}).get("sheetId") == url_gid),
                None,
            )
        if chosen is None:
            # Default to first visible tab.
            chosen = next(
                (t for t in tabs
                 if not t.get("properties", {}).get("hidden")),
                tabs[0],
            )

        tab_title = chosen["properties"]["title"]
        grid = chosen.get("properties", {}).get("gridProperties") or {}
        row_count = grid.get("rowCount") or 1000
        col_count = grid.get("columnCount") or 26

        # 2. Resolve the A1 range.
        if range_a1:
            full_range = f"'{tab_title}'!{range_a1}"
        else:
            # All cells in the tab, capped at the grid's actual size.
            def _col_letter(n):
                s = ""
                while n > 0:
                    n, r = divmod(n - 1, 26)
                    s = chr(65 + r) + s
                return s
            full_range = f"'{tab_title}'!A1:{_col_letter(col_count)}{row_count}"

        # 3. Read values.
        values = sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=full_range,
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        ).execute().get("values", [])

        # Strip trailing all-empty rows the user left behind.
        while values and all((c is None or str(c).strip() == "") for c in values[-1]):
            values.pop()

        header = []
        rows_dict = []
        if header_row and values:
            header = [str(h).strip() for h in values[0]]
            for r in values[1:]:
                row = {}
                for i, h in enumerate(header):
                    key = h or f"col_{i+1}"
                    row[key] = r[i] if i < len(r) else None
                rows_dict.append(row)

        print(json.dumps({"status": "ok", "result": {
            "kind": "sheet_rows",
            "account": acc.get("email"),
            "spreadsheet_id": spreadsheet_id,
            "title": meta.get("properties", {}).get("title"),
            "tab": tab_title,
            "header": header,
            "rows": rows_dict if header_row else values,
            "rows_raw": values,
            "row_count": (len(values) - (1 if header_row and header else 0)),
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={chosen['properties'].get('sheetId', 0)}",
            "available_tabs": [t["properties"]["title"] for t in tabs],
        }}))
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as e:
        # Common: 404 (no access), 403 (scope missing). Track and move on.
        last_err = f"{type(e).__name__}: {str(e)[:240]}"
        continue

print(json.dumps({"status": "error", "error":
    last_err or "Couldn't read that sheet from any connected Drive account. "
    "Make sure the account you connected has access (try opening the URL "
    "in that browser session) or reconnect it in Settings → Connections."}))
"""
