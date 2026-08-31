"""PostgreSQL prompt-log writer.

Same column set as MySQL; differences are dialect-only:
  - INT/TINYINT -> INTEGER/SMALLINT, DATETIME(3) -> TIMESTAMP(3), MEDIUMTEXT -> TEXT
  - upsert via ON CONFLICT (aws_account_id, request_id) DO UPDATE
psycopg2 uses %s placeholders, so the VALUES clause matches MySQL's.
"""

import logging

from conf.config import PG_DB, PG_HOST, PG_PASSWORD, PG_PORT, PG_USER
from writers.base import PROMPT_LOG_COLUMNS, UNIQUE_KEY, PromptLogWriter

logger = logging.getLogger(__name__)

CREATE_PROMPT_LOG_PG = """
CREATE TABLE IF NOT EXISTS kiro_prompt_log (
    id BIGSERIAL PRIMARY KEY,
    aws_account_id VARCHAR(16) NOT NULL,
    account_label VARCHAR(32) NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    user_id_normalized VARCHAR(128) NOT NULL,
    event_time TIMESTAMP(3) NOT NULL,
    event_date DATE NOT NULL,
    model_id VARCHAR(64),
    chat_trigger_type VARCHAR(32),
    prompt_length INTEGER DEFAULT 0,
    user_message_length INTEGER DEFAULT 0,
    response_length INTEGER DEFAULT 0,
    has_code_in_response SMALLINT DEFAULT 0,
    code_reference_count INTEGER DEFAULT 0,
    prompt_text TEXT,
    response_text TEXT,
    source_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_prompt_log UNIQUE (aws_account_id, request_id)
);
CREATE INDEX IF NOT EXISTS idx_pl_account_date ON kiro_prompt_log (aws_account_id, event_date);
CREATE INDEX IF NOT EXISTS idx_pl_user_date ON kiro_prompt_log (user_id_normalized, event_date);
CREATE INDEX IF NOT EXISTS idx_pl_model ON kiro_prompt_log (model_id);
CREATE INDEX IF NOT EXISTS idx_pl_event_time ON kiro_prompt_log (event_time);
"""

# Build INSERT ... ON CONFLICT from the shared column list (no hand-maintained SQL).
_cols = ", ".join(PROMPT_LOG_COLUMNS)
_placeholders = ", ".join(["%s"] * len(PROMPT_LOG_COLUMNS))
_update_cols = [c for c in PROMPT_LOG_COLUMNS if c not in UNIQUE_KEY]
_update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in _update_cols)
UPSERT_PROMPT_LOG_PG = (
    f"INSERT INTO kiro_prompt_log ({_cols}) VALUES ({_placeholders}) "
    f"ON CONFLICT (aws_account_id, request_id) DO UPDATE SET {_update_set}"
)


class PostgresPromptWriter(PromptLogWriter):
    def __init__(self):
        self.conn = None

    def _connect(self):
        if self.conn is None:
            import psycopg2  # lazy: only needed for this backend
            self.conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, dbname=PG_DB,
                user=PG_USER, password=PG_PASSWORD,
            )
            self.conn.autocommit = True
        return self.conn

    def init_schema(self) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(CREATE_PROMPT_LOG_PG)

    def write(self, rows: list[tuple]) -> int:
        if not rows:
            return 0
        conn = self._connect()
        with conn.cursor() as cur:
            cur.executemany(UPSERT_PROMPT_LOG_PG, rows)
        logger.info(f"[postgres] upserted {len(rows)} prompt-log rows")
        return len(rows)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
