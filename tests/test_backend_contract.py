"""Contract self-check: the shared PROMPT_LOG_COLUMNS list must stay in lockstep
with (a) the tuple parse_prompt_log_file() emits and (b) the MySQL upsert SQL.
If any drift, row values land in the wrong columns across every backend.

Run: python3 tests/test_backend_contract.py   (no framework, asserts only)
"""

import gzip
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import UPSERT_PROMPT_LOG  # noqa: E402
from main import parse_prompt_log_file  # noqa: E402
from writers.base import PROMPT_LOG_COLUMNS, UNIQUE_KEY  # noqa: E402
from writers.postgres_writer import UPSERT_PROMPT_LOG_PG  # noqa: E402


def _make_sample_file(tmpdir: Path) -> Path:
    """One prompt-log .json.gz with a single valid record."""
    rec = {
        "records": [{
            "generateAssistantResponseEventRequest": {
                "userId": "d-abc123.11112222-3333-4444-5555-666677778888",
                "prompt": "--- USER MESSAGE BEGIN ---\nhello\n--- USER MESSAGE END ---",
                "timeStamp": "2026-08-22T10:11:12.345678900Z",
                "modelId": "claude-sonnet",
                "chatTriggerType": "MANUAL",
            },
            "generateAssistantResponseEventResponse": {
                "requestId": "req-0001",
                "assistantResponse": "here is code:\n```py\nprint(1)\n```",
                "codeReferenceEvents": [{"a": 1}],
            },
        }]
    }
    p = tmpdir / "sample.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as gz:
        json.dump(rec, gz)
    return p


def test_tuple_matches_columns():
    with tempfile.TemporaryDirectory() as d:
        f = _make_sample_file(Path(d))
        rows = parse_prompt_log_file(f, "111111111111", "prod", store_text=True)
    assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
    row = rows[0]
    assert len(row) == len(PROMPT_LOG_COLUMNS), (
        f"tuple has {len(row)} fields but PROMPT_LOG_COLUMNS has "
        f"{len(PROMPT_LOG_COLUMNS)} — they MUST match in order"
    )
    # Spot-check that named columns line up with expected values by position.
    d = dict(zip(PROMPT_LOG_COLUMNS, row))
    assert d["aws_account_id"] == "111111111111"
    assert d["request_id"] == "req-0001"
    assert d["user_id_normalized"] == "abc123-11112222-3333-4444-5555-666677778888", d["user_id_normalized"]
    assert d["has_code_in_response"] == 1
    assert d["code_reference_count"] == 1
    assert d["source_file"] == "sample.json.gz"
    print("OK: tuple order matches PROMPT_LOG_COLUMNS")


def test_mysql_sql_placeholder_count():
    n = UPSERT_PROMPT_LOG.count("%s")
    assert n == len(PROMPT_LOG_COLUMNS), (
        f"MySQL UPSERT has {n} placeholders but {len(PROMPT_LOG_COLUMNS)} columns"
    )
    print("OK: MySQL upsert placeholder count matches")


def test_postgres_sql_generated_from_columns():
    n = UPSERT_PROMPT_LOG_PG.count("%s")
    assert n == len(PROMPT_LOG_COLUMNS), (
        f"Postgres UPSERT has {n} placeholders but {len(PROMPT_LOG_COLUMNS)} columns"
    )
    # every non-key column must appear in the DO UPDATE SET clause
    for c in PROMPT_LOG_COLUMNS:
        if c in UNIQUE_KEY:
            continue
        assert re.search(rf"\b{c} = EXCLUDED\.{c}\b", UPSERT_PROMPT_LOG_PG), (
            f"Postgres upsert missing update for column {c}"
        )
    print("OK: Postgres upsert generated correctly from PROMPT_LOG_COLUMNS")


if __name__ == "__main__":
    test_tuple_matches_columns()
    test_mysql_sql_placeholder_count()
    test_postgres_sql_generated_from_columns()
    print("\nAll backend-contract checks passed.")
