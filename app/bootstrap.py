import os
import time

from sqlalchemy import text

import app.db.chat_models  # noqa: F401 - registers chat tables in Base.metadata
from app.db.chat_models import ensure_chat_session_runtime_schema
from app.db.repository import create_tables
from app.db.session import engine
from app.interfaces.telegram_bot import main as run_telegram_bot
from app.logger import get_logger, setup_logger


logger = get_logger(__name__)


def wait_for_database() -> None:
    attempts = int(os.getenv("DB_WAIT_ATTEMPTS", "60"))
    delay = float(os.getenv("DB_WAIT_DELAY", "2"))

    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database is ready")
            return
        except Exception as exc:
            logger.warning("Database is not ready yet (%s/%s): %s", attempt, attempts, exc)
            time.sleep(delay)

    raise RuntimeError("Database did not become ready in time")


def main() -> None:
    setup_logger()
    wait_for_database()
    create_tables(engine)
    ensure_chat_session_runtime_schema(engine)
    entrypoint = os.getenv("APP_ENTRYPOINT", "telegram").strip().lower()
    if entrypoint == "telegram":
        run_telegram_bot()
        return
    raise RuntimeError(f"Unsupported APP_ENTRYPOINT={entrypoint!r}; use 'telegram'")


if __name__ == "__main__":
    main()
