from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.services.registration_guard import registration_guard

from app.schemas.auth import (
    RegisterRequest,
)

from app.utils.security import (
    hash_password,
    verify_password,
)

from app.repositories.user_repository import (
    create_user,
    find_user_by_email,
    find_user_by_phone,
    find_user_by_google_sub,
    update_last_login_at,
)

from app.services.session_service import (
    create_session,
)

from app.core.jwt import (
    create_access_token,
)

THAILAND_TIMEZONE = timezone(
    timedelta(hours=7)
)


class EmailAlreadyExistsError(Exception):
    pass


class PhoneAlreadyExistsError(Exception):
    pass

class InvalidCredentialsError(Exception):
    pass


class UserInactiveError(Exception):
    pass

class GoogleAccountAlreadyExistsError(Exception):
    pass


class LocalAccountEmailExistsError(Exception):
    pass

class GoogleAccountNotFoundError(Exception):
    pass

# =====================================
# ฟังก์ชันสำหรับสมัครสมาชิกผู้ใช้ใหม่
@registration_guard
def register_user(
    data: RegisterRequest,
    _write_guard=None,
) -> dict:

    email = data.email.lower().strip()
    phone = data.phone
    full_name = data.full_name.strip()


    # =====================================
    # CHECK EMAIL
    # =====================================

    existing_email = find_user_by_email(
        email
    )

    if existing_email:
        raise EmailAlreadyExistsError()


    # =====================================
    # CHECK PHONE
    # =====================================

    existing_phone = find_user_by_phone(
        phone
    )

    if existing_phone:
        raise PhoneAlreadyExistsError()


    # =====================================
    # GENERATE ID
    # =====================================

    user_id = str(uuid4())


    # =====================================
    # HASH PASSWORD
    # =====================================

    password_hash = hash_password(
        data.password
    )


    # =====================================
    # SECURITY DEFAULTS
    # =====================================

    role = "user"
    account_status = "active"


    # =====================================
    # DATE / TIME
    # =====================================

    current_time = datetime.now(
        THAILAND_TIMEZONE
    ).isoformat(
        timespec="seconds"
    )


    # =====================================
    # SAVE USER
    # =====================================

    _write_guard()
    create_user(
        user_id=user_id,
        full_name=full_name,
        email=email,
        phone=phone,
        password_hash=password_hash,

        auth_provider="local",
        google_sub="",

        role=role,
        status=account_status,
        created_at=current_time,
        updated_at=current_time,
    )


    # =====================================
    # RESPONSE
    # =====================================

    return {
        "message": "สมัครสมาชิกสำเร็จ",
        "user": {
            "user_id": user_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "role": role,
            "status": account_status,
            "created_at": current_time,
        }
    }

# =====================================
# ฟังก์ชันสำหรับสมัครสมาชิกผู้ใช้ใหม่ด้วย Google OAuth
@registration_guard
def register_google_user(
    google_profile: dict,
    _write_guard=None,
) -> dict:

    google_sub = str(
        google_profile["google_sub"]
    ).strip()


    email = str(
        google_profile["email"]
    ).strip().lower()


    full_name = str(
        google_profile["full_name"]
    ).strip()


    # =====================================
    # GOOGLE ACCOUNT ALREADY EXISTS
    # =====================================

    existing_google_user = (
        find_user_by_google_sub(
            google_sub
        )
    )


    if existing_google_user:

        raise GoogleAccountAlreadyExistsError()


    # =====================================
    # EMAIL ALREADY USED BY LOCAL ACCOUNT
    # =====================================

    existing_email_user = (
        find_user_by_email(
            email
        )
    )


    if existing_email_user:

        raise LocalAccountEmailExistsError()


    # =====================================
    # CREATE USER
    # =====================================

    user_id = str(
        uuid4()
    )


    role = "user"
    account_status = "active"


    current_time = datetime.now(
        THAILAND_TIMEZONE
    ).isoformat(
        timespec="seconds"
    )


    _write_guard()
    create_user(

        user_id=
            user_id,

        full_name=
            full_name,

        email=
            email,

        # Google ไม่ให้ phone
        phone=
            "",

        # Google account ไม่มี
        # local password
        password_hash=
            "",  # nosec B106 # Verified OAuth subject; local login rejects empty hashes.

        auth_provider=
            "google",

        google_sub=
            google_sub,

        role=
            role,

        status=
            account_status,

        created_at=
            current_time,

        updated_at=
            current_time,
    )

    update_last_login_at(
        user_id=user_id,
        last_login_at=current_time,
    )

    # =====================================
    # CREATE POWERTRACK SESSION
    # =====================================

    session_id = create_session(
        user_id=user_id,
        role=role,
    )


    # =====================================
    # CREATE POWERTRACK JWT
    # =====================================

    access_token = create_access_token(
        user_id=user_id,
        role=role,
        session_id=session_id,
    )


    return {

        "access_token":
            access_token,

        "user": {

            "user_id":
                user_id,

            "full_name":
                full_name,

            "email":
                email,

            "phone":
                "",

            "role":
                role,

            "status":
                account_status,
        }
    }

