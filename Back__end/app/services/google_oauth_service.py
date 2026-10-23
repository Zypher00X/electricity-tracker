import secrets
import json

from google_auth_oauthlib.flow import Flow

from google.oauth2 import id_token

from google.auth.transport.requests import (
    Request as GoogleRequest,
)

from app.core.config import (
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    GOOGLE_OAUTH_STATE_EXPIRE_SECONDS,
)

from app.core.redis import (
    redis_client,
)


# ==========================================
# GOOGLE OAUTH CONFIG
# ==========================================

GOOGLE_AUTH_URI = (
    "https://accounts.google.com/o/oauth2/auth"
)

GOOGLE_TOKEN_URI = (  # nosec B105 # Public Google HTTPS token endpoint.
    "https://oauth2.googleapis.com/token"
)


GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


# ==========================================
# OAUTH STATE
# ==========================================

GOOGLE_STATE_PREFIX = (
    "powertrack:oauth:google:state:"
)


def create_google_oauth_state(
    mode: str,
) -> tuple[str, str]:

    if mode not in {
        "register",
        "login",
    }:
        raise ValueError(
            "Invalid Google OAuth mode"
        )


    # OAuth state
    state = secrets.token_urlsafe(
        32
    )


    # PKCE code verifier
    #
    # token_urlsafe(64) จะได้ string
    # ความยาวประมาณ 86 chars
    # อยู่ในช่วง 43-128 chars
    code_verifier = secrets.token_urlsafe(
        64
    )


    oauth_data = {
        "mode": mode,
        "code_verifier": code_verifier,
    }


    redis_client.setex(
        f"{GOOGLE_STATE_PREFIX}{state}",
        GOOGLE_OAUTH_STATE_EXPIRE_SECONDS,
        json.dumps(
            oauth_data
        ),
    )


    return (
        state,
        code_verifier,
    )


def consume_google_oauth_state(
    state: str,
) -> dict | None:

    if not state:
        return None


    key = (
        f"{GOOGLE_STATE_PREFIX}{state}"
    )


    data_json = redis_client.getdel(
        key
    )


    if not data_json:
        return None


    try:

        data = json.loads(
            data_json
        )

    except json.JSONDecodeError:

        return None


    mode = data.get(
        "mode"
    )

    code_verifier = data.get(
        "code_verifier"
    )


    if mode not in {
        "register",
        "login",
    }:
        return None


    if not code_verifier:
        return None


    return {
        "mode": mode,
        "code_verifier": code_verifier,
    }


# ==========================================
# OAUTH FLOW
# ==========================================

def create_google_flow(
    state: str | None = None,
    code_verifier: str | None = None,
) -> Flow:

    client_config = {

        "web": {

            "client_id":
                GOOGLE_OAUTH_CLIENT_ID,

            "client_secret":
                GOOGLE_OAUTH_CLIENT_SECRET,

            "auth_uri":
                GOOGLE_AUTH_URI,

            "token_uri":
                GOOGLE_TOKEN_URI,

            "redirect_uris": [
                GOOGLE_OAUTH_REDIRECT_URI
            ],
        }
    }


    flow = Flow.from_client_config(
        client_config,

        scopes=
            GOOGLE_SCOPES,

        state=
            state,

        code_verifier=
            code_verifier,

        # เราจัดการ verifier เอง
        autogenerate_code_verifier=
            False,
    )


    flow.redirect_uri = (
        GOOGLE_OAUTH_REDIRECT_URI
    )


    return flow


# ==========================================
# CREATE GOOGLE AUTH URL
# ==========================================

def get_google_authorization_url(
    mode: str,
) -> tuple[str, str]:

    state, code_verifier = (
        create_google_oauth_state(
            mode
        )
    )


    flow = create_google_flow(
        state=state,
        code_verifier=code_verifier,
    )


    authorization_url, _ = (
        flow.authorization_url(

            access_type="online",

            include_granted_scopes="true",

            prompt="select_account",

            state=state,
        )
    )


    return (
        authorization_url,
        state,
    )


# ==========================================
# EXCHANGE AUTHORIZATION CODE
# ==========================================

def exchange_google_code(
    code: str,
    state: str,
    code_verifier: str,
) -> dict:

    flow = create_google_flow(
        state=state,
        code_verifier=code_verifier,
    )


    flow.fetch_token(
        code=code
    )


    google_id_token = (
        flow.credentials.id_token
    )


    if not google_id_token:

        raise ValueError(
            "Google ID token is missing"
        )


    # ======================================
    # VERIFY GOOGLE ID TOKEN
    # ======================================

    profile = (
        id_token.verify_oauth2_token(
            google_id_token,

            GoogleRequest(),

            GOOGLE_OAUTH_CLIENT_ID,
        )
    )


    google_sub = str(
        profile.get(
            "sub",
            ""
        )
    ).strip()


    email = str(
        profile.get(
            "email",
            ""
        )
    ).strip().lower()


    full_name = str(
        profile.get(
            "name",
            ""
        )
    ).strip()


    email_verified = bool(
        profile.get(
            "email_verified",
            False,
        )
    )


    if not google_sub:

        raise ValueError(
            "Google sub is missing"
        )


    if not email:

        raise ValueError(
            "Google email is missing"
        )


    if not email_verified:

        raise ValueError(
            "Google email is not verified"
        )


    return {

        "google_sub":
            google_sub,

        "email":
            email,

        "full_name":
            full_name or email,

        "picture":
            str(
                profile.get(
                    "picture",
                    ""
                )
            ),
    }