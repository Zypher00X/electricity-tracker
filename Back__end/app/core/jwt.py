from datetime import (
    datetime,
    timedelta,
    timezone,
)

from uuid import uuid4

import jwt

from jwt import (
    ExpiredSignatureError,
    InvalidTokenError,
)

from app.core.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ISSUER,
    JWT_AUDIENCE,
)


# ==========================================
# CUSTOM EXCEPTIONS
# ==========================================

class AccessTokenExpiredError(Exception):
    pass


class AccessTokenInvalidError(Exception):
    pass


# ==========================================
# CREATE ACCESS TOKEN
# ==========================================

def create_access_token(
    user_id: str,
    role: str,
    session_id: str,
) -> str:

    now = datetime.now(
        timezone.utc
    )

    expires_at = now + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )


    payload = {

        # Subject = User ID
        "sub": user_id,

        # Redis Session ID
        "sid": session_id,

        # RBAC Role
        "role": role,

        # Token type
        "type": "access",

        # Unique JWT ID
        "jti": str(
            uuid4()
        ),

        # Issued At
        "iat": now,

        # Not Before
        "nbf": now,

        # Expiration
        "exp": expires_at,

        # Issuer
        "iss": JWT_ISSUER,

        # Audience
        "aud": JWT_AUDIENCE,
    }


    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


    return token


# ==========================================
# DECODE / VERIFY ACCESS TOKEN
# ==========================================

def decode_access_token(
    token: str,
) -> dict:

    try:

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,

            algorithms=[
                JWT_ALGORITHM
            ],

            audience=JWT_AUDIENCE,

            issuer=JWT_ISSUER,

            options={
                "require": [
                    "sub",
                    "sid",
                    "role",
                    "type",
                    "jti",
                    "iat",
                    "nbf",
                    "exp",
                    "iss",
                    "aud",
                ]
            },
        )


    except ExpiredSignatureError:

        raise AccessTokenExpiredError()


    except InvalidTokenError:

        raise AccessTokenInvalidError()


    # ======================================
    # TOKEN TYPE
    # ======================================

    if payload.get("type") != "access":

        raise AccessTokenInvalidError()


    # ======================================
    # ROLE
    # ======================================

    role = payload.get("role")

    if role not in {
        "user",
        "admin",
    }:

        raise AccessTokenInvalidError()


    # ======================================
    # REQUIRED IDENTIFIERS
    # ======================================

    if not payload.get("sub"):
        raise AccessTokenInvalidError()

    if not payload.get("sid"):
        raise AccessTokenInvalidError()


    return payload