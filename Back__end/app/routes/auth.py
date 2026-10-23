import logging
import hmac

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)

from fastapi.responses import (
    RedirectResponse,
)

from app.schemas.auth import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
)

from app.services.auth_service import (
    EmailAlreadyExistsError,
    PhoneAlreadyExistsError,
    InvalidCredentialsError,
    GoogleAccountAlreadyExistsError,
    GoogleAccountNotFoundError,
    LocalAccountEmailExistsError,
    UserInactiveError,
    register_google_user,
    login_google_user,
    register_user,
    login_user,
)

from app.core.config import (
    AUTH_COOKIE_NAME,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

from app.dependencies.auth import (
    get_current_user,
)

from app.core.jwt import (
    AccessTokenExpiredError,
    AccessTokenInvalidError,
    decode_access_token,
)

from app.services.session_service import (
    delete_session,
)

from app.services.rate_limit_service import (
    RateLimitExceededError,
    RateLimitBackendError,
    consume_login_ip_limit,
    consume_login_failure_limit,
    reset_login_failure_limit,
    consume_register_limit,
    normalize_identifier,
)

from app.repositories.user_repository import (
    find_user_by_identifier,
)

from app.services.google_oauth_service import (
    consume_google_oauth_state,
    exchange_google_code,
    get_google_authorization_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    request: Request,
):

    try:

        # =================================
        # CLIENT IP
        # =================================

        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )


        # =================================
        # RATE LIMIT
        # =================================

        consume_register_limit(
            client_ip
        )


        # =================================
        # REGISTER USER
        # =================================

        result = register_user(
            data
        )

        return result


    except RateLimitExceededError as error:

        raise HTTPException(
            status_code=
                status.HTTP_429_TOO_MANY_REQUESTS,

            detail=
                "มีการสมัครสมาชิกบ่อยเกินไป กรุณาลองใหม่ภายหลัง",

            headers={
                "Retry-After":
                    str(
                        error.retry_after
                    )
            },
        )


    except RateLimitBackendError:

        raise HTTPException(
            status_code=
                status.HTTP_503_SERVICE_UNAVAILABLE,

            detail=
                "ระบบรักษาความปลอดภัยไม่พร้อมใช้งานชั่วคราว",
        )


    except EmailAlreadyExistsError:

        raise HTTPException(
            status_code=
                status.HTTP_409_CONFLICT,

            detail=
                "อีเมลนี้ถูกใช้งานแล้ว",
        )


    except PhoneAlreadyExistsError:

        raise HTTPException(
            status_code=
                status.HTTP_409_CONFLICT,

            detail=
                "เบอร์โทรศัพท์นี้ถูกใช้งานแล้ว",
        )


    except Exception as error:

        logger.warning('Authentication operation failed: %s', type(error).__name__)

        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                "ไม่สามารถสมัครสมาชิกได้",
        )


# =========================================
# LOGIN
# =========================================

