#!/usr/bin/env python3
"""Kiro Usage Analytics — main orchestrator.

Workflow:
  1. Enforce data retention (delete local files older than DATA_RETENTION_DAYS)
  2. Sync new CSVs from S3 for the selected AWS account (incremental, idempotent)
  3. Parse CSVs into rows (tagged with aws_account_id / account_label)
  4. Upsert into MySQL

Run: python main.py [--account PROFILE] [--full] [--force] [--date YYYY-MM-DD]
                    [--prompt-logs] [--store-text] [--backend BACKEND]
  --account      AWS profile name (see conf/accounts.json). Defaults to DEFAULT_AWS_PROFILE.
  --full         Re-parse ALL local CSVs into DB for this account
  --force        Reset sync state and re-download files (today, or --date if given)
  --date         Target date to re-download (YYYY-MM-DD), used with --force
  --prompt-logs  Download prompt logs AND load their metadata into the selected backend
  --store-text   Store full prompt/response text (default: metadata only; implied for search backends)
  --backend      Prompt-log store: mysql|postgres|opensearch|elasticsearch|clickhouse (default mysql)

Examples:
  python main.py --account 111111111111_AdministratorAccess
  python main.py --account 222222222222_AdministratorAccess --force --date 2026-08-20
  python main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22
  python main.py --account 222222222222_AdministratorAccess --prompt-logs --store-text --date 2026-08-22
  python main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22 --backend opensearch
  python main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22 --backend clickhouse
"""

import argparse
import gzip
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from conf.config import PROMPT_LOG_BACKEND, get_account_config, get_account_data_dir
from db import (
    get_connection,
    init_schema,
    upsert_by_user_analytic_rows,
    upsert_user_report_rows,
)
from s3_sync import sync_all
from writers import get_writer

logger = logging.getLogger(__name__)


def _parse_bool(val) -> int:
    """Convert various boolean representations to 0/1."""
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, str):
        return 1 if val.lower() in ("true", "1", "yes") else 0
    return int(bool(val))


