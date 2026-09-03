#!/usr/bin/env python3
"""Kiro Usage Analytics — multi-account sync and multi-backend orchestrator.

Overview:
  This module coordinates the end-to-end telemetry pipeline for Kiro (Amazon Q Developer):
  1. Retention sweep: Removes local raw files older than DATA_RETENTION_DAYS (default 30).
  2. S3 Sync: Incrementally pulls raw daily CSV reports and gzipped JSON prompt logs.
  3. Parsing & Normalization: Extracts metrics and normalizes Identity Center user IDs.
  4. Backend Ingestion: Upserts data into the selected database (MySQL, PostgreSQL, ClickHouse,
     OpenSearch, or Elasticsearch) using deterministic unique keys to prevent duplicate records.

Supported Datasets:
  - user_report: 35 columns (Date, UserId, Client_Type, Credits, Tier, 20 AI model metrics).
  - by_user_analytic: 48 columns (granular counts for chat, code fix, docgen, testgen, dev cycles).
  - prompt_logs: 17 columns (request IDs, normalized user IDs, model IDs, token/character lengths,
    code indicators, and raw prompt/response text).

Supported Storage Backends:
  - mysql: Relational aggregation, SQL joins, default backend.
  - postgres: Relational metrics, advanced SQL, JSONB support.
  - clickhouse: Columnar high-speed queries across hundreds of thousands of prompt events.
  - opensearch: Full-text search and discovery over prompt/response text, Dashboards UI.
  - elasticsearch: Full-text search and analytical log indexing for Elastic stack users.

CLI Syntax:
  python main.py [--account PROFILE] [--dataset DATASET] [--load-only] [--date YYYY-MM-DD]
                 [--backend BACKEND] [--store-text] [--force] [--full]

Options:
  --account      AWS profile name configured in conf/accounts.json. Defaults to DEFAULT_AWS_PROFILE.
  --dataset      Which dataset to process: all (default) | user_report | by_user_analytic | prompt_logs.
  --load-only    Skip S3 download and load existing local files directly into backend (fast/offline).
  --date         Scope S3 sync and backend load to a specific day (YYYY-MM-DD).
  --backend      Target database: mysql | postgres | opensearch | elasticsearch | clickhouse.
  --store-text   Store full prompt/response text in SQL backends (search backends always store text).
  --force        Reset sync state and re-download files for target date.
  --full         Re-parse ALL local files into DB ignoring --date filter.

Examples:
  # Ingest ALL 3 datasets for a specific date into OpenSearch
  python main.py --account 073885930324_AdministratorAccess --backend opensearch --date 2026-08-22

  # Ingest ONLY prompt logs for a specific date into ClickHouse
  python main.py --account 073885930324_AdministratorAccess --backend clickhouse --dataset prompt_logs --date 2026-08-22

  # Ingest ONLY user_report CSVs directly from local disk (zero S3 calls) into Postgres
  python main.py --account 073885930324_AdministratorAccess --backend postgres --dataset user_report --load-only
"""

import argparse
import gzip
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from conf.config import ACCOUNTS, STORAGE_BACKEND, get_account_config, get_account_data_dir
from s3_sync import sync_all
from writers import (
    _USER_REPORT_MODELS,
    BY_USER_ANALYTIC,
    PROMPT_LOG,
    USER_REPORT,
    get_writer,
)

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
    """Parse a user_report CSV into 35-element tuples ready for database upsert.

    Extracts core subscription attributes (credits used, tier, client type, conversations)
    plus message counts across all 20 active AI models (Claude Opus/Sonnet/Haiku, GPT, DeepSeek,
    GLM, Minimax, Qwen). Column names are matched case-insensitively with dot-to-underscore mapping.
    """
    try:
        df = pd.read_csv(filepath, dtype=str)
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return []

    # Map normalized column names (lowercase with underscores) to their raw CSV header names
    # e.g. 'claude_opus_4.6_messages' or 'CLAUDE_SONNET_4_20250514_V1_0_messages' -> 'claude_opus_4_6_messages'
    col_map = {col.lower().replace(".", "_"): col for col in df.columns}

    rows = []
    for _, r in df.iterrows():
        base_tuple = [
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
        ]
        for m_col in _USER_REPORT_MODELS:
            raw_col = col_map.get(m_col)
            val = r.get(raw_col) if raw_col else None
            base_tuple.append(_safe_int(val))

        rows.append(tuple(base_tuple))
    return rows


def parse_by_user_analytic_csv(filepath: Path, account_id: str, account_label: str) -> list[tuple]:
    """Parse a by_user_analytic CSV into 48-element tuples ready for database upsert.

    Extracts detailed telemetry across all developer features: Chat, CodeFix, CodeReview,
    Dev, DocGeneration, InlineChat, Inline suggestions, TestGeneration, and Transformation.
    """
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

    In prompt_logs, the format is d-<idc>.<user_id_in_user_report>.
    Extracts the user_id suffix after '.' to match user_id in kiro_user_report.
    Leaves already-normalized IDs unchanged.
    """
    if not user_id:
        return ""
    if "." in user_id:
        return user_id.split(".", 1)[1]
    if user_id.startswith("d-"):
        return user_id[2:]
    return user_id


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
    """Parse one prompt_log .json.gz file into 17-element tuples ready for upsert.

    Extracts request ID, raw userId, normalized userId for SQL/Search joins, event
    timestamps (with millisecond precision), model ID, trigger type, character counts,
    code generation indicators, and optionally the full raw prompt/response text.
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