@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    data: LoginRequest,
    request: Request,
    response: Response,
):

    try:

        # =================================
        # CLIENT IP
        # =================================

        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )


        # =================================
        # GLOBAL IP RATE LIMIT
        # =================================

        consume_login_ip_limit(
            client_ip
        )


        # =================================
        # FIND USER
        # =================================

        login_user_record = (
            find_user_by_identifier(
                data.identifier
            )
        )


        # =================================
        # RATE LIMIT SUBJECT
        # =================================

        if login_user_record:

            user_id = str(
                login_user_record.get(
                    "user_id",
                    ""
                )
            ).strip()

            rate_limit_subject = (
                f"user:{user_id}"
            )

        else:

            normalized_identifier = (
                normalize_identifier(
                    data.identifier
                )
            )

            rate_limit_subject = (
                "unknown:"
                f"{normalized_identifier}"
            )


        # =================================
        # ACCOUNT LOGIN RATE LIMIT
        # =================================

        consume_login_failure_limit(
            client_ip,
            rate_limit_subject,
        )


        # =================================
        # LOGIN
        # =================================

        result = login_user(
            user=login_user_record,
            password=data.password,
        )


        # =================================
        # SUCCESS → RESET FAILURE COUNTER
        # =================================

        reset_login_failure_limit(
            client_ip,
            rate_limit_subject,
        )


        # =================================
        # JWT
        # =================================

        access_token = result.get(
            "access_token"
        )


        if not access_token:

            raise HTTPException(
                status_code=
                    status.HTTP_500_INTERNAL_SERVER_ERROR,

                detail=
                    "ไม่สามารถสร้าง Authentication Token ได้",
            )


        # =================================
        # HTTPONLY COOKIE
        # =================================

        response.set_cookie(

            key=
                AUTH_COOKIE_NAME,

            value=
                access_token,

            httponly=True,

            secure=
                COOKIE_SECURE,

            samesite=
                COOKIE_SAMESITE,

            path="/",

            max_age=
                ACCESS_TOKEN_EXPIRE_MINUTES
                * 60,
        )


        # =================================
        # RESPONSE
        # =================================

        return {

            "message":
                result["message"],

            "user":
                result["user"],
        }


    except RateLimitExceededError as error:

        raise HTTPException(
            status_code=
                status.HTTP_429_TOO_MANY_REQUESTS,

            detail=
                "มีการพยายามเข้าสู่ระบบบ่อยเกินไป กรุณาลองใหม่ภายหลัง",

            headers={
                "Retry-After":
                    str(
                        error.retry_after
                    )
            },
        )


    except RateLimitBackendError:

        raise HTTPException(
            status_code=
                status.HTTP_503_SERVICE_UNAVAILABLE,

            detail=
                "ระบบรักษาความปลอดภัยไม่พร้อมใช้งานชั่วคราว",
        )


    except InvalidCredentialsError:

        raise HTTPException(
            status_code=
                status.HTTP_401_UNAUTHORIZED,

            detail=
                "อีเมล/เบอร์โทรศัพท์หรือรหัสผ่านไม่ถูกต้อง",
        )


    except UserInactiveError:

        raise HTTPException(
            status_code=
                status.HTTP_403_FORBIDDEN,

            detail=
                "บัญชีผู้ใช้นี้ไม่สามารถใช้งานได้",
        )


    except HTTPException:

        raise


    except Exception as error:

        logger.warning('Authentication operation failed: %s', type(error).__name__)

        raise HTTPException(
            status_code=
                status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail=
                "ไม่สามารถเข้าสู่ระบบได้",
        )

# =========================================
# CURRENT USER
# =========================================

@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
)
def get_me(

    current_user: dict = Depends(
        get_current_user
    ),

):

    return {
        "user": {
            "user_id":
                current_user["user_id"],

            "full_name":
                current_user["full_name"],

            "email":
                current_user["email"],

            "phone":
                current_user["phone"],

            "role":
                current_user["role"],

            "status":
                current_user["status"],
        }
    }


# =========================================
# LOGOUT
# =========================================

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
def logout(
    response: Response,

    access_token: str | None = Cookie(
        default=None,
        alias=AUTH_COOKIE_NAME,
    ),
):

    # =====================================
    # REVOKE REDIS SESSION
    # =====================================

    if access_token:

        try:

            payload = decode_access_token(
                access_token
            )

            session_id = str(
                payload.get(
                    "sid",
                    ""
                )
            ).strip()

            if session_id:

                delete_session(
                    session_id
                )

        except (
            AccessTokenExpiredError,
            AccessTokenInvalidError,
        ):

            # Token หมดอายุหรือเสียแล้ว
            # ยังต้องลบ Cookie ให้ผู้ใช้ได้ Logout
            pass


    # =====================================
    # DELETE AUTH COOKIE
    # =====================================

    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )


    return {
        "message": "ออกจากระบบสำเร็จ"
    }

