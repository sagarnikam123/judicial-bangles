"""MySQL prompt-log writer — thin wrapper over the existing db.py logic."""

import logging

from db import CREATE_PROMPT_LOG, UPSERT_PROMPT_LOG, get_connection
from writers.base import PromptLogWriter

logger = logging.getLogger(__name__)


class MySQLPromptWriter(PromptLogWriter):
    def __init__(self):
        self.conn = None

    def _connect(self):
        if self.conn is None:
            self.conn = get_connection()
        return self.conn

    def init_schema(self) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(CREATE_PROMPT_LOG)

    def write(self, rows: list[tuple]) -> int:
        if not rows:
            return 0
        conn = self._connect()
        with conn.cursor() as cur:
            cur.executemany(UPSERT_PROMPT_LOG, rows)
        logger.info(f"[mysql] upserted {len(rows)} prompt-log rows")
        return len(rows)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
