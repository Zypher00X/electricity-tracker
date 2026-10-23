import json

from datetime import (
    datetime,
    timezone,
)

from uuid import uuid4


from app.core.redis import (
    redis_client,
)

from app.core.config import (
    SESSION_EXPIRE_SECONDS,
)


# ==========================================
# SESSION PREFIX
# ==========================================

SESSION_PREFIX = "powertrack:session:"


# ==========================================
# SESSION KEY
# ==========================================

def get_session_key(
    session_id: str,
) -> str:

    return (
        f"{SESSION_PREFIX}"
        f"{session_id}"
    )


# ==========================================
# CREATE SESSION
# ==========================================

def create_session(
    user_id: str,
    role: str,
) -> str:

    session_id = str(
        uuid4()
    )


    session_data = {

        "user_id": user_id,

        "role": role,

        "created_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }


    session_key = get_session_key(
        session_id
    )


    redis_client.setex(
        session_key,
        SESSION_EXPIRE_SECONDS,
        json.dumps(
            session_data
        ),
    )


    return session_id


# ==========================================
# GET SESSION
# ==========================================

def get_session(
    session_id: str,
) -> dict | None:

    session_key = get_session_key(
        session_id
    )


    session_json = redis_client.get(
        session_key
    )


    if not session_json:
        return None


    try:

        return json.loads(
            session_json
        )

    except json.JSONDecodeError:

        return None


# ==========================================
# DELETE SESSION
# ==========================================

def delete_session(
    session_id: str,
) -> bool:

    session_key = get_session_key(
        session_id
    )


    deleted_count = redis_client.delete(
        session_key
    )


    return deleted_count > 0


# ==========================================
# SESSION EXISTS
# ==========================================

def session_exists(
    session_id: str,
) -> bool:

    session_key = get_session_key(
        session_id
    )


    return bool(
        redis_client.exists(
            session_key
        )
    )