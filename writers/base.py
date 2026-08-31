"""Shared contract for prompt-log writers.

The single source of truth for the row shape is PROMPT_LOG_COLUMNS: it MUST match,
in order, the tuple produced by main.parse_prompt_log_file(). Every backend maps
that tuple through these names, so adding/reordering a field is a one-place change.
"""

from abc import ABC, abstractmethod

# Column order == the tuple order emitted by parse_prompt_log_file().
# (aws_account_id, account_label, request_id, user_id, user_id_normalized,
#  event_time, event_date, model_id, chat_trigger_type,
#  prompt_length, user_message_length, response_length,
#  has_code_in_response, code_reference_count,
#  prompt_text, response_text, source_file)
PROMPT_LOG_COLUMNS = [
    "aws_account_id",
    "account_label",
    "request_id",
    "user_id",
    "user_id_normalized",
    "event_time",
    "event_date",
    "model_id",
    "chat_trigger_type",
    "prompt_length",
    "user_message_length",
    "response_length",
    "has_code_in_response",
    "code_reference_count",
    "prompt_text",
    "response_text",
    "source_file",
]

# Columns that make each record unique (idempotent upsert / doc _id key).
UNIQUE_KEY = ["aws_account_id", "request_id"]


class PromptLogWriter(ABC):
    """A backend that persists prompt-log rows idempotently.

    Usage:
        with get_writer("postgres") as w:
            w.init_schema()
            w.write(rows)   # called repeatedly in batches
    """

    @abstractmethod
    def init_schema(self) -> None:
        """Create the table/index if it doesn't exist. Idempotent."""

    @abstractmethod
    def write(self, rows: list[tuple]) -> int:
        """Upsert a batch of row tuples (order == PROMPT_LOG_COLUMNS). Returns count written."""

    def close(self) -> None:
        """Release resources. Override if the backend holds a connection."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def get_writer(backend: str) -> "PromptLogWriter":
    """Factory: map a backend name to a writer instance.

    Imports are done here (not at module top) so an unused backend's client lib
    doesn't need to be installed.
    """
    backend = (backend or "mysql").lower()
    if backend == "mysql":
        from writers.mysql_writer import MySQLPromptWriter
        return MySQLPromptWriter()
    if backend in ("postgres", "postgresql"):
        from writers.postgres_writer import PostgresPromptWriter
        return PostgresPromptWriter()
    if backend in ("opensearch", "elasticsearch", "elastic", "es"):
        from writers.search_writer import SearchPromptWriter
        return SearchPromptWriter(flavor=backend)
    if backend == "clickhouse":
        from writers.clickhouse_writer import ClickHousePromptWriter
        return ClickHousePromptWriter()
    raise ValueError(
        f"Unknown backend '{backend}'. "
        "Choose: mysql, postgres, opensearch, elasticsearch, clickhouse"
    )
