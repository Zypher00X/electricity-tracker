from fastapi import (
    Cookie,
    HTTPException,
    status,
    Depends,
)

from app.core.config import (
    AUTH_COOKIE_NAME,
)

from app.core.jwt import (
    AccessTokenExpiredError,
    AccessTokenInvalidError,
    decode_access_token,
)

from app.services.session_service import (
    delete_session,
    get_session,
)

from app.services.auth_user_cache import (
    find_user_by_id,
)


# ==========================================
# AUTH ERROR
# ==========================================

def authentication_error():

    return HTTPException(
        status_code=
            status.HTTP_401_UNAUTHORIZED,

        detail=
            "กรุณาเข้าสู่ระบบ",

        headers={
            "WWW-Authenticate":
                "Bearer"
        },
    )


# ==========================================
# GET CURRENT USER
# ==========================================

def get_current_user(

    access_token: str | None = Cookie(
        default=None,
        alias=AUTH_COOKIE_NAME,
    ),

) -> dict:

    # ======================================
    # COOKIE EXISTS?
    # ======================================

    if not access_token:

        raise authentication_error()


    # ======================================
    # VERIFY JWT
    # ======================================

    try:

        payload = decode_access_token(
            access_token
        )


    except AccessTokenExpiredError:

        raise HTTPException(
            status_code=
                status.HTTP_401_UNAUTHORIZED,

            detail=
                "Session หมดอายุ กรุณาเข้าสู่ระบบใหม่",
        )


    except AccessTokenInvalidError:

        raise authentication_error()


    # ======================================
    # READ JWT CLAIMS
    # ======================================

    user_id = str(
        payload.get(
            "sub",
            ""
        )
    ).strip()


    session_id = str(
        payload.get(
            "sid",
            ""
        )
    ).strip()


    token_role = str(
        payload.get(
            "role",
            ""
        )
    ).strip().lower()


    if (
        not user_id
        or not session_id
        or token_role
        not in {
            "user",
            "admin",
        }
    ):

        raise authentication_error()


    # ======================================
    # READ REDIS SESSION
    # ======================================

    session = get_session(
        session_id
    )


    if not session:

        # Session อาจหมดอายุ
        # หรือถูก revoke/logout ไปแล้ว
        raise authentication_error()


    # ======================================
    # VERIFY SESSION USER
    # ======================================

    session_user_id = str(
        session.get(
            "user_id",
            ""
        )
    ).strip()


    session_role = str(
        session.get(
            "role",
            ""
        )
    ).strip().lower()


    if session_user_id != user_id:

        delete_session(
            session_id
        )

        raise authentication_error()


    # ======================================
    # VERIFY SESSION ROLE
    # ======================================

    if session_role != token_role:

        delete_session(
            session_id
        )

        raise authentication_error()


    # ======================================
    # GET CURRENT USER FROM DATABASE
    # ======================================

    user = find_user_by_id(
        user_id
    )


    if not user:

        delete_session(
            session_id
        )

        raise authentication_error()


    # ======================================
    # CURRENT ACCOUNT STATUS
    # ======================================

    current_status = str(
        user.get(
            "status",
            ""
        )
    ).strip().lower()


    if current_status != "active":

        delete_session(
            session_id
        )

        raise HTTPException(
            status_code=
                status.HTTP_403_FORBIDDEN,

            detail=
                "บัญชีผู้ใช้นี้ไม่สามารถใช้งานได้",
        )


    # ======================================
    # CURRENT DATABASE ROLE
    # ======================================

    current_role = str(
        user.get(
            "role",
            ""
        )
    ).strip().lower()


    if current_role not in {
        "user",
        "admin",
    }:

        delete_session(
            session_id
        )

        raise authentication_error()


    # ======================================
    # VERIFY ROLE CONSISTENCY
    # ======================================

    if (
        current_role != token_role
        or current_role != session_role
    ):

        # Role ในฐานข้อมูลถูกเปลี่ยน
        # JWT และ Redis Session เก่าจะถูกยกเลิก
        # แล้วบังคับให้ Login ใหม่

        delete_session(
            session_id
        )

        raise HTTPException(
            status_code=
                status.HTTP_401_UNAUTHORIZED,

            detail=
                "สิทธิ์ผู้ใช้มีการเปลี่ยนแปลง กรุณาเข้าสู่ระบบใหม่",
        )


    # ======================================
    # SAFE CURRENT USER
    # ======================================

    return {

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
            current_role,

        "status":
            current_status,

        # ใช้ภายใน Backend ภายหลัง
        "_session_id":
            session_id,
    }


