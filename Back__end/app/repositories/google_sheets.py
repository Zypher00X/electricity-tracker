import os

import gspread
from google.oauth2.service_account import Credentials


# ==========================================
# GOOGLE SHEETS CONFIG
# ==========================================

GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    "/app/credentials/google-service-account.json",
)

GOOGLE_SPREADSHEET_ID = os.getenv(
    "GOOGLE_SPREADSHEET_ID"
)

GOOGLE_USERS_SHEET = os.getenv(
    "GOOGLE_USERS_SHEET",
    "users",
)


# ==========================================
# GOOGLE API SCOPES
# ==========================================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ==========================================
# CREATE GOOGLE SHEETS CLIENT
# ==========================================

def get_google_sheets_client():

    credentials = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH,
        scopes=SCOPES,
    )

    client = gspread.authorize(credentials)

    return client


# ==========================================
# OPEN SPREADSHEET
# ==========================================

def get_spreadsheet():

    if not GOOGLE_SPREADSHEET_ID:
        raise ValueError(
            "GOOGLE_SPREADSHEET_ID is not configured"
        )

    client = get_google_sheets_client()

    spreadsheet = client.open_by_key(
        GOOGLE_SPREADSHEET_ID
    )

    return spreadsheet


# ==========================================
# USERS WORKSHEET
# ==========================================

def get_users_worksheet():

    spreadsheet = get_spreadsheet()

    worksheet = spreadsheet.worksheet(
        GOOGLE_USERS_SHEET
    )

    return worksheet


# ==========================================
# CONNECTION TEST
# ==========================================

def test_google_sheets_connection():

    spreadsheet = get_spreadsheet()

    worksheet = get_users_worksheet()

    headers = worksheet.row_values(1)

    return {
        "spreadsheet_title": spreadsheet.title,
        "worksheet_title": worksheet.title,
        "headers": headers,
    }