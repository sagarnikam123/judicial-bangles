"""Contract self-check for the dataset-driven writers.

The whole design rests on one invariant: for each dataset, the tuple the parser
emits lines up 1:1 (order + length) with Dataset.columns, and the generated SQL
(DDL + upsert) is built from that same column list. If any drift, row values land
in the wrong columns across every backend.

Run: python3 tests/test_backend_contract.py   (no framework, asserts only)
"""

import gzip
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import (  # noqa: E402
    parse_by_user_analytic_csv,
    parse_prompt_log_file,
    parse_user_report_csv,
)
from writers.base import BY_USER_ANALYTIC, PROMPT_LOG, USER_REPORT  # noqa: E402
from writers.sqlgen import (  # noqa: E402
    clickhouse_column_type,
    mysql_column_type,
    postgres_column_type,
    upsert_sql_mysql,
    upsert_sql_postgres,
)


def _write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text)
    return p


def test_user_report_tuple_matches_columns():
    csv = ("Date,UserId,User_Email,Client_Type,Chat_Conversations,Credits_Used,"
           "Overage_Cap,Overage_Credits_Used,Overage_Enabled,ProfileId,Subscription_Tier,"
           "Total_Messages,New_User,auto_messages,claude_opus_4.6_messages,claude_opus_4.8_messages\n"
           "2026-08-22,idc-uuid,jdoe@example.com,KIRO_IDE,3,12.5,100,0,false,pid,PRO,"
           "42,true,10,5,7\n")
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "ur.csv", csv)
        rows = parse_user_report_csv(f, "111111111111", "prod")
    assert len(rows) == 1
    assert len(rows[0]) == len(USER_REPORT.columns), (
        f"user_report tuple has {len(rows[0])} fields, "
        f"columns has {len(USER_REPORT.columns)}"
    )
    print("OK: user_report tuple matches columns")


def test_by_user_analytic_tuple_matches_columns():
    # header only + one all-zeros row is enough to check arity
    cols = ("Date,UserId,Chat_AICodeLines,Chat_MessagesInteracted,Chat_MessagesSent,"
            "CodeFix_AcceptanceEventCount,CodeFix_AcceptedLines,CodeFix_GeneratedLines,"
            "CodeFix_GenerationEventCount,CodeReview_FailedEventCount,CodeReview_FindingsCount,"
            "CodeReview_SucceededEventCount,Dev_AcceptanceEventCount,Dev_AcceptedLines,"
            "Dev_GeneratedLines,Dev_GenerationEventCount,DocGeneration_AcceptedFileUpdates,"
            "DocGeneration_AcceptedFilesCreations,DocGeneration_AcceptedLineAdditions,"
            "DocGeneration_AcceptedLineUpdates,DocGeneration_EventCount,"
            "DocGeneration_RejectedFileCreations,DocGeneration_RejectedFileUpdates,"
            "DocGeneration_RejectedLineAdditions,DocGeneration_RejectedLineUpdates,"
            "InlineChat_AcceptanceEventCount,InlineChat_AcceptedLineAdditions,"
            "InlineChat_AcceptedLineDeletions,InlineChat_DismissalEventCount,"
            "InlineChat_DismissedLineAdditions,InlineChat_DismissedLineDeletions,"
            "InlineChat_RejectedLineAdditions,InlineChat_RejectedLineDeletions,"
            "InlineChat_RejectionEventCount,InlineChat_TotalEventCount,Inline_AICodeLines,"
            "Inline_AcceptanceCount,Inline_SuggestionsCount,TestGeneration_AcceptedLines,"
            "TestGeneration_AcceptedTests,TestGeneration_EventCount,TestGeneration_GeneratedLines,"
            "TestGeneration_GeneratedTests,Transformation_EventCount,Transformation_LinesGenerated,"
            "Transformation_LinesIngested")
    row = "2026-08-22,idc-uuid," + ",".join(["0"] * 45)
    with tempfile.TemporaryDirectory() as d:
        f = _write(Path(d), "an.csv", cols + "\n" + row + "\n")
        rows = parse_by_user_analytic_csv(f, "111111111111", "prod")
    assert len(rows) == 1
    assert len(rows[0]) == len(BY_USER_ANALYTIC.columns), (
        f"by_user_analytic tuple has {len(rows[0])} fields, "
        f"columns has {len(BY_USER_ANALYTIC.columns)}"
    )
    print("OK: by_user_analytic tuple matches columns")


