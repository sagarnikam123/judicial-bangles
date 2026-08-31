"""ClickHouse prompt-log writer.

ClickHouse has no row-level UPSERT. The idempotent-correct pattern is
ReplacingMergeTree ordered by (aws_account_id, request_id): duplicate keys are
collapsed at merge time, keeping the last-inserted version. Queries that must
see the deduped view immediately can use `SELECT ... FINAL` or GROUP BY the key.

ponytail: dedup is eventual (on background merge), not on insert — the known
ClickHouse tradeoff. Upgrade path: add `FINAL` in Grafana queries, or a
`created_at` version column with ReplacingMergeTree(created_at) for last-wins.

clickhouse-connect's insert() takes column-ordered row tuples directly, so the
tuple from parse_prompt_log_file() is passed through with only bool/int coercion.
"""

import logging

from conf.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_TABLE,
    CLICKHOUSE_USER,
)
from writers.base import PROMPT_LOG_COLUMNS, PromptLogWriter

logger = logging.getLogger(__name__)

CREATE_PROMPT_LOG_CH = f"""
CREATE TABLE IF NOT EXISTS {CLICKHOUSE_TABLE} (
    aws_account_id String,
    account_label String,
    request_id String,
    user_id String,
    user_id_normalized String,
    event_time DateTime64(3),
    event_date Date,
    model_id String,
    chat_trigger_type String,
    prompt_length Int32,
    user_message_length Int32,
    response_length Int32,
    has_code_in_response UInt8,
    code_reference_count Int32,
    prompt_text String,
    response_text String,
    source_file String,
    created_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(created_at)
ORDER BY (aws_account_id, request_id)
PARTITION BY toYYYYMM(event_date)
"""


class ClickHousePromptWriter(PromptLogWriter):
    def __init__(self):
        self.client = None
        self.table = CLICKHOUSE_TABLE

    def _connect(self):
        if self.client is None:
            import clickhouse_connect  # lazy import
            self.client = clickhouse_connect.get_client(
                host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT,
                username=CLICKHOUSE_USER, password=CLICKHOUSE_PASSWORD,
                database=CLICKHOUSE_DB,
            )
        return self.client

    def init_schema(self) -> None:
        client = self._connect()
        client.command(f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DB}")
        client.command(CREATE_PROMPT_LOG_CH)

    def _coerce(self, row: tuple) -> list:
        d = dict(zip(PROMPT_LOG_COLUMNS, row))
        # ClickHouse String columns reject NULL; map None text -> "".
        d["prompt_text"] = d.get("prompt_text") or ""
        d["response_text"] = d.get("response_text") or ""
        d["model_id"] = d.get("model_id") or ""
        d["chat_trigger_type"] = d.get("chat_trigger_type") or ""
        d["has_code_in_response"] = int(bool(d.get("has_code_in_response")))
        return [d[c] for c in PROMPT_LOG_COLUMNS]

    def write(self, rows: list[tuple]) -> int:
        if not rows:
            return 0
        client = self._connect()
        data = [self._coerce(r) for r in rows]
        client.insert(self.table, data, column_names=PROMPT_LOG_COLUMNS)
        logger.info(f"[clickhouse] inserted {len(data)} prompt-log rows into {self.table}")
        return len(data)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