# =========================================
# GOOGLE OAUTH START
# =========================================

@router.get(
    "/google/start",
)
def google_oauth_start(
    mode: str = Query(
        pattern="^(register|login)$"
    ),
):

    authorization_url, state = (
        get_google_authorization_url(
            mode
        )
    )


    response = RedirectResponse(
        url=authorization_url,
        status_code=302,
    )


    # Cookie นี้ใช้ bind OAuth state
    # กับ Browser ที่เริ่ม flow
    response.set_cookie(

        key=
            "powertrack_google_oauth_state",

        value=
            state,

        httponly=
            True,

        secure=
            COOKIE_SECURE,

        samesite=
            "lax",

        max_age=
            300,

        path=
            "/api/auth/google",
    )


    return response

# =========================================
# GOOGLE OAUTH CALLBACK
# =========================================

@router.get(
    "/google/callback",
)
def google_oauth_callback(

    code: str,

    state: str,

    google_state_cookie: str | None = Cookie(
        default=None,
        alias="powertrack_google_oauth_state",
    ),
):

    # =====================================
    # VERIFY STATE COOKIE
    # =====================================

    if (
        not google_state_cookie
        or not hmac.compare_digest(
            state,
            google_state_cookie,
        )
    ):

        return RedirectResponse(
            url="/register?error=google_state",
            status_code=302,
        )


    # =====================================
    # VERIFY ONE-TIME REDIS STATE
    # =====================================

    oauth_state = consume_google_oauth_state(
        state
    )


    if not oauth_state:

        return RedirectResponse(
            url="/register?error=google_state",
            status_code=302,
        )


    mode = oauth_state[
        "mode"
    ]


    code_verifier = oauth_state[
        "code_verifier"
    ]


    try:

        google_profile = (
            exchange_google_code(
                code=code,
                state=state,
                code_verifier=code_verifier,
            )
        )


        # =========================================
        # REGISTER MODE
        # =========================================

        if mode == "register":

            result = register_google_user(
                google_profile
            )


        # =========================================
        # LOGIN MODE
        # =========================================

        elif mode == "login":

            result = login_google_user(
                google_profile
            )


        else:

            return RedirectResponse(
                url="/login?error=google_oauth",
                status_code=302,
            )


    except GoogleAccountAlreadyExistsError:

        return RedirectResponse(
            url="/login?error=google_account_exists",
            status_code=302,
        )


    except LocalAccountEmailExistsError:

        return RedirectResponse(
            url="/register?error=email_exists",
            status_code=302,
        )


    except GoogleAccountNotFoundError:

        return RedirectResponse(
            url="/login?error=google_account_not_found",
            status_code=302,
        )


    except UserInactiveError:

        return RedirectResponse(
            url="/login?error=account_inactive",
            status_code=302,
        )


    except Exception as error:

        logger.warning('Authentication operation failed: %s', type(error).__name__)

        return RedirectResponse(
            url="/login?error=google_oauth",
            status_code=302,
        )


    # =====================================
    # POWERTRACK AUTH COOKIE
    # =====================================

    user_role = result[
        "user"
    ][
        "role"
    ]


    if user_role == "admin":

        redirect_url = (
            "/admin/dashboard"
        )

    else:

        redirect_url = (
            "/dashboard"
        )


    response = RedirectResponse(
        url=redirect_url,
        status_code=302,
    )


    response.set_cookie(

        key=
            AUTH_COOKIE_NAME,

        value=
            result["access_token"],

        httponly=
            True,

        secure=
            COOKIE_SECURE,

        samesite=
            COOKIE_SAMESITE,

        path=
            "/",

        max_age=
            ACCESS_TOKEN_EXPIRE_MINUTES
            * 60,
    )


    # OAuth state cookie ใช้เสร็จแล้ว
    response.delete_cookie(
        key=
            "powertrack_google_oauth_state",

        path=
            "/api/auth/google",
    )


    return response