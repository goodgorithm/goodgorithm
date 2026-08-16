from upstash_redis import Redis

import config

_client: Redis | None = None


def get_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis(
            url=config.UPSTASH_REDIS_REST_URL,
            token=config.UPSTASH_REDIS_REST_TOKEN,
        )
    return _client
