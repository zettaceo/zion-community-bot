from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .db import ZionDB
from .models import Severity


logger = logging.getLogger("zion.migrate")


def migrate_legacy_guardian_state(db: ZionDB, state_file: Path) -> None:
    marker = "legacy_guardian_state_imported_v1"
    if db.get_setting(marker) == "1":
        return

    if not state_file.exists():
        db.set_setting(marker, "1")
        return

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Estado legado não pôde ser lido: %s", exc)
        return

    now = time.time()

    try:
        for raw_key, entries in payload.get("message_history", {}).items():
            chat_raw, user_raw = raw_key.split(":", 1)
            chat_id = int(chat_raw)
            user_id = int(user_raw)
            for timestamp, message_id in entries:
                ts = float(timestamp)
                if now - ts <= 600:
                    db.record_recent_message(
                        chat_id,
                        user_id,
                        int(message_id),
                        ts,
                    )

        for raw_key, blocked_until in payload.get(
            "flood_blocked_until",
            {},
        ).items():
            chat_raw, user_raw = raw_key.split(":", 1)
            until = float(blocked_until)
            if until > now:
                db.set_containment(
                    int(chat_raw),
                    int(user_raw),
                    until,
                    "legacy_flood",
                    now,
                )

        for raw_key, value in payload.get("flood_strikes", {}).items():
            chat_raw, user_raw = raw_key.split(":", 1)
            strike_count, last_strike = value
            count = max(0, int(strike_count))
            last = float(last_strike)
            ttl = max(60, int(3600 - max(0.0, now - last)))
            for index in range(count):
                db.add_strike(
                    chat_id=int(chat_raw),
                    user_id=int(user_raw),
                    reason="legacy_flood",
                    severity=Severity.MEDIUM,
                    source="legacy_import",
                    ttl_seconds=ttl,
                    metadata={
                        "legacy_index": index + 1,
                        "legacy_count": count,
                    },
                    now=last,
                )

        db.set_setting(marker, "1")
        logger.info("Estado legado do Guardião migrado para SQLite.")
    except Exception as exc:
        logger.exception(
            "Falha ao migrar estado legado; arquivo original preservado: %s",
            exc,
        )
