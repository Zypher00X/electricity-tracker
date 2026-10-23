from typing import Optional

from app.repositories.google_sheets import (
    get_users_worksheet,
)

import re


def get_all_users() -> list[dict]:

    worksheet = get_users_worksheet()

    rows = worksheet.get_all_values()

    # Sheet ว่าง
    if not rows:
        return []

    # แถวแรกคือ Header
    headers = rows[0]

    users = []

    # แถวที่เหลือคือข้อมูล
    for row in rows[1:]:

        # เติมช่องว่างกรณี row สั้นกว่า header
        padded_row = row + [""] * (
            len(headers) - len(row)
        )

        user = dict(
            zip(
                headers,
                padded_row,
            )
        )

        users.append(user)

    return users


def find_user_by_email(
    email: str,
) -> Optional[dict]:

    users = get_all_users()

    email = email.strip().lower()

    for user in users:

        stored_email = str(
            user.get("email", "")
        ).strip().lower()

        if stored_email == email:
            return user

    return None


def normalize_phone(
    phone: str,
) -> str:

    return re.sub(
        r"\D",
        "",
        str(phone),
    )


def find_user_by_phone(
    phone: str,
) -> Optional[dict]:

    users = get_all_users()

    phone = normalize_phone(phone)

    for user in users:

        stored_phone = normalize_phone(
            user.get("phone", "")
        )

        if stored_phone == phone:
            return user

    return None


def create_user(
    user_id: str,
    full_name: str,
    email: str,
    phone: str,
    password_hash: str,
    auth_provider: str,
    google_sub: str,
    role: str,
    status: str,
    created_at: str,
    updated_at: str,
) -> None:

    worksheet = get_users_worksheet()

    worksheet.append_row(
        [
            user_id,
            full_name,
            email,
            phone,
            password_hash,
            auth_provider,
            google_sub,
            role,
            status,
            created_at,
            updated_at,
            "",  # last_login_at
        ],
        value_input_option="RAW",
    )

# ========================================
# ฟังก์ชันค้นหาผู้ใช้โดยใช้ identifier (email หรือ phone) ในของฝั่ง login
def find_user_by_identifier(
    identifier: str,
) -> Optional[dict]:

    identifier = identifier.strip()

    # ถ้ามี @ ให้ลองค้นหาเป็น email
    if "@" in identifier:

        return find_user_by_email(
            identifier
        )

    # ถ้าไม่ใช่ email ให้ลองเป็น phone
    normalized_phone = normalize_phone(
        identifier
    )

    if normalized_phone:

        return find_user_by_phone(
            normalized_phone
        )

    return None

# ========================================
# ฟังก์ชันค้นหาผู้ใช้โดยใช้ user_id
def find_user_by_id(
    user_id: str,
) -> Optional[dict]:

    users = get_all_users()

    user_id = str(
        user_id
    ).strip()


    for user in users:

        stored_user_id = str(
            user.get(
                "user_id",
                ""
            )
        ).strip()


        if stored_user_id == user_id:

            return user


    return None

# =======================================
# ฟังก์ชันค้นหาผู้ใช้โดยใช้ google_sub
def find_user_by_google_sub(
    google_sub: str,
) -> Optional[dict]:

    users = get_all_users()

    google_sub = str(
        google_sub
    ).strip()


    if not google_sub:
        return None


    for user in users:

        stored_google_sub = str(
            user.get(
                "google_sub",
                ""
            )
        ).strip()


        if stored_google_sub == google_sub:

            return user


    return None

# =======================================
# ฟังก์ชันอัปเดต last_login_at ของผู้ใช้
def update_last_login_at(
    user_id: str,
    last_login_at: str,
) -> bool:

    worksheet = get_users_worksheet()

    rows = worksheet.get_all_values()

    if not rows:
        return False


    headers = rows[0]


    try:

        user_id_column = (
            headers.index("user_id")
            + 1
        )

        last_login_column = (
            headers.index("last_login_at")
            + 1
        )

    except ValueError:

        return False


    for row_number, row in enumerate(
        rows[1:],
        start=2,
    ):

        padded_row = (
            row
            + [""] * (
                len(headers)
                - len(row)
            )
        )


        stored_user_id = str(
            padded_row[
                user_id_column - 1
            ]
        ).strip()


        if stored_user_id == user_id:

            worksheet.update_cell(
                row_number,
                last_login_column,
                last_login_at,
            )

            return True


    return False