import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from infra import degradation
from pipeline_stages import category_model, sentiment

logger = logging.getLogger("processing")

# Auditable first-look status, not a log replacement -- narrows down where
# to look next, doesn't replace digging through logs for the actual detail.
# See CLAUDE.md's Service resilience section and the wiki's Pipeline
# Internals page.

_public_config: dict = {}


def _build_status() -> dict:
    degraded = degradation.snapshot()
    return {
        "status": "degraded" if degraded else "ok",
        "last_cycle_success_at": degradation.last_cycle_success_at(),
        "degraded": degraded,
        "models": {
            "sentiment": {
                "method": sentiment.SENTIMENT_METHOD,
                "version": sentiment.SENTIMENT_MODEL_LOADED_VERSION,
            },
            "category": {
                "method": category_model.CATEGORY_METHOD,
                "version": category_model.CATEGORY_MODEL_LOADED_VERSION,
            },
        },
        "config": _public_config,
    }


class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(_build_status()).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        # BaseHTTPRequestHandler logs every request to stderr by default --
        # this is a low-traffic status endpoint, not worth the log noise.
        pass


def start(port: int, public_config: dict) -> None:
    """Starts the status server in a background daemon thread so it never
    blocks main.py's own loop -- a daemon thread also means it never
    prevents process shutdown on its own. Never called in --once mode: a
    one-shot CLI run has nothing worth serving status for."""
    global _public_config
    _public_config = public_config
    server = ThreadingHTTPServer(("0.0.0.0", port), _StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("status server listening on :%d/health", port)
