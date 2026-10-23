"""Serialize uniqueness checks and appends; Google Sheets has no unique index."""
import hashlib
from functools import wraps
from app.electricity.service import ElectricityService
from app.repositories.google_sheets import GOOGLE_SPREADSHEET_ID, GOOGLE_USERS_SHEET
from app.services import session_service


def registration_guard(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        namespace = hashlib.sha256(f'{GOOGLE_SPREADSHEET_ID}:{GOOGLE_USERS_SHEET}'.encode()).hexdigest()[:16]
        with ElectricityService(None, session_service.redis_client, 'powertrack:register:' + namespace).sheet_lock() as guard:
            return function(*args, **kwargs, _write_guard=guard)
    return guarded
