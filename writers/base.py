"""Shared contract for storage-backend writers.

Three datasets flow through the writers, each produced as uniform row tuples by
the parsers in main.py. The single source of truth for every dataset is its
Dataset entry below: column order MUST match, in order, the tuple the matching
parser emits. Adding/reordering a field is a one-place change.

    user_report        <- parse_user_report_csv()
    by_user_analytic   <- parse_by_user_analytic_csv()
    prompt_log         <- parse_prompt_log_file()

Every backend maps these same tuples, so "pick a backend, load everything" works
for all three datasets, not just prompt logs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dataset:
    """Metadata describing one logical table/index across all backends."""
    name: str                       # logical dataset id (== target table/index name)
    columns: list[str]              # column order == parser tuple order
    unique_key: list[str]           # columns that make a row unique (upsert / _id key)
    date_col: str                   # primary date column (partitioning / time filters)
    text_cols: list[str] = field(default_factory=list)   # large text (search backends index these)
    int_cols: list[str] = field(default_factory=list)     # integer-typed columns
    float_cols: list[str] = field(default_factory=list)   # float/double columns
    bool_cols: list[str] = field(default_factory=list)     # 0/1 flag columns
    datetime_cols: list[str] = field(default_factory=list) # ms-precision timestamp columns


# ── user_report ──────────────────────────────────────────────────────────────
USER_REPORT = Dataset(
    name="kiro_user_report",
    columns=[
        "aws_account_id", "account_label", "report_date", "user_id", "user_email",
        "client_type", "chat_conversations", "credits_used", "overage_cap",
        "overage_credits_used", "overage_enabled", "profile_id", "subscription_tier",
        "total_messages", "new_user", "auto_messages",
        "claude_opus_4_6_messages", "claude_opus_4_8_messages",
    ],
    unique_key=["aws_account_id", "report_date", "user_id", "client_type"],
    date_col="report_date",
    int_cols=["chat_conversations", "total_messages", "auto_messages",
              "claude_opus_4_6_messages", "claude_opus_4_8_messages"],
    float_cols=["credits_used", "overage_cap", "overage_credits_used"],
    bool_cols=["overage_enabled", "new_user"],
)

# ── by_user_analytic ─────────────────────────────────────────────────────────
_ANALYTIC_METRICS = [
    "chat_ai_code_lines", "chat_messages_interacted", "chat_messages_sent",
    "codefix_acceptance_count", "codefix_accepted_lines", "codefix_generated_lines",
    "codefix_generation_count", "codereview_failed_count", "codereview_findings_count",
    "codereview_succeeded_count", "dev_acceptance_count", "dev_accepted_lines",
    "dev_generated_lines", "dev_generation_count", "docgen_accepted_file_updates",
    "docgen_accepted_file_creations", "docgen_accepted_line_additions",
    "docgen_accepted_line_updates", "docgen_event_count", "docgen_rejected_file_creations",
    "docgen_rejected_file_updates", "docgen_rejected_line_additions",
    "docgen_rejected_line_updates", "inlinechat_acceptance_count",
    "inlinechat_accepted_line_additions", "inlinechat_accepted_line_deletions",
    "inlinechat_dismissal_count", "inlinechat_dismissed_line_additions",
    "inlinechat_dismissed_line_deletions", "inlinechat_rejected_line_additions",
    "inlinechat_rejected_line_deletions", "inlinechat_rejection_count",
    "inlinechat_total_count", "inline_ai_code_lines", "inline_acceptance_count",
    "inline_suggestions_count", "testgen_accepted_lines", "testgen_accepted_tests",
    "testgen_event_count", "testgen_generated_lines", "testgen_generated_tests",
    "transformation_event_count", "transformation_lines_generated",
    "transformation_lines_ingested",
]
BY_USER_ANALYTIC = Dataset(
    name="kiro_by_user_analytic",
    columns=["aws_account_id", "account_label", "user_id", "report_date", *_ANALYTIC_METRICS],
    unique_key=["aws_account_id", "user_id", "report_date"],
    date_col="report_date",
    int_cols=list(_ANALYTIC_METRICS),
)

# ── prompt_log ───────────────────────────────────────────────────────────────
PROMPT_LOG = Dataset(
    name="kiro_prompt_log",
    columns=[
        "aws_account_id", "account_label", "request_id", "user_id", "user_id_normalized",
        "event_time", "event_date", "model_id", "chat_trigger_type",
        "prompt_length", "user_message_length", "response_length",
        "has_code_in_response", "code_reference_count",
        "prompt_text", "response_text", "source_file",
    ],
    unique_key=["aws_account_id", "request_id"],
    date_col="event_date",
    text_cols=["prompt_text", "response_text"],
    int_cols=["prompt_length", "user_message_length", "response_length", "code_reference_count"],
    bool_cols=["has_code_in_response"],
    datetime_cols=["event_time"],
)

DATASETS = {ds.name: ds for ds in (USER_REPORT, BY_USER_ANALYTIC, PROMPT_LOG)}

# Backwards-compat alias (prompt-log-only callers/tests referenced this name).
PROMPT_LOG_COLUMNS = PROMPT_LOG.columns
UNIQUE_KEY = PROMPT_LOG.unique_key


class Writer(ABC):
    """A backend that persists dataset rows idempotently.

    Usage:
        with get_writer("postgres") as w:
            w.init_schema(USER_REPORT)
            w.write(USER_REPORT, rows)   # called repeatedly in batches
    """

    @abstractmethod
    def init_schema(self, dataset: Dataset) -> None:
        """Create the table/index for `dataset` if absent. Idempotent."""

    @abstractmethod
    def write(self, dataset: Dataset, rows: list[tuple]) -> int:
        """Upsert a batch of row tuples (order == dataset.columns). Returns count written."""

    def close(self) -> None:
        """Release resources. Override if the backend holds a connection."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def get_writer(backend: str) -> "Writer":
    """Factory: map a backend name to a writer instance.

    Imports are done here (not at module top) so an unused backend's client lib
    doesn't need to be installed.
    """
    backend = (backend or "mysql").lower()
    if backend == "mysql":
        from writers.mysql_writer import MySQLWriter
        return MySQLWriter()
    if backend in ("postgres", "postgresql"):
        from writers.postgres_writer import PostgresWriter
        return PostgresWriter()
    if backend in ("opensearch", "elasticsearch", "elastic", "es"):
        from writers.search_writer import SearchWriter
        return SearchWriter(flavor=backend)
    if backend == "clickhouse":
        from writers.clickhouse_writer import ClickHouseWriter
        return ClickHouseWriter()
    raise ValueError(
        f"Unknown backend '{backend}'. "
        "Choose: mysql, postgres, opensearch, elasticsearch, clickhouse"
    )
