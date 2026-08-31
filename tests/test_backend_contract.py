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


if __name__ == "__main__":
    test_user_report_tuple_matches_columns()
    test_by_user_analytic_tuple_matches_columns()
    test_prompt_log_tuple_matches_columns()
    test_generated_sql_covers_every_column()
    print("\nAll dataset-contract checks passed.")