# ==========================================
# REQUIRE USER ROLE
# ==========================================

def require_user(
    current_user: dict = Depends(
        get_current_user
    ),
) -> dict:

    if current_user.get("role") != "user":

        raise HTTPException(
            status_code=
                status.HTTP_403_FORBIDDEN,

            detail=
                "คุณไม่มีสิทธิ์เข้าถึงส่วนผู้ใช้งาน",
        )

    return current_user


# ==========================================
# REQUIRE ADMIN ROLE
# ==========================================

def require_admin(
    current_user: dict = Depends(
        get_current_user
    ),
) -> dict:

    if current_user.get("role") != "admin":

        raise HTTPException(
            status_code=
                status.HTTP_403_FORBIDDEN,

            detail=
                "คุณไม่มีสิทธิ์เข้าถึงส่วนผู้ดูแลระบบ",
        )

    return current_user


# ==========================================
# GET CURRENT USER FOR PAGE
#
# ใช้กับ HTML Page Routes
# ถ้า Authentication ไม่ผ่าน
# จะคืน None แทนการตอบ JSON 401
# ==========================================

def get_current_user_for_page(
    access_token: str | None = Cookie(
        default=None,
        alias=AUTH_COOKIE_NAME,
    ),
) -> dict | None:

    if not access_token:
        return None

    try:

        # ==================================
        # VERIFY JWT
        # ==================================

        payload = decode_access_token(
            access_token
        )


        user_id = str(
            payload.get(
                "sub",
                ""
            )
        ).strip()


        session_id = str(
            payload.get(
                "sid",
                ""
            )
        ).strip()


        token_role = str(
            payload.get(
                "role",
                ""
            )
        ).strip().lower()


        if (
            not user_id
            or not session_id
            or token_role not in {
                "user",
                "admin",
            }
        ):
            return None


        # ==================================
        # CHECK REDIS SESSION
        # ==================================

        session = get_session(
            session_id
        )


        if not session:
            return None


        session_user_id = str(
            session.get(
                "user_id",
                ""
            )
        ).strip()


        session_role = str(
            session.get(
                "role",
                ""
            )
        ).strip().lower()


        if (
            session_user_id != user_id
            or session_role != token_role
        ):

            delete_session(
                session_id
            )

            return None


        # ==================================
        # CHECK CURRENT USER
        # ==================================

        user = find_user_by_id(
            user_id
        )


        if not user:

            delete_session(
                session_id
            )

            return None


        current_status = str(
            user.get(
                "status",
                ""
            )
        ).strip().lower()


        current_role = str(
            user.get(
                "role",
                ""
            )
        ).strip().lower()


        if current_status != "active":

            delete_session(
                session_id
            )

            return None


        if current_role not in {
            "user",
            "admin",
        }:

            delete_session(
                session_id
            )

            return None


        # ==================================
        # ROLE CHANGED
        # ==================================

        if (
            current_role != token_role
            or current_role != session_role
        ):

            delete_session(
                session_id
            )

            return None


        # ==================================
        # AUTHENTICATED
        # ==================================

        return {
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
                current_role,

            "status":
                current_status,

            "_session_id":
                session_id,
        }


    except (
        AccessTokenExpiredError,
        AccessTokenInvalidError,
    ):

        return None
