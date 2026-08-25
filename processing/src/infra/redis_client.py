import redis as redis_py

import config


class _CompatPipeline:
    """Preserves the upstash_redis Pipeline shape (.execute([...]) queues a
    raw command and returns self; .exec() runs the queue and returns
    ordered results) on top of redis-py's real Pipeline, so dedup.py/
    bot_filter.py/topicality.py/redis_guard.py need no changes for the
    underlying client swap. redis-py's own Pipeline.execute_command(...)
    already queues rather than sends immediately, which is what makes
    .execute() -> .exec() a faithful translation rather than a re-implementation."""

    def __init__(self, pipe):
        self._pipe = pipe

    def execute(self, command):
        self._pipe.execute_command(*command)
        return self

    def exec(self):
        return self._pipe.execute()

    def get(self, key):
        self._pipe.get(key)
        return self

    def set(self, key, value, ex=None):
        self._pipe.set(key, value, ex=ex)
        return self

    def incr(self, key):
        self._pipe.incr(key)
        return self

    def expire(self, key, seconds, nx=False):
        self._pipe.expire(key, seconds, nx=nx)
        return self

    def sadd(self, key, *values):
        self._pipe.sadd(key, *values)
        return self

    def smembers(self, key):
        self._pipe.smembers(key)
        return self


class _CompatClient:
    """Same rationale as _CompatPipeline -- preserves upstash_redis's client
    surface (.execute([...]) raw dispatch, .scan(cursor, match=, count=)
    returning (cursor, keys), .pipeline(), .delete(*keys)) on top of
    redis-py, so every existing call site keeps working unchanged."""

    def __init__(self, conn):
        self._conn = conn

    def pipeline(self):
        return _CompatPipeline(self._conn.pipeline())

    def execute(self, command):
        return self._conn.execute_command(*command)

    def scan(self, cursor, match=None, count=None):
        return self._conn.scan(cursor=cursor, match=match, count=count)

    def delete(self, *keys):
        return self._conn.delete(*keys)


_client: _CompatClient | None = None


def get_client() -> _CompatClient:
    global _client
    if _client is None:
        # decode_responses=True matches upstash_redis's always-string
        # values -- redis-py defaults to bytes, which would silently break
        # every key/value comparison and f-string across the pipeline
        # stages that use this client.
        conn = redis_py.Redis.from_url(config.REDIS_URL, decode_responses=True)
        _client = _CompatClient(conn)
    return _client