# =====================================
# ฟังก์ชันสำหรับเข้าสู่ระบบผู้ใช้
def login_user(
    user: dict | None,
    password: str,
) -> dict:

    # =====================================
    # USER EXISTS?
    # =====================================

    if not user:
        raise InvalidCredentialsError()

    # =====================================
    # VERIFY PASSWORD
    # =====================================

    password_hash = str(
        user.get(
            "password_hash",
            ""
        )
    )

    if not password_hash:
        raise InvalidCredentialsError()


    try:

        password_is_valid = verify_password(
            password,
            password_hash,
        )

    except Exception:

        raise InvalidCredentialsError()


    if not password_is_valid:
        raise InvalidCredentialsError()


    # =====================================
    # CHECK STATUS
    # =====================================

    status_value = str(
        user.get(
            "status",
            ""
        )
    ).strip().lower()


    if status_value != "active":
        raise UserInactiveError()


    # =====================================
    # READ ROLE
    # =====================================

    role = str(
        user.get(
            "role",
            ""
        )
    ).strip().lower()


    if role not in {
        "user",
        "admin",
    }:
        raise UserInactiveError()


    # =====================================
    # USER ID
    # =====================================

    user_id = str(
        user.get(
            "user_id",
            ""
        )
    )


    if not user_id:
        raise InvalidCredentialsError()

    current_time = datetime.now(
        THAILAND_TIMEZONE
    ).isoformat(
        timespec="seconds"
    )


    update_last_login_at(
        user_id=user_id,
        last_login_at=current_time,
    )

    # =====================================
    # CREATE REDIS SESSION
    # =====================================

    session_id = create_session(
        user_id=user_id,
        role=role,
    )


    # =====================================
    # CREATE JWT ACCESS TOKEN
    # =====================================

    access_token = create_access_token(
        user_id=user_id,
        role=role,
        session_id=session_id,
    )


    # =====================================
    # RESPONSE
    # =====================================

    return {

        "message":
            "เข้าสู่ระบบสำเร็จ",

        "access_token":
            access_token,

        "token_type":
            "bearer",  # nosec B105 # Public protocol scheme, not a credential.

        "user": {

            "user_id":
                user_id,

            "full_name":
                str(
                    user.get(
                        "full_name",
                        ""
                    )
                ),

            "email":
                str(
                    user.get(
                        "email",
                        ""
                    )
                ),

            "phone":
                str(
                    user.get(
                        "phone",
                        ""
                    )
                ),

            "role":
                role,

            "status":
                status_value,
        }
    }

# ==========================================
# GOOGLE LOGIN
# ==========================================

def login_google_user(
    google_profile: dict,
) -> dict:

    google_sub = str(
        google_profile.get(
            "google_sub",
            ""
        )
    ).strip()


    if not google_sub:

        raise GoogleAccountNotFoundError()


    # =====================================
    # FIND GOOGLE ACCOUNT
    # =====================================

    user = find_user_by_google_sub(
        google_sub
    )


    if not user:

        raise GoogleAccountNotFoundError()


    # =====================================
    # CHECK AUTH PROVIDER
    # =====================================

    auth_provider = str(
        user.get(
            "auth_provider",
            ""
        )
    ).strip().lower()


    if auth_provider != "google":

        raise GoogleAccountNotFoundError()


    # =====================================
    # CHECK STATUS
    # =====================================

    status_value = str(
        user.get(
            "status",
            ""
        )
    ).strip().lower()


    if status_value != "active":

        raise UserInactiveError()


    # =====================================
    # CHECK ROLE
    # =====================================

    role = str(
        user.get(
            "role",
            ""
        )
    ).strip().lower()


    if role not in {
        "user",
        "admin",
    }:

        raise UserInactiveError()


    # =====================================
    # USER ID
    # =====================================

    user_id = str(
        user.get(
            "user_id",
            ""
        )
    ).strip()


    if not user_id:

        raise GoogleAccountNotFoundError()


    # =====================================
    # UPDATE LAST LOGIN
    # =====================================

    current_time = datetime.now(
        THAILAND_TIMEZONE
    ).isoformat(
        timespec="seconds"
    )


    update_last_login_at(
        user_id=user_id,
        last_login_at=current_time,
    )


    # =====================================
    # CREATE REDIS SESSION
    # =====================================

    session_id = create_session(
        user_id=user_id,
        role=role,
    )


    # =====================================
    # CREATE POWERTRACK JWT
    # =====================================

    access_token = create_access_token(
        user_id=user_id,
        role=role,
        session_id=session_id,
    )


    # =====================================
    # RESPONSE FOR ROUTE
    # =====================================

    return {

        "access_token":
            access_token,

        "user": {

            "user_id":
                user_id,

            "full_name":
                str(
                    user.get(
                        "full_name",
                        ""
                    )
                ),

            "email":
                str(
                    user.get(
                        "email",
                        ""
                    )
                ),

            "phone":
                str(
                    user.get(
                        "phone",
                        ""
                    )
                ),

            "role":
                role,

            "status":
                status_value,
        }
    }