def _safe_int(val, default=0) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _parse_date(val) -> str:
    """Normalize date string to YYYY-MM-DD."""
    if not val:
        return None
    val = str(val).strip()
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(val, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val


def parse_user_report_csv(filepath: Path, account_id: str, account_label: str) -> list[tuple]:
    """Parse a user_report CSV into tuples ready for upsert, tagged with account info."""
    try:
        df = pd.read_csv(filepath, dtype=str)
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return []

    rows = []
    for _, r in df.iterrows():
        rows.append((
            account_id,
            account_label,
            _parse_date(r.get("Date")),
            r.get("UserId", "").strip('"'),
            r.get("User_Email", ""),
            r.get("Client_Type", ""),
            _safe_int(r.get("Chat_Conversations")),
            _safe_float(r.get("Credits_Used")),
            _safe_float(r.get("Overage_Cap")),
            _safe_float(r.get("Overage_Credits_Used")),
            _parse_bool(r.get("Overage_Enabled", "false")),
            r.get("ProfileId", ""),
            r.get("Subscription_Tier", ""),
            _safe_int(r.get("Total_Messages")),
            _parse_bool(r.get("New_User", "false")),
            _safe_int(r.get("auto_messages")),
            _safe_int(r.get("claude_opus_4.6_messages", r.get("claude_opus_4_6_messages"))),
            _safe_int(r.get("claude_opus_4.8_messages", r.get("claude_opus_4_8_messages"))),
        ))
    return rows


def parse_by_user_analytic_csv(filepath: Path, account_id: str, account_label: str) -> list[tuple]:
    """Parse a by_user_analytic CSV into tuples ready for upsert, tagged with account info."""
    try:
        df = pd.read_csv(filepath, dtype=str)
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return []

    rows = []
    for _, r in df.iterrows():
        rows.append((
            account_id,
            account_label,
            r.get("UserId", "").strip('"'),
            _parse_date(r.get("Date")),
            _safe_int(r.get("Chat_AICodeLines")),
            _safe_int(r.get("Chat_MessagesInteracted")),
            _safe_int(r.get("Chat_MessagesSent")),
            _safe_int(r.get("CodeFix_AcceptanceEventCount")),
            _safe_int(r.get("CodeFix_AcceptedLines")),
            _safe_int(r.get("CodeFix_GeneratedLines")),
            _safe_int(r.get("CodeFix_GenerationEventCount")),
            _safe_int(r.get("CodeReview_FailedEventCount")),
            _safe_int(r.get("CodeReview_FindingsCount")),
            _safe_int(r.get("CodeReview_SucceededEventCount")),
            _safe_int(r.get("Dev_AcceptanceEventCount")),
            _safe_int(r.get("Dev_AcceptedLines")),
            _safe_int(r.get("Dev_GeneratedLines")),
            _safe_int(r.get("Dev_GenerationEventCount")),
            _safe_int(r.get("DocGeneration_AcceptedFileUpdates")),
            _safe_int(r.get("DocGeneration_AcceptedFilesCreations")),
            _safe_int(r.get("DocGeneration_AcceptedLineAdditions")),
            _safe_int(r.get("DocGeneration_AcceptedLineUpdates")),
            _safe_int(r.get("DocGeneration_EventCount")),
            _safe_int(r.get("DocGeneration_RejectedFileCreations")),
            _safe_int(r.get("DocGeneration_RejectedFileUpdates")),
            _safe_int(r.get("DocGeneration_RejectedLineAdditions")),
            _safe_int(r.get("DocGeneration_RejectedLineUpdates")),
            _safe_int(r.get("InlineChat_AcceptanceEventCount")),
            _safe_int(r.get("InlineChat_AcceptedLineAdditions")),
            _safe_int(r.get("InlineChat_AcceptedLineDeletions")),
            _safe_int(r.get("InlineChat_DismissalEventCount")),
            _safe_int(r.get("InlineChat_DismissedLineAdditions")),
            _safe_int(r.get("InlineChat_DismissedLineDeletions")),
            _safe_int(r.get("InlineChat_RejectedLineAdditions")),
            _safe_int(r.get("InlineChat_RejectedLineDeletions")),
            _safe_int(r.get("InlineChat_RejectionEventCount")),
            _safe_int(r.get("InlineChat_TotalEventCount")),
            _safe_int(r.get("Inline_AICodeLines")),
            _safe_int(r.get("Inline_AcceptanceCount")),
            _safe_int(r.get("Inline_SuggestionsCount")),
            _safe_int(r.get("TestGeneration_AcceptedLines")),
            _safe_int(r.get("TestGeneration_AcceptedTests")),
            _safe_int(r.get("TestGeneration_EventCount")),
            _safe_int(r.get("TestGeneration_GeneratedLines")),
            _safe_int(r.get("TestGeneration_GeneratedTests")),
            _safe_int(r.get("Transformation_EventCount")),
            _safe_int(r.get("Transformation_LinesGenerated")),
            _safe_int(r.get("Transformation_LinesIngested")),
        ))
    return rows


def _normalize_user_id(user_id: str) -> str:
    """Convert prompt_log userId to user_report form for JOINs.

    prompt_logs: d-<idc>.<uuid>   ->   user_report: <idc>-<uuid>
    Leaves already-normalized IDs unchanged.
    """
    if not user_id:
        return ""
    uid = user_id
    if uid.startswith("d-"):
        uid = uid[2:]
    # replace the first "." (idc/uuid separator) with "-"
    return uid.replace(".", "-", 1)


def _extract_user_message(prompt: str) -> str:
    """Return the text between USER MESSAGE markers, or the whole prompt if absent."""
    if not prompt:
        return ""
    begin = "--- USER MESSAGE BEGIN ---"
    end = "--- USER MESSAGE END ---"
    if begin in prompt and end in prompt:
        return prompt.split(begin, 1)[1].split(end, 1)[0].strip()
    return prompt


def _parse_event_time(ts: str) -> tuple[str, str]:
    """Parse an ISO8601 timestamp into (datetime_str 'YYYY-MM-DD HH:MM:SS.mmm', date_str).

    Handles nanosecond precision (trims to milliseconds for MySQL DATETIME(3)).
    """
    if not ts:
        return None, None
    clean = ts.rstrip("Z")
    # split fractional seconds; keep only 3 digits (ms) for MySQL
    if "." in clean:
        base, frac = clean.split(".", 1)
        frac = frac[:3].ljust(3, "0")
        clean = f"{base}.{frac}"
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
    else:
        fmt = "%Y-%m-%dT%H:%M:%S"
    try:
        dt = datetime.strptime(clean, fmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], dt.strftime("%Y-%m-%d")
    except ValueError:
        return None, None


def parse_prompt_log_file(filepath: Path, account_id: str, account_label: str,
                          store_text: bool = False) -> list[tuple]:
    """Parse one prompt_log .json.gz file into rows ready for upsert.

    A single file may contain multiple records. Column order must match
    db.UPSERT_PROMPT_LOG.
    """
    try:
        with gzip.open(filepath, "rt", encoding="utf-8") as gz:
            data = json.load(gz)
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return []

    rows = []
    for rec in data.get("records", []):
        req = rec.get("generateAssistantResponseEventRequest", {})
        resp = rec.get("generateAssistantResponseEventResponse", {})

        request_id = resp.get("requestId")
        if not request_id:
            continue  # can't dedupe without a request id — skip

        user_id = req.get("userId", "")
        prompt = req.get("prompt", "") or ""
        response = resp.get("assistantResponse", "") or ""
        event_time, event_date = _parse_event_time(req.get("timeStamp", ""))
        if not event_time:
            continue  # skip records without a usable timestamp

        rows.append((
            account_id,
            account_label,
            request_id,
            user_id,
            _normalize_user_id(user_id),
            event_time,
            event_date,
            req.get("modelId"),
            req.get("chatTriggerType"),
            len(prompt),
            len(_extract_user_message(prompt)),
            len(response),
            1 if "```" in response else 0,
            len(resp.get("codeReferenceEvents") or []),
            prompt if store_text else None,
            response if store_text else None,
            filepath.name,
        ))
    return rows


def load_all_prompt_logs(account_id: str, account_label: str, store_text: bool = False,
                         backend: str = "mysql") -> int:
    """Parse and load ALL local prompt_log files for one account into `backend`.

    data/<account_id>/prompt_logs/*.json.gz

    backend: mysql | postgres | opensearch | elasticsearch | clickhouse.
    Search backends index full text regardless of store_text (that's their point).
    """
    prompt_dir = get_account_data_dir(account_id) / "prompt_logs"
    if not prompt_dir.exists():
        return 0

    # Search engines exist to search text — always keep it for those backends.
    if backend in ("opensearch", "elasticsearch", "elastic", "es"):
        store_text = True

    total = 0
    with get_writer(backend) as writer:
        writer.init_schema()
        batch = []
        for f in sorted(prompt_dir.glob("*.json.gz")):
            batch.extend(parse_prompt_log_file(f, account_id, account_label, store_text))
            # flush in batches to keep memory bounded on large corpora (300k+ files)
            if len(batch) >= 1000:
                total += writer.write(batch)
                batch = []
        if batch:
            total += writer.write(batch)

    return total


def load_all_local_csvs(account_id: str, account_label: str) -> dict:
    """Parse and upsert ALL local CSVs for one account (full reload mode).

    Flat layout (Option D), per-account:
      data/<account_id>/user_report/*.csv
      data/<account_id>/by_user_analytic/*.csv
    """
    account_data_dir = get_account_data_dir(account_id)
    user_report_dir = account_data_dir / "user_report"
    analytic_dir = account_data_dir / "by_user_analytic"

    conn = get_connection()
    try:
        total_ur = 0
        if user_report_dir.exists():
            for f in sorted(user_report_dir.glob("*.csv")):
                rows = parse_user_report_csv(f, account_id, account_label)
                upsert_user_report_rows(rows, conn=conn)
                total_ur += len(rows)

        total_an = 0
        if analytic_dir.exists():
            for f in sorted(analytic_dir.glob("*.csv")):
                rows = parse_by_user_analytic_csv(f, account_id, account_label)
                upsert_by_user_analytic_rows(rows, conn=conn)
                total_an += len(rows)
    finally:
        conn.close()

    return {"user_report_rows": total_ur, "by_user_analytic_rows": total_an}


def run(account: str | None = None, full_reload: bool = False, force: bool = False,
        target_date: str | None = None, prompt_logs: bool = False, store_text: bool = False,
        backend: str = "mysql"):
    """Main entry point for a single AWS account."""
    cfg = get_account_config(account)
    logger.info(f"=== Kiro Usage Analytics Sync: {cfg['label']} ({cfg['account_id']}) ===")

    # CSV report tables always live in MySQL; only prompt logs are backend-selectable.
    init_schema()

    sync_result = sync_all(profile=cfg["profile"], force=force, target_date=target_date, prompt_logs=prompt_logs)
    logger.info(f"S3 sync: {sync_result}")

    # ponytail: always reload all local CSVs for this account (small file counts,
    # simplest correct option for daily cron); --full is kept as an explicit alias
    load_result = load_all_local_csvs(cfg["account_id"], cfg["label"])

    # Load prompt log metadata only when prompt logs were requested (opt-in — the
    # dev corpus is 300k+ files, so we don't scan it on every ordinary sync).
    if prompt_logs:
        prompt_rows = load_all_prompt_logs(cfg["account_id"], cfg["label"],
                                           store_text=store_text, backend=backend)
        load_result["prompt_log_rows"] = prompt_rows
        load_result["prompt_log_backend"] = backend

    logger.info(f"DB load: {load_result}")
    logger.info("=== Done ===")
    return {"account": cfg["account_id"], "label": cfg["label"], "sync": sync_result, "load": load_result}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Kiro Usage Analytics - S3 to MySQL sync")
    parser.add_argument("--account", type=str, default=None,
                        help="AWS profile name to sync (see conf/config.py ACCOUNTS). Defaults to DEFAULT_AWS_PROFILE.")
    parser.add_argument("--full", action="store_true", help="Full reload all local CSVs into DB for this account")
    parser.add_argument("--force", action="store_true", help="Reset sync state and re-download files from S3")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date to re-download (YYYY-MM-DD). Used with --force to re-fetch a specific day.")
    parser.add_argument("--prompt-logs", action="store_true",
                        help="Also download prompt logs (.json.gz) AND load their metadata into kiro_prompt_log. Use with --date to limit scope.")
    parser.add_argument("--store-text", action="store_true",
                        help="Store full prompt/response text in the DB (default: metadata only, text stays NULL and is read from files).")
    parser.add_argument("--backend", type=str, default=PROMPT_LOG_BACKEND,
                        choices=["mysql", "postgres", "opensearch", "elasticsearch", "clickhouse"],
                        help="Storage backend for prompt logs (default: PROMPT_LOG_BACKEND env or mysql). "
                             "CSV report tables always use MySQL.")
    args = parser.parse_args()

    result = run(account=args.account, full_reload=args.full, force=args.force,
                 target_date=args.date, prompt_logs=args.prompt_logs, store_text=args.store_text,
                 backend=args.backend)
    print(f"\nResult: {result}")