def _load_prompt_logs(writer, account_id: str, account_label: str,
                      store_text: bool, is_search: bool, target_date: str | None = None) -> int:
    """Stream prompt_log files through `writer` in bounded batches (1,000 rows/batch).

    Scans local `data/<account_id>/prompt_logs/*.json.gz`. When `target_date` is given,
    only files matching YYYYMMDD are parsed. Flushes in batches to keep memory consumption
    strictly bounded when processing high-volume accounts (300k+ files).
    """
    prompt_dir = get_account_data_dir(account_id) / "prompt_logs"
    if not prompt_dir.exists():
        return 0
    # Search engines exist to search text — always keep it for those backends.
    store_text = store_text or is_search

    total = 0
    batch = []
    files = sorted(prompt_dir.glob("*.json.gz"))
    if target_date:
        date_str = target_date.replace("-", "")
        files = [f for f in files if date_str in f.name]

    for f in files:
        batch.extend(parse_prompt_log_file(f, account_id, account_label, store_text))
        # flush in batches to keep memory bounded on large corpora (300k+ files)
        if len(batch) >= 1000:
            total += writer.write(PROMPT_LOG, batch)
            batch = []
    if batch:
        total += writer.write(PROMPT_LOG, batch)
    return total


def load_all(account_id: str, account_label: str, backend: str = "mysql",
             prompt_logs: bool = False, store_text: bool = False,
             dataset: str = "all", target_date: str | None = None) -> dict:
    """Parse and load local data for one account into `backend`.

    dataset: "all" (default, loads all 3 datasets) | "user_report" | "by_user_analytic" | "prompt_logs"
    target_date: YYYY-MM-DD to load only files for that date (or None for all files).
    backend: mysql | postgres | opensearch | elasticsearch | clickhouse.

    Creates schemas lazily via writer on first write. Uses deterministic unique keys
    for idempotency (re-running overwrites/updates without creating duplicate documents).
    """
    account_data_dir = get_account_data_dir(account_id)
    is_search = backend in ("opensearch", "elasticsearch", "elastic", "es")
    result = {"backend": backend, "dataset": dataset}
    date_str = target_date.replace("-", "") if target_date else None

    try:
        writer_ctx = get_writer(backend)
    except Exception as e:
        logger.error(
            f"\n{'!'*60}\n"
            f"Failed to initialize '{backend}' writer: {e}\n"
            f"Quick start with Docker Compose:\n"
            f"  docker compose -f deploy/compose/docker-compose.{backend}.yml up -d\n"
            f"{'!'*60}\n"
        )
        sys.exit(1)

    try:
        with writer_ctx as writer:
            # user_report
            if dataset in ("all", "user_report"):
                result["user_report_rows"] = 0
                ur_dir = account_data_dir / "user_report"
                if ur_dir.exists():
                    files = sorted(ur_dir.glob("*.csv"))
                    if date_str:
                        files = [f for f in files if date_str in f.name]
                    for f in files:
                        rows = parse_user_report_csv(f, account_id, account_label)
                        result["user_report_rows"] += writer.write(USER_REPORT, rows)

            # by_user_analytic
            if dataset in ("all", "by_user_analytic"):
                result["by_user_analytic_rows"] = 0
                an_dir = account_data_dir / "by_user_analytic"
                if an_dir.exists():
                    files = sorted(an_dir.glob("*.csv"))
                    if date_str:
                        files = [f for f in files if date_str in f.name]
                    for f in files:
                        rows = parse_by_user_analytic_csv(f, account_id, account_label)
                        result["by_user_analytic_rows"] += writer.write(BY_USER_ANALYTIC, rows)

            # prompt_log: strictly obey dataset filter or explicit prompt_logs flag
            if dataset in ("all", "prompt_logs") or (prompt_logs and dataset == "all"):
                result["prompt_log_rows"] = _load_prompt_logs(
                    writer, account_id, account_label, store_text, is_search, target_date=target_date)
    except Exception as e:
        err_str = str(e).lower()
        if any(term in err_str for term in ("connection refused", "cannot connect", "failed to connect", "not reachable", "operationalerror")):
            logger.error(
                f"\n{'!'*60}\n"
                f"Could not connect to '{backend}' backend: {e}\n"
                f"Please verify your database service is running.\n"
                f"Quick start with Docker Compose:\n"
                f"  docker compose -f deploy/compose/docker-compose.{backend}.yml up -d\n"
                f"{'!'*60}\n"
            )
            sys.exit(1)
        raise

    return result


