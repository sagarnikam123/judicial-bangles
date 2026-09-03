"""Pluggable storage backends for all Kiro datasets.

The parsers in main.py produce uniform row tuples for three datasets
(user_report, by_user_analytic, prompt_log). Each writer here persists any of
them to one backend. Select at runtime with --backend / STORAGE_BACKEND.

    mysql        -> MySQLWriter
    postgres     -> PostgresWriter
    opensearch   -> SearchWriter      (opensearch-py)
    elasticsearch-> SearchWriter      (same client, ES-compatible)
    clickhouse   -> ClickHouseWriter

Backend client libraries are imported lazily inside each writer, so using MySQL
never requires opensearch-py / psycopg2 / clickhouse-connect to be installed.
"""

from writers.base import (
    _USER_REPORT_MODELS,
    BY_USER_ANALYTIC,
    DATASETS,
    PROMPT_LOG,
    PROMPT_LOG_COLUMNS,
    USER_REPORT,
    Dataset,
    Writer,
    get_writer,
)

__all__ = [
    "Dataset", "Writer", "get_writer", "DATASETS",
    "USER_REPORT", "BY_USER_ANALYTIC", "PROMPT_LOG", "PROMPT_LOG_COLUMNS",
    "_USER_REPORT_MODELS",
]
