"""Compatibility entrypoint for the ZION Community OS.

systemd continues to execute bot.py. The implementation lives in zion/.
"""

import logging
import sys

from zion.logging_safe import configure_logging, redact_secrets
from zion.config import Settings
from zion.telegram_app import main


__all__ = ["main", "redact_secrets"]


if __name__ == "__main__":
    settings = Settings.from_env()
    logger = configure_logging(settings.log_path)

    try:
        main()
    except KeyboardInterrupt:
        logger.info("ZION interrompido manualmente.")
    except Exception:
        logger.exception(
            "Falha fatal no ZION. O systemd poderá reiniciá-lo."
        )
        sys.exit(1)