def run(account: str | None = None, full_reload: bool = False, force: bool = False,
        target_date: str | None = None, prompt_logs: bool = False, store_text: bool = False,
        backend: str = "mysql", dataset: str = "all", load_only: bool = False):
    """Main orchestrator for a single AWS account.

    Coordinates incremental S3 downloads (or bypasses via load_only) and pushes
    parsed records into the configured storage backend.
    """
    cfg = get_account_config(account)
    logger.info(f"=== Kiro Usage Analytics Sync: {cfg['label']} ({cfg['account_id']}) "
                f"[backend={backend}, dataset={dataset}] ===")

    if load_only:
        sync_result = {"skipped": True, "reason": "--load-only specified"}
        logger.info("S3 sync skipped (--load-only)")
    else:
        try:
            sync_result = sync_all(profile=cfg["profile"], force=force, target_date=target_date,
                                   prompt_logs=prompt_logs, dataset=dataset)
            logger.info(f"S3 sync: {sync_result}")
        except Exception as e:
            err_msg = str(e)
            if "ExpiredToken" in err_msg or "token has expired" in err_msg.lower():
                logger.error(
                    f"\n{'!'*60}\n"
                    f"AWS session token has expired for profile '{cfg['profile']}'.\n"
                    f"  1. Refresh your session: aws sso login --profile {cfg['profile']}\n"
                    f"  2. Or load already-downloaded local data without S3: re-run with --load-only\n"
                    f"{'!'*60}\n"
                )
                sys.exit(1)
            elif "NoCredentialsError" in err_msg:
                logger.error(
                    f"\n{'!'*60}\n"
                    f"No AWS credentials found for profile '{cfg['profile']}'.\n"
                    f"  1. Login via AWS: aws sso login --profile {cfg['profile']}\n"
                    f"  2. Or load already-downloaded local data without S3: re-run with --load-only\n"
                    f"{'!'*60}\n"
                )
                sys.exit(1)
            raise

    # If full_reload is True, target_date filter is ignored during load to parse all local files
    load_date = None if full_reload else target_date
    load_result = load_all(cfg["account_id"], cfg["label"], backend=backend,
                           prompt_logs=prompt_logs, store_text=store_text,
                           dataset=dataset, target_date=load_date)

    logger.info(f"DB load: {load_result}")
    logger.info("=== Done ===")
    return {"account": cfg["account_id"], "label": cfg["label"], "sync": sync_result, "load": load_result}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Kiro Usage Analytics - S3 to (MySQL/Postgres/OpenSearch/Elasticsearch/ClickHouse) sync")
    parser.add_argument("--account", type=str, default=None,
                        help="AWS profile name to sync, or 'all' to process all configured accounts. Defaults to DEFAULT_AWS_PROFILE.")
    parser.add_argument("--dataset", type=str, default="all",
                        choices=["all", "user_report", "by_user_analytic", "prompt_logs"],
                        help="Specific dataset to sync and load (default: all — syncs and loads all 3 datasets).")
    parser.add_argument("--load-only", "--no-sync", dest="load_only", action="store_true",
                        help="Skip S3 download and only load existing local files into the backend.")
    parser.add_argument("--full", action="store_true", help="Full reload all local CSVs into DB for this account")
    parser.add_argument("--force", action="store_true", help="Reset sync state and re-download files from S3")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date (YYYY-MM-DD). Scopes S3 download and DB load to this day.")
    parser.add_argument("--prompt-logs", action="store_true",
                        help="Explicitly include prompt logs (backwards-compatible alias for --dataset all / --dataset prompt_logs).")
    parser.add_argument("--store-text", action="store_true",
                        help="Store full prompt/response text in SQL backends (default: metadata only; search backends always store text).")
    parser.add_argument("--backend", type=str, default=STORAGE_BACKEND,
                        choices=["mysql", "postgres", "opensearch", "elasticsearch", "clickhouse"],
                        help="Storage backend: mysql | postgres | opensearch | elasticsearch | clickhouse (default: STORAGE_BACKEND env).")
    args = parser.parse_args()

    # Reconcile dataset flag with legacy --prompt-logs
    if args.dataset != "all":
        effective_prompt_logs = (args.dataset == "prompt_logs")
    else:
        effective_prompt_logs = args.prompt_logs

    if args.account == "all":
        batch_results = {}
        for profile in ACCOUNTS.keys():
            logger.info(f"\n{'='*70}\nProcessing account: {profile}\n{'='*70}")
            try:
                batch_results[profile] = run(
                    account=profile, full_reload=args.full, force=args.force,
                    target_date=args.date, prompt_logs=effective_prompt_logs, store_text=args.store_text,
                    backend=args.backend, dataset=args.dataset, load_only=args.load_only
                )
            except Exception as e:
                logger.error(f"Failed processing account '{profile}': {e}")
                batch_results[profile] = {"error": str(e)}
        print(f"\nBatch Results across {len(batch_results)} account(s):\n{json.dumps(batch_results, indent=2, default=str)}")
    else:
        result = run(
            account=args.account, full_reload=args.full, force=args.force,
            target_date=args.date, prompt_logs=effective_prompt_logs, store_text=args.store_text,
            backend=args.backend, dataset=args.dataset, load_only=args.load_only
        )
        print(f"\nResult: {result}")