def test_prompt_log_tuple_matches_columns():
    rec = {"records": [{
        "generateAssistantResponseEventRequest": {
            "userId": "d-abc.11112222-3333-4444-5555-666677778888",
            "prompt": "--- USER MESSAGE BEGIN ---\nhi\n--- USER MESSAGE END ---",
            "timeStamp": "2026-08-22T10:11:12.345678900Z",
            "modelId": "claude-sonnet", "chatTriggerType": "MANUAL",
        },
        "generateAssistantResponseEventResponse": {
            "requestId": "req-1", "assistantResponse": "x\n```py\n1\n```",
            "codeReferenceEvents": [{"a": 1}],
        },
    }]}
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "s.json.gz"
        with gzip.open(p, "wt", encoding="utf-8") as gz:
            json.dump(rec, gz)
        rows = parse_prompt_log_file(p, "111111111111", "prod", store_text=True)
    assert len(rows) == 1
    assert len(rows[0]) == len(PROMPT_LOG.columns), (
        f"prompt_log tuple has {len(rows[0])} fields, columns has {len(PROMPT_LOG.columns)}"
    )
    d2 = dict(zip(PROMPT_LOG.columns, rows[0]))
    assert d2["user_id_normalized"] == "abc-11112222-3333-4444-5555-666677778888"
    assert d2["has_code_in_response"] == 1
    print("OK: prompt_log tuple matches columns")


def test_generated_sql_covers_every_column():
    for ds in (USER_REPORT, BY_USER_ANALYTIC, PROMPT_LOG):
        n = len(ds.columns)
        # MySQL upsert: one %s per column, one VALUES()-update per non-key column
        my = upsert_sql_mysql(ds)
        assert my.count("%s") == n, f"{ds.name}: mysql placeholders {my.count('%s')} != {n}"
        # Postgres upsert: same placeholder count + EXCLUDED for each non-key column
        pg = upsert_sql_postgres(ds)
        assert pg.count("%s") == n, f"{ds.name}: pg placeholders {pg.count('%s')} != {n}"
        for c in ds.columns:
            if c in ds.unique_key:
                continue
            assert re.search(rf"\b{c} = EXCLUDED\.{c}\b", pg), f"{ds.name}: pg missing {c}"
        # every column resolves to a concrete type in all three SQL dialects
        for c in ds.columns:
            assert mysql_column_type(ds, c)
            assert postgres_column_type(ds, c)
            assert clickhouse_column_type(ds, c)
        print(f"OK: generated SQL covers all {n} columns for {ds.name}")


def test_clickhouse_coerces_string_dates_to_objects():
    """Parsers emit dates as strings; the ClickHouse driver needs date/datetime
    objects for Date/DateTime columns (a plain str raises TypeError on insert).
    Guards the _coerce conversion. Offline — no ClickHouse server needed.
    """
    from datetime import date, datetime

    from writers.base import PROMPT_LOG, USER_REPORT
    from writers.clickhouse_writer import ClickHouseWriter

    w = ClickHouseWriter()

    # user_report: report_date (date_col) as "YYYY-MM-DD" string -> date
    ur_row = tuple("x" if c not in USER_REPORT.int_cols + USER_REPORT.float_cols
                   + USER_REPORT.bool_cols else 0 for c in USER_REPORT.columns)
    ur_row = tuple(("2026-08-22" if c == "report_date" else v)
                   for c, v in zip(USER_REPORT.columns, ur_row))
    coerced = dict(zip(USER_REPORT.columns, w._coerce(USER_REPORT, ur_row)))
    assert isinstance(coerced["report_date"], date), type(coerced["report_date"])

    # prompt_log: event_time (datetime_col) with ms + event_date -> datetime/date
    pl = {c: ("2026-08-22 10:11:12.345" if c == "event_time"
              else "2026-08-22" if c == "event_date"
              else None if c in PROMPT_LOG.text_cols
              else 0 if c in PROMPT_LOG.int_cols + PROMPT_LOG.bool_cols
              else "x") for c in PROMPT_LOG.columns}
    coerced = dict(zip(PROMPT_LOG.columns, w._coerce(PROMPT_LOG, tuple(pl[c] for c in PROMPT_LOG.columns))))
    assert isinstance(coerced["event_time"], datetime), type(coerced["event_time"])
    assert isinstance(coerced["event_date"], date)
    # nullable text -> "" (ClickHouse String is non-nullable)
    assert coerced["prompt_text"] == ""
    print("OK: ClickHouse coerces string dates/datetimes to objects, NULL text to ''")


def test_every_writer_is_a_context_manager():
    """get_writer(b) must return an object usable in `with ...` (Writer subclass).

    Regression guard: main.load_all() does `with get_writer(backend) as w`, so a
    writer missing __enter__/__exit__ (e.g. not subclassing Writer) breaks every
    load. Construction is offline (clients are lazy), so this needs no live server.
    """
    from writers.base import Writer, get_writer
    for b in ("mysql", "postgres", "opensearch", "elasticsearch", "clickhouse"):
        w = get_writer(b)
        assert isinstance(w, Writer), f"{b} writer must subclass Writer"
        assert hasattr(w, "__enter__") and hasattr(w, "__exit__"), f"{b} not a context manager"
    print("OK: all 5 writers are Writer-subclass context managers")


if __name__ == "__main__":
    test_user_report_tuple_matches_columns()
    test_by_user_analytic_tuple_matches_columns()
    test_prompt_log_tuple_matches_columns()
    test_generated_sql_covers_every_column()
    test_clickhouse_coerces_string_dates_to_objects()
    test_every_writer_is_a_context_manager()
    print("\nAll dataset-contract checks passed.")
