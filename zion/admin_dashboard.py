from __future__ import annotations

import html
import json
import logging
import os
import shutil
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .db import ZionDB
from .logging_safe import configure_logging


logger = logging.getLogger("zion.dashboard")


def _allowed_dashboard_host(value: str, port: int) -> bool:
    host = (value or "").strip().lower()
    allowed = {
        "localhost",
        f"localhost:{port}",
        "127.0.0.1",
        f"127.0.0.1:{port}",
        "[::1]",
        f"[::1]:{port}",
    }
    return host in allowed


def _status_payload(
    db: ZionDB,
    *,
    root_dir: Path,
    wifi_interface: str,
    started_monotonic: float,
) -> dict[str, Any]:
    try:
        disk = shutil.disk_usage(root_dir)
        disk_free_mb = int(disk.free / 1024 / 1024)
    except OSError:
        disk_free_mb = -1

    wifi_present = (
        Path("/sys/class/net") / wifi_interface
    ).exists()

    integrity_ok, integrity_result = db.integrity_check()
    db_size_mb = int(db.file_size_bytes() / 1024 / 1024)
    db_read_ok = True

    try:
        operating_state = db.get_operating_state().value
    except Exception:
        operating_state = "SAFE_MODE"
        db_read_ok = False

    try:
        stats = db.stats()
    except Exception:
        stats = {}
        db_read_ok = False

    database_ok = db.ping() and integrity_ok and db_read_ok

    return {
        "zion_dashboard": "online",
        "operating_state": operating_state,
        "database": "ok" if database_ok else "fail",
        "sqlite_integrity": integrity_result,
        "database_size_mb": db_size_mb,
        "wifi_interface_present": wifi_present,
        "disk_free_mb": disk_free_mb,
        "dashboard_uptime_seconds": int(
            time.monotonic() - started_monotonic
        ),
        "stats": stats,
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
<p class="ok">Dashboard: {html.escape(str(payload["zion_dashboard"]))}</p>
<p>State: {html.escape(str(payload["operating_state"]))}</p>
<p>Database: {html.escape(str(payload["database"]))}</p>
<p>SQLite integrity: {html.escape(str(payload["sqlite_integrity"]))}</p>
<p>Database size: {html.escape(str(payload["database_size_mb"]))} MB</p>
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
    root_dir = Path(
        os.getenv(
            "ZION_DASHBOARD_ROOT",
            "/home/zetta/zion-community-bot",
        )
    )
    db_path = Path(
        os.getenv(
            "ZION_DASHBOARD_DB_PATH",
            str(root_dir / "zion.db"),
        )
    )
    wifi_interface = os.getenv(
        "ZION_DASHBOARD_WIFI_INTERFACE",
        "wlx78bdbc575d1c",
    ).strip()
    bind = os.getenv(
        "ZION_DASHBOARD_BIND",
        "127.0.0.1",
    ).strip()
    port = int(os.getenv("ZION_DASHBOARD_PORT", "8765"))

    if bind not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError(
            "ZION dashboard v1 only permits localhost binding."
        )

    log_path = Path(
        os.getenv(
            "ZION_DASHBOARD_LOG_PATH",
            str(
                Path.home()
                / ".local"
                / "state"
                / "zion-community-bot"
                / "zion-dashboard.log"
            ),
        )
    ).expanduser()
    configure_logging(log_path)

    db = ZionDB(db_path, readonly=True)
    started_monotonic = time.monotonic()

    class Handler(BaseHTTPRequestHandler):
        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )

        def _send_bytes(
            self,
            status: int,
            content_type: str,
            body: bytes,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not _allowed_dashboard_host(
                self.headers.get("Host", ""),
                port,
            ):
                self._send_bytes(
                    421,
                    "text/plain; charset=utf-8",
                    b"Misdirected Request",
                )
                return

            payload = _status_payload(
                db,
                root_dir=root_dir,
                wifi_interface=wifi_interface,
                started_monotonic=started_monotonic,
            )

            if self.path == "/healthz":
                body = json.dumps(
                    {
                        "ok": bool(payload["database"] == "ok"),
                        "state": payload["operating_state"],
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                self._send_bytes(
                    200 if payload["database"] == "ok" else 503,
                    "application/json; charset=utf-8",
                    body,
                )
                return

            if self.path == "/api/status":
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self._send_bytes(
                    200,
                    "application/json; charset=utf-8",
                    body,
                )
                return

            if self.path != "/":
                self._send_bytes(
                    404,
                    "text/plain; charset=utf-8",
                    b"Not Found",
                )
                return

            body = _render_html(payload).encode("utf-8")
            self._send_bytes(
                200,
                "text/html; charset=utf-8",
                body,
            )

        def log_message(self, format: str, *args: object) -> None:
            logger.info(
                "dashboard request client=%s status=%s",
                self.client_address[0],
                args[1] if len(args) > 1 else "?",
            )

    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
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
