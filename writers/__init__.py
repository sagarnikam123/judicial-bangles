"""Pluggable prompt-log storage backends.

parse_prompt_log_file() (in main.py) produces uniform row tuples. Each writer
here accepts those tuples and persists them to one backend. Select at runtime
with --backend / PROMPT_LOG_BACKEND.

    mysql        -> MySQLPromptWriter       (default, reuses db.py)
    postgres     -> PostgresPromptWriter
    opensearch   -> SearchPromptWriter      (opensearch-py)
    elasticsearch-> SearchPromptWriter      (same client, ES-compatible)
    clickhouse   -> ClickHousePromptWriter

Backend client libraries are imported lazily inside each writer, so using MySQL
never requires opensearch-py / psycopg2 / clickhouse-connect to be installed.
"""

from writers.base import PROMPT_LOG_COLUMNS, PromptLogWriter, get_writer

__all__ = ["PROMPT_LOG_COLUMNS", "PromptLogWriter", "get_writer"]
