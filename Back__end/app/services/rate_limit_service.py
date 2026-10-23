import hashlib
import re

from redis.exceptions import RedisError

from app.core.redis import (
    redis_client,
)

from app.core.config import (
    LOGIN_IP_RATE_LIMIT,
    LOGIN_IP_RATE_WINDOW_SECONDS,
    LOGIN_FAILURE_RATE_LIMIT,
    LOGIN_FAILURE_RATE_WINDOW_SECONDS,
    REGISTER_RATE_LIMIT,
    REGISTER_RATE_WINDOW_SECONDS,
)


# ==========================================
# EXCEPTIONS
# ==========================================

class RateLimitExceededError(Exception):

    def __init__(
        self,
        retry_after: int,
    ):

        self.retry_after = retry_after

        super().__init__(
            "Rate limit exceeded"
        )


class RateLimitBackendError(Exception):
    pass


# ==========================================
# REDIS LUA SCRIPT
#
# INCR + EXPIRE ต้องเกิดแบบ Atomic
# ==========================================

RATE_LIMIT_SCRIPT = """
local current = redis.call(
    "INCR",
    KEYS[1]
)

if current == 1 then

    redis.call(
        "EXPIRE",
        KEYS[1],
        ARGV[1]
    )

end

local ttl = redis.call(
    "TTL",
    KEYS[1]
)

return {
    current,
    ttl
}
"""


# ==========================================
# HASH KEY COMPONENT
# ==========================================

def hash_value(
    value: str,
) -> str:

    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


# ==========================================
# NORMALIZE LOGIN IDENTIFIER
# ==========================================

def normalize_identifier(
    identifier: str,
) -> str:

    value = identifier.strip()

    # Email
    if "@" in value:

        return value.lower()

    # Phone
    phone = re.sub(
        r"\D",
        "",
        value,
    )

    return phone


# ==========================================
# GENERIC RATE LIMIT CONSUMER
# ==========================================

def consume_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
) -> None:

    try:

        result = redis_client.eval(
            RATE_LIMIT_SCRIPT,
            1,
            key,
            window_seconds,
        )


        current = int(
            result[0]
        )

        ttl = int(
            result[1]
        )


    except RedisError as error:

        raise RateLimitBackendError() from error


    # ตัวอย่าง limit=5
    #
    # 1 ✅
    # 2 ✅
    # 3 ✅
    # 4 ✅
    # 5 ✅
    # 6 ❌

    if current > limit:

        raise RateLimitExceededError(
            retry_after=max(
                ttl,
                1,
            )
        )


# ==========================================
# LOGIN - IP LIMIT
# ==========================================

def consume_login_ip_limit(
    client_ip: str,
) -> None:

    hashed_ip = hash_value(
        client_ip
    )


    key = (
        "powertrack:"
        "ratelimit:"
        "login:"
        "ip:"
        f"{hashed_ip}"
    )


    consume_rate_limit(
        key=key,
        limit=LOGIN_IP_RATE_LIMIT,
        window_seconds=
            LOGIN_IP_RATE_WINDOW_SECONDS,
    )


# ==========================================
# LOGIN FAILURE KEY
# ==========================================

def get_login_failure_key(
    client_ip: str,
    subject: str,
) -> str:

    combined_value = (
        f"{client_ip}:"
        f"{subject}"
    )

    hashed_value = hash_value(
        combined_value
    )

    return (
        "powertrack:"
        "ratelimit:"
        "login:"
        "failure:"
        f"{hashed_value}"
    )


# ==========================================
# CONSUME LOGIN FAILURE LIMIT
# ==========================================

def consume_login_failure_limit(
    client_ip: str,
    subject: str,
) -> None:

    key = get_login_failure_key(
        client_ip,
        subject,
    )

    consume_rate_limit(
        key=key,
        limit=LOGIN_FAILURE_RATE_LIMIT,
        window_seconds=
            LOGIN_FAILURE_RATE_WINDOW_SECONDS,
    )


# ==========================================
# RESET LOGIN FAILURE LIMIT
# ==========================================

def reset_login_failure_limit(
    client_ip: str,
    subject: str,
) -> None:

    key = get_login_failure_key(
        client_ip,
        subject,
    )

    try:

        redis_client.delete(
            key
        )

    except RedisError as error:

        raise RateLimitBackendError() from error


# ==========================================
# REGISTER - IP LIMIT
# ==========================================

def consume_register_limit(
    client_ip: str,
) -> None:

    hashed_ip = hash_value(
        client_ip
    )


    key = (
        "powertrack:"
        "ratelimit:"
        "register:"
        "ip:"
        f"{hashed_ip}"
    )


    consume_rate_limit(
        key=key,
        limit=REGISTER_RATE_LIMIT,
        window_seconds=
            REGISTER_RATE_WINDOW_SECONDS,
    )