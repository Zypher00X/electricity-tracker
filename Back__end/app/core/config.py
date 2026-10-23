import os


# ==========================================
# JWT CONFIGURATION
# ==========================================

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY"
)

JWT_ALGORITHM = os.getenv(
    "JWT_ALGORITHM",
    "HS256",
)

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "15",
    )
)

JWT_ISSUER = os.getenv(
    "JWT_ISSUER",
    "powertrack",
)

JWT_AUDIENCE = os.getenv(
    "JWT_AUDIENCE",
    "powertrack-web",
)


# ==========================================
# SECURITY CHECK
# ==========================================

if not JWT_SECRET_KEY:

    raise RuntimeError(
        "JWT_SECRET_KEY is not configured"
    )


if len(JWT_SECRET_KEY) < 64:

    raise RuntimeError(
        "JWT_SECRET_KEY is too short"
    )

# ==========================================
# REDIS CONFIGURATION
# ==========================================

REDIS_HOST = os.getenv(
    "REDIS_HOST",
    "redis",
)

REDIS_PORT = int(
    os.getenv(
        "REDIS_PORT",
        "6379",
    )
)

REDIS_DB = int(
    os.getenv(
        "REDIS_DB",
        "0",
    )
)

REDIS_PASSWORD = os.getenv(
    "REDIS_PASSWORD"
)


REDIS_URL = os.getenv("REDIS_URL", "").strip()
if REDIS_URL:
    from urllib.parse import urlsplit
    try:
        parsed_redis = urlsplit(REDIS_URL)
        valid_redis_url = (parsed_redis.scheme in {"redis", "rediss"} and
                           bool(parsed_redis.hostname) and not parsed_redis.fragment and
                           parsed_redis.port != 0)
        has_password = bool(parsed_redis.password)
    except ValueError:
        valid_redis_url = False
        has_password = False
    if not valid_redis_url:
        raise RuntimeError("REDIS_URL must be a valid redis:// or rediss:// URL")
    if not has_password and os.getenv("REDIS_ALLOW_PASSWORDLESS_PRIVATE", "false").lower() != "true":
        raise RuntimeError("Passwordless Redis requires explicit private-network opt-in")

if not REDIS_URL and not REDIS_PASSWORD:

    raise RuntimeError(
        "REDIS_PASSWORD is not configured"
    )


# ==========================================
# SESSION CONFIGURATION
# ==========================================

SESSION_EXPIRE_SECONDS = int(
    os.getenv(
        "SESSION_EXPIRE_SECONDS",
        "1800",
    )
)

# ==========================================
# AUTH COOKIE CONFIGURATION
# ==========================================

AUTH_COOKIE_NAME = os.getenv(
    "AUTH_COOKIE_NAME",
    "powertrack_access_token",
)


COOKIE_SECURE = (
    os.getenv(
        "COOKIE_SECURE",
        "false",
    ).strip().lower()
    == "true"
)


COOKIE_SAMESITE = os.getenv(
    "COOKIE_SAMESITE",
    "lax",
).strip().lower()


if COOKIE_SAMESITE not in {
    "lax",
    "strict",
    "none",
}:

    raise RuntimeError(
        "COOKIE_SAMESITE must be lax, strict or none"
    )


# SameSite=None ต้องใช้ Secure Cookie
if (
    COOKIE_SAMESITE == "none"
    and not COOKIE_SECURE
):

    raise RuntimeError(
        "SameSite=None requires COOKIE_SECURE=true"
    )

# ==========================================
# RATE LIMIT CONFIGURATION
# ==========================================

LOGIN_IP_RATE_LIMIT = int(
    os.getenv(
        "LOGIN_IP_RATE_LIMIT",
        "30",
    )
)

LOGIN_IP_RATE_WINDOW_SECONDS = int(
    os.getenv(
        "LOGIN_IP_RATE_WINDOW_SECONDS",
        "60",
    )
)


LOGIN_FAILURE_RATE_LIMIT = int(
    os.getenv(
        "LOGIN_FAILURE_RATE_LIMIT",
        "5",
    )
)

LOGIN_FAILURE_RATE_WINDOW_SECONDS = int(
    os.getenv(
        "LOGIN_FAILURE_RATE_WINDOW_SECONDS",
        "900",
    )
)


REGISTER_RATE_LIMIT = int(
    os.getenv(
        "REGISTER_RATE_LIMIT",
        "5",
    )
)

REGISTER_RATE_WINDOW_SECONDS = int(
    os.getenv(
        "REGISTER_RATE_WINDOW_SECONDS",
        "3600",
    )
)

# ==========================================
# GOOGLE OAUTH
# ==========================================

GOOGLE_OAUTH_CLIENT_ID = os.getenv(
    "GOOGLE_OAUTH_CLIENT_ID"
)

GOOGLE_OAUTH_CLIENT_SECRET = os.getenv(
    "GOOGLE_OAUTH_CLIENT_SECRET"
)

GOOGLE_OAUTH_REDIRECT_URI = os.getenv(
    "GOOGLE_OAUTH_REDIRECT_URI",
    "http://localhost:8000/api/auth/google/callback",
)

GOOGLE_OAUTH_STATE_EXPIRE_SECONDS = int(
    os.getenv(
        "GOOGLE_OAUTH_STATE_EXPIRE_SECONDS",
        "300",
    )
)


if not GOOGLE_OAUTH_CLIENT_ID:

    raise RuntimeError(
        "GOOGLE_OAUTH_CLIENT_ID is not configured"
    )


if not GOOGLE_OAUTH_CLIENT_SECRET:

    raise RuntimeError(
        "GOOGLE_OAUTH_CLIENT_SECRET is not configured"
    )
