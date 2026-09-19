from __future__ import annotations

import html
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import Settings
from .db import ZionDB
from .health import HealthService
from .logging_safe import configure_logging


logger = logging.getLogger("zion.dashboard")


def _status_payload(
    settings: Settings,
    db: ZionDB,
    health: HealthService,
) -> dict[str, Any]:
    snapshot = health.snapshot()
    return {
        "zion": "online",
        "operating_state": snapshot.state.value,
        "database": "ok" if snapshot.db_ok else "fail",
        "ai_provider": "mistral",
        "ai_enabled": settings.ai_enabled,
        "ai_configured": snapshot.ai_configured,
        "ai_observe": settings.ai_observe,
        "wifi_interface_present": snapshot.wifi_interface_present,
        "disk_free_mb": snapshot.disk_free_mb,
        "dashboard_uptime_seconds": snapshot.uptime_seconds,
        "stats": db.stats(),
    }


def _render_html(payload: dict[str, Any]) -> str:
    stats = payload["stats"]
    rows = "".join(
        "<tr><th>"
        + html.escape(str(key))
        + "</th><td>"
        + html.escape(str(value))
        + "</td></tr>"
        for key, value in stats.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZION Operations</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0b0d12; color: #e8ecf3; }}
main {{ max-width: 760px; margin: auto; }}
.card {{ border: 1px solid #2c3340; border-radius: 14px; padding: 1.2rem; margin: 1rem 0; background: #121722; }}
h1 {{ margin-bottom: .2rem; }}
small {{ color: #99a3b3; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: .55rem; border-bottom: 1px solid #252b36; }}
.ok {{ font-weight: 700; }}
</style>
</head>
<body>
<main>
<h1>ZION Operations</h1>
<small>Read-only localhost dashboard</small>
<div class="card">
<p class="ok">ZION: {html.escape(str(payload["zion"]))}</p>
<p>State: {html.escape(str(payload["operating_state"]))}</p>
<p>Database: {html.escape(str(payload["database"]))}</p>
<p>AI: Mistral / enabled={html.escape(str(payload["ai_enabled"]))} / observe={html.escape(str(payload["ai_observe"]))}</p>
<p>Wi-Fi interface: {html.escape(str(payload["wifi_interface_present"]))}</p>
<p>Free disk: {html.escape(str(payload["disk_free_mb"]))} MB</p>
</div>
<div class="card">
<h2>Counters</h2>
<table>{rows}</table>
</div>
</main>
</body>
</html>"""


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_path)

    bind = os.getenv("ZION_DASHBOARD_BIND", "127.0.0.1").strip()
    port = int(os.getenv("ZION_DASHBOARD_PORT", "8765"))

    if bind not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError(
            "ZION dashboard v1 only permits localhost binding."
        )

    db = ZionDB(settings.db_path)
    db.initialize()
    health = HealthService(settings, db)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = _status_payload(settings, db, health)

            if self.path == "/healthz":
                body = json.dumps(
                    {
                        "ok": bool(payload["database"] == "ok"),
                        "state": payload["operating_state"],
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path == "/api/status":
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/json; charset=utf-8",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path != "/":
                self.send_error(404)
                return

            body = _render_html(payload).encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8",
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            logger.info(
                "dashboard request client=%s status=%s",
                self.client_address[0],
                args[1] if len(args) > 1 else "?",
            )

    server = ThreadingHTTPServer((bind, port), Handler)
    logger.info(
        "ZION dashboard listening on http://%s:%s",
        bind,
        port,
    )

    try:
        server.serve_forever(poll_interval=1.0)
    finally:
        server.server_close()
        db.close()


if __name__ == "__main__":
    main()
