from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .db import ZionDB


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
        if not isinstance(payload, dict):
            raise ValueError("legacy root must be an object")
    except Exception as exc:
        logger.warning(
            "Estado legado não pôde ser lido | error=%s",
            type(exc).__name__,
        )
        return

    now = time.time()

    recent_messages: list[tuple[int, int, int, float]] = []
    containments: list[tuple[int, int, float, str, float]] = []
    strikes: list[tuple[int, int, int, float, int]] = []

    try:
        history = payload.get("message_history", {})
        if not isinstance(history, dict):
            raise ValueError("message_history must be an object")

        for raw_key, entries in history.items():
            chat_raw, user_raw = str(raw_key).split(":", 1)
            chat_id = int(chat_raw)
            user_id = int(user_raw)
            if not isinstance(entries, list):
                raise ValueError("message_history entry must be a list")

            for entry in entries:
                if (
                    not isinstance(entry, (list, tuple))
                    or len(entry) != 2
                ):
                    raise ValueError("invalid message_history item")
                timestamp, message_id = entry
                ts = float(timestamp)
                if now - ts <= 600:
                    recent_messages.append(
                        (
                            chat_id,
                            user_id,
                            int(message_id),
                            ts,
                        )
                    )

        blocked = payload.get("flood_blocked_until", {})
        if not isinstance(blocked, dict):
            raise ValueError("flood_blocked_until must be an object")

        for raw_key, blocked_until in blocked.items():
            chat_raw, user_raw = str(raw_key).split(":", 1)
            until = float(blocked_until)
            if until > now:
                containments.append(
                    (
                        int(chat_raw),
                        int(user_raw),
                        until,
                        "legacy_flood",
                        now,
                    )
                )

        raw_strikes = payload.get("flood_strikes", {})
        if not isinstance(raw_strikes, dict):
            raise ValueError("flood_strikes must be an object")

        for raw_key, value in raw_strikes.items():
            chat_raw, user_raw = str(raw_key).split(":", 1)
            if (
                not isinstance(value, (list, tuple))
                or len(value) != 2
            ):
                raise ValueError("invalid flood_strikes item")

            strike_count, last_strike = value
            count = max(0, int(strike_count))
            last = float(last_strike)

            # Legacy strikes were valid for one hour from their original
            # occurrence. Preserve that absolute expiry instead of applying
            # a "remaining TTL" to the old occurrence timestamp.
            if count > 0 and last + 3600 > now:
                strikes.append(
                    (
                        int(chat_raw),
                        int(user_raw),
                        count,
                        last,
                        3600,
                    )
                )
    except Exception as exc:
        logger.warning(
            "Estado legado inválido; nenhuma alteração aplicada | error=%s",
            type(exc).__name__,
        )
        return

    try:
        db.import_legacy_guardian_state(
            marker=marker,
            recent_messages=recent_messages,
            containments=containments,
            strikes=strikes,
            now=now,
        )
        logger.info("Estado legado do Guardião migrado para SQLite.")
    except Exception as exc:
        logger.exception(
            "Falha ao migrar estado legado; transação revertida: %s",
            type(exc).__name__,
        )
