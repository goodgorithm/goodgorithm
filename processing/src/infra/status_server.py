import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from infra import degradation
from pipeline_stages import category_model, sentiment

logger = logging.getLogger("processing")

# Auditable first-look status, not a log replacement -- narrows down where
# to look next, doesn't replace digging through logs for the actual detail.
# See CLAUDE.md's Service resilience section and the wiki's Pipeline
# Internals page.

# A last-successful-cycle older than this counts as degraded -- catches a
# loop that wedged without crashing. Comfortably above the idle cycle gap
# (PROCESSING_INTERVAL_SECONDS, default 300, plus one cycle's work), with
# the strict endpoint's external monitor debounced on top. See the wiki's
# Configuration page.
STATUS_STALE_CYCLE_SECONDS = int(os.environ.get("STATUS_STALE_CYCLE_SECONDS", "900"))

_public_config: dict = {}
_started_at: datetime = datetime.now(timezone.utc)


def _build_status() -> dict:
    degraded = degradation.snapshot()
    stale = degradation.cycle_staleness_message(STATUS_STALE_CYCLE_SECONDS, _started_at)
    if stale:
        # Folded into `degraded` (not a separate top-level field) so the
        # single `status` verdict and the strict endpoint's 503 both cover
        # a wedged loop, and a reader scans one place for "what's wrong".
        degraded = {
            **degraded,
            "cycle": {"last_degraded_at": datetime.now(timezone.utc).isoformat(), "message": stale},
        }
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


def strict_status_code(status: dict) -> int:
    """503 when degraded, 200 otherwise -- so /health/strict works as a plain
    up/down check for an external monitor. Kept off /health itself, which
    must stay 200 for Railway's deploy-time healthcheck (a degraded process
    is still deliberately running -- see CLAUDE.md's Service resilience)."""
    return 503 if status["status"] == "degraded" else 200


class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._respond(200, _build_status())
        elif self.path == "/health/strict":
            status = _build_status()
            self._respond(strict_status_code(status), status)
        else:
            self.send_response(404)
            self.end_headers()

    def _respond(self, code: int, status: dict) -> None:
        # Compact separators so the body matches ingestion/'s JSON.stringify
        # output byte-for-byte on the "status":"..." marker -- the external
        # monitor's keyword assertion is written once for both services.
        body = json.dumps(status, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
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
    global _public_config, _started_at
    _public_config = public_config
    _started_at = datetime.now(timezone.utc)
    server = ThreadingHTTPServer(("0.0.0.0", port), _StatusHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("status server listening on :%d/health", port)
