"""Shared Redis configuration; legacy Docker host/password remains the default."""
import redis
from app.core.config import REDIS_URL, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD


def create_redis_client(*, timeout=5, max_connections=None):
    options = dict(decode_responses=True, socket_connect_timeout=timeout, socket_timeout=timeout)
    if max_connections is not None:
        options['max_connections'] = max_connections
    if REDIS_URL:
        # redis-py verifies TLS certificates for rediss:// by default.
        return redis.Redis.from_url(REDIS_URL, **options)
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                       password=REDIS_PASSWORD, **options)


redis_client = create_redis_client()


def ping_redis() -> bool:
    return bool(redis_client.ping())
