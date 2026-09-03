"""Incremental S3 sync — downloads Kiro (Amazon Q Developer) reports and prompt logs from S3.

Overview:
  This module pulls raw telemetry and usage data from Amazon S3 buckets down to the local
  filesystem (`data/<account_id>/...`). It operates strictly as a downloader; database loading
  and schema upserts are handled downstream by `main.py`.

What it downloads:
  1. user_report:
     - Daily CSVs per client type (`KIRO_IDE`, `KIRO_CLI`, `PLUGIN`).
     - Contains per-user credit consumption, subscription tier, and model message counts.
     - S3 path: .../AWSLogs/<account>/KiroLogs/user_report/us-east-1/<YYYY>/<MM>/<DD>/00/...
     - Local dest: data/<account_id>/user_report/<original_filename>.csv
  2. by_user_analytic:
     - Daily CSVs detailing 46 granular feature metrics (chat, code fix, docgen, testgen).
     - S3 path: .../AWSLogs/<account>/KiroLogs/by_user_analytic/us-east-1/<YYYY>/<MM>/<DD>/00/...
     - Local dest: data/<account_id>/by_user_analytic/<original_filename>.csv
  3. prompt_logs (opt-in via --prompt-logs):
     - High-volume gzipped JSON files (`.json.gz`) containing prompt and response conversation records.
     - S3 path: .../AWSLogs/<account>/KiroLogs/GenerateAssistantResponse/us-east-1/<YYYY>/<MM>/<DD>/<HH>/...
     - Local dest: data/<account_id>/prompt_logs/<original_filename>.json.gz

How it works:
  1. Retention Sweep:
     - Inspects local files in `data/<account_id>/` and deletes any file older than
       DATA_RETENTION_DAYS (default 30, configured in `conf/.env.kiro`).
     - Cleans purged files from state tracking.
  2. S3 Object Listing & Prefix Optimization:
     - Uses boto3 S3 client authenticated via AWS SSO profiles or IAM roles.
     - When `--date YYYY-MM-DD` is supplied, prefixes are narrowed to `<prefix>/YYYY/MM/DD/`
       so S3 only scans objects for that specific date (avoids listing hundreds of thousands of keys).
  3. Safe Download & Idempotency:
     - Before downloading each object, checks if the file already exists locally and is non-empty (`st_size > 0`).
     - Skips already-downloaded files unless `--force` is specified.
     - Tracks downloaded filenames in `data/<account_id>/.sync_state.json`.

What happens if run multiple times? (Idempotency guarantee):
  - Running repeatedly for the same date or without flags is 100% safe and idempotent.
  - Zero redundant downloads: Files already on disk are detected immediately and skipped (consuming 0 bandwidth).
  - Zero duplicate database entries: Downstream storage writers use deterministic unique keys
    (or document IDs in OpenSearch/Elasticsearch), ensuring re-runs overwrite in-place without duplicating.
  - Re-downloading on demand: Passing `--force --date YYYY-MM-DD` deletes the local copies
    for that specific date and re-fetches clean copies from S3.

CLI Usage:
  # Incremental sync (only new CSV reports since last run)
  python s3_sync.py --account <profile>

  # Download reports for a specific calendar day
  python s3_sync.py --account <profile> --date 2026-08-22

  # Download prompt logs for a specific day (strongly recommended over syncing all prompt logs)
  python s3_sync.py --account <profile> --prompt-logs --date 2026-08-22

  # Force re-download for a specific day (deletes local files for that day first)
  python s3_sync.py --account <profile> --force --date 2026-08-22
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import sys

import boto3

from conf.config import (
    ACCOUNTS,
    DATA_RETENTION_DAYS,
    get_account_config,
    get_account_data_dir,
)

logger = logging.getLogger(__name__)


def _state_file(account_data_dir: Path) -> Path:
    return account_data_dir / ".sync_state.json"


def _get_s3_client(profile: str, region: str):
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("s3")


def _load_state(account_data_dir: Path) -> dict:
    sf = _state_file(account_data_dir)
    if sf.exists():
        state = json.loads(sf.read_text())
        # Migrate flat downloaded_files → per-type structure if needed
        if "downloaded_files" in state and "files" not in state:
            old_files = state.pop("downloaded_files")
            state["files"] = {
                "user_report": [f for f in old_files if "/user_report/" in f],
                "by_user_analytic": [f for f in old_files if "/by_user_analytic/" in f],
                "prompt_logs": [f for f in old_files if "/prompt_logs/" in f],
            }
        # Normalize all tracked files to filenames (immune to directory renames or moves)
        if "files" in state:
            for k in list(state["files"].keys()):
                state["files"][k] = sorted(list({Path(f).name for f in state["files"][k]}))
        return state
    return {
        "user_report_last": None,
        "by_user_analytic_last": None,
        "prompt_log_last": None,
        "files": {
            "user_report": [],
            "by_user_analytic": [],
            "prompt_logs": [],
        },
    }


def _save_state(account_data_dir: Path, state: dict):
    _state_file(account_data_dir).write_text(json.dumps(state, indent=2, default=str))


def reset_state(account_data_dir: Path):
    """Delete sync state to force full re-download on next run."""
    sf = _state_file(account_data_dir)
    if sf.exists():
        sf.unlink()
        logger.info("Sync state reset — next run will download all files")


# -- Retention --

def enforce_retention(account_data_dir: Path):
    """Delete local files older than DATA_RETENTION_DAYS."""
    cutoff = time.time() - (DATA_RETENTION_DAYS * 86400)
    deleted = 0
    for sub_dir in ("user_report", "by_user_analytic", "prompt_logs"):
        dir_path = account_data_dir / sub_dir
        if not dir_path.exists():
            continue
        for f in dir_path.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
                logger.info(f"Retention: deleted {f.name} (older than {DATA_RETENTION_DAYS}d)")

    if deleted:
        state = _load_state(account_data_dir)
        for sub_dir in ("user_report", "by_user_analytic", "prompt_logs"):
            dir_path = account_data_dir / sub_dir
            if dir_path.exists():
                state.setdefault("files", {})[sub_dir] = sorted(f.name for f in dir_path.iterdir() if f.is_file())
            else:
                state.setdefault("files", {})[sub_dir] = []
        _save_state(account_data_dir, state)

    logger.info(f"Retention check: {deleted} files deleted")
    return deleted


# -- S3 listing and download --

def _list_objects(s3, bucket: str, prefix: str, after_date: str | None = None, target_date: str | None = None) -> list[dict]:
    """List S3 objects with optional filters.

    after_date: only objects modified after this ISO timestamp (incremental sync)
    target_date: only objects whose S3 key contains this date path segment (YYYY/MM/DD)
    """
    date_segment = None
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            date_segment = f"/{dt.year}/{dt.month:02d}/{dt.day:02d}/"
        except ValueError:
            logger.error(f"Invalid --date format: {target_date}, expected YYYY-MM-DD")

    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if date_segment and date_segment not in key:
                continue

            if after_date and not target_date:
                obj_modified = obj["LastModified"].isoformat()
                if obj_modified <= after_date:
                    continue

            objects.append(obj)
    return objects


def _download_single(s3, bucket: str, obj: dict, dest_root: Path, force: bool) -> tuple[Path | None, str, bool]:
    """Download a single S3 object atomically.

    Returns (local_path, filename, was_downloaded).
    """
    key = obj["Key"]
    filename = key.rsplit("/", 1)[-1]
    if not filename:
        return None, "", False
    local_path = dest_root / filename

    obj_size = obj.get("Size")
    # Skip if file already exists locally and matches S3 size (avoids partial/corrupted files)
    if not force and local_path.exists():
        local_size = local_path.stat().st_size
        if (obj_size is not None and local_size == obj_size) or (obj_size is None and local_size > 0):
            return local_path, filename, False

    tmp_path = dest_root / f".{filename}.{os.getpid()}.tmp"
    try:
        s3.download_file(bucket, key, str(tmp_path))
        os.replace(tmp_path, local_path)
        return local_path, filename, True
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def _download_objects(s3, bucket: str, objects: list[dict], dest_root: Path,
                      file_type: str, force: bool = False, max_workers: int = 10) -> list[Path]:
    """Download objects flat into dest_root/ keeping original filename.

    Idempotent: skips files already on disk (tracked in state) unless force=True.
    Atomic: downloads to a temporary file then renames to avoid partial files on crash.
    Parallel: uses ThreadPoolExecutor for high throughput on large datasets.
    """
    downloaded = []
    dest_root.mkdir(parents=True, exist_ok=True)

    account_data_dir = dest_root.parent
    state = _load_state(account_data_dir)
    known_files = set(state.get("files", {}).get(file_type, []))

    total = len(objects)
    if total == 0:
        return downloaded

    workers = min(max_workers, total)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_obj = {
            executor.submit(_download_single, s3, bucket, obj, dest_root, force): obj
            for obj in objects
        }
        completed_count = 0
        for future in as_completed(future_to_obj):
            local_path, filename, was_downloaded = future.result()
            if not filename:
                continue
            known_files.add(filename)
            if was_downloaded and local_path:
                downloaded.append(local_path)
                completed_count += 1
                logger.info(f"[{completed_count}/{total}] {filename}")

    state.setdefault("files", {})[file_type] = sorted(known_files)
    _save_state(account_data_dir, state)

    return downloaded


def sync_user_reports(cfg: dict, s3=None, force: bool = False, target_date: str | None = None,
                      max_workers: int = 10) -> list[Path]:
    """Sync user_report CSVs (credits/subscription data) for one account."""
    if s3 is None:
        s3 = _get_s3_client(cfg["profile"], cfg["region"])
    account_data_dir = get_account_data_dir(cfg["account_id"])
    state = _load_state(account_data_dir)

    base_prefix = cfg["user_report_prefix"] + "user_report/"
    region = cfg.get("region", "us-east-1")
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            prefix = f"{base_prefix}{region}/{dt.year}/{dt.month:02d}/{dt.day:02d}/"
        except ValueError:
            prefix = base_prefix
        objects = _list_objects(s3, cfg["user_report_bucket"], prefix, after_date=None, target_date=None)
    else:
        after = None if force else state.get("user_report_last")
        objects = _list_objects(s3, cfg["user_report_bucket"], base_prefix, after_date=after, target_date=None)

    downloaded = _download_objects(
        s3, cfg["user_report_bucket"], objects, account_data_dir / "user_report",
        "user_report", force, max_workers=max_workers
    )

    if objects and not target_date:
        latest = max(o["LastModified"] for o in objects)
        state = _load_state(account_data_dir)
        state["user_report_last"] = latest.isoformat()
        _save_state(account_data_dir, state)

    logger.info(f"[{cfg['label']}] user_report: {len(downloaded)} new files downloaded")
    return downloaded


def sync_by_user_analytic(cfg: dict, s3=None, force: bool = False, target_date: str | None = None,
                          max_workers: int = 10) -> list[Path]:
    """Sync by_user_analytic CSVs (detailed feature usage) for one account."""
    if s3 is None:
        s3 = _get_s3_client(cfg["profile"], cfg["region"])
    account_data_dir = get_account_data_dir(cfg["account_id"])
    state = _load_state(account_data_dir)

    base_prefix = cfg["user_report_prefix"] + "by_user_analytic/"
    region = cfg.get("region", "us-east-1")
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            prefix = f"{base_prefix}{region}/{dt.year}/{dt.month:02d}/{dt.day:02d}/"
        except ValueError:
            prefix = base_prefix
        objects = _list_objects(s3, cfg["user_report_bucket"], prefix, after_date=None, target_date=None)
    else:
        after = None if force else state.get("by_user_analytic_last")
        objects = _list_objects(s3, cfg["user_report_bucket"], base_prefix, after_date=after, target_date=None)

    downloaded = _download_objects(
        s3, cfg["user_report_bucket"], objects, account_data_dir / "by_user_analytic",
        "by_user_analytic", force, max_workers=max_workers
    )

    if objects and not target_date:
        latest = max(o["LastModified"] for o in objects)
        state = _load_state(account_data_dir)
        state["by_user_analytic_last"] = latest.isoformat()
        _save_state(account_data_dir, state)

    logger.info(f"[{cfg['label']}] by_user_analytic: {len(downloaded)} new files downloaded")
    return downloaded


def sync_prompt_logs(cfg: dict, s3=None, force: bool = False, target_date: str | None = None,
                     max_workers: int = 10) -> list[Path]:
    """Sync prompt logs (gzipped JSON) for one account.

    Downloads to data/<account_id>/prompt_logs/<original_filename>.json.gz
    Opt-in via --prompt-logs flag (high file count: ~300k in dev).
    Supports --date to download only a specific day (strongly recommended for dev).
    """
    if s3 is None:
        s3 = _get_s3_client(cfg["profile"], cfg["region"])
    account_data_dir = get_account_data_dir(cfg["account_id"])
    state = _load_state(account_data_dir)

    after = None if force else state.get("prompt_log_last")
    base_prefix = cfg["prompt_log_prefix"] + "GenerateAssistantResponse/"
    region = cfg.get("region", "us-east-1")

    # Optimization: if target_date given, build a narrower S3 prefix to avoid listing 300k+ objects
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            # S3 path: .../GenerateAssistantResponse/<region>/YYYY/MM/DD/
            prefix = f"{base_prefix}{region}/{dt.year}/{dt.month:02d}/{dt.day:02d}/"
        except ValueError:
            prefix = base_prefix
        # No watermark filtering needed when targeting specific date
        objects = _list_objects(s3, cfg["prompt_log_bucket"], prefix, after_date=None, target_date=None)
    else:
        prefix = base_prefix
        objects = _list_objects(s3, cfg["prompt_log_bucket"], prefix, after_date=after, target_date=None)

    downloaded = _download_objects(
        s3, cfg["prompt_log_bucket"], objects, account_data_dir / "prompt_logs",
        "prompt_logs", force, max_workers=max_workers
    )

    if objects and not target_date:
        latest = max(o["LastModified"] for o in objects)
        state = _load_state(account_data_dir)
        state["prompt_log_last"] = latest.isoformat()
        _save_state(account_data_dir, state)

    logger.info(f"[{cfg['label']}] prompt_logs: {len(downloaded)} new files downloaded")
    return downloaded


def _remove_files_for_date(account_data_dir: Path, target_date: str, dataset: str = "all"):
    """Remove local files matching a target date (YYYYMMDD in filename) so --force re-downloads them."""
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_str = dt.strftime("%Y%m%d")
    removed = 0

    state = _load_state(account_data_dir)
    files = state.setdefault("files", {"user_report": [], "by_user_analytic": [], "prompt_logs": []})

    sub_dirs = ["user_report", "by_user_analytic", "prompt_logs"] if dataset == "all" else [dataset]

    for sub_dir in sub_dirs:
        dir_path = account_data_dir / sub_dir
        if not dir_path.exists():
            continue
        type_files = set(files.get(sub_dir, []))
        for f in dir_path.iterdir():
            if f.is_file() and date_str in f.name:
                type_files.discard(f.name)
                type_files.discard(str(f))
                f.unlink()
                removed += 1
                logger.info(f"Removed for re-download: {f.name}")
        files[sub_dir] = sorted(type_files)

    _save_state(account_data_dir, state)
    logger.info(f"Removed {removed} files for date {target_date} (dataset={dataset})")


def sync_all(profile: str | None = None, force: bool = False, target_date: str | None = None,
             prompt_logs: bool = False, dataset: str = "all", max_workers: int = 10) -> dict:
    """Run sync for one AWS account/profile: retention cleanup then incremental download.

    profile: AWS profile name (key in conf.config.ACCOUNTS). Defaults to DEFAULT_AWS_PROFILE.
    force: re-download files (for target_date, or today if --date not set)
    target_date: YYYY-MM-DD — only sync files for that specific day
    prompt_logs: if True, also download prompt log .json.gz files (or via --dataset prompt_logs)
    dataset: "all" (default) | "user_report" | "by_user_analytic" | "prompt_logs"
    max_workers: maximum parallel download threads (default: 10)
    """
    cfg = get_account_config(profile)
    account_data_dir = get_account_data_dir(cfg["account_id"])

    enforce_retention(account_data_dir)

    s3 = _get_s3_client(cfg["profile"], cfg["region"])

    if force and not target_date:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.info(f"--force without --date: targeting today ({target_date})")

    if force:
        _remove_files_for_date(account_data_dir, target_date, dataset=dataset)

    user_reports = []
    if dataset in ("all", "user_report"):
        user_reports = sync_user_reports(cfg, s3, force=force, target_date=target_date, max_workers=max_workers)

    analytics = []
    if dataset in ("all", "by_user_analytic"):
        analytics = sync_by_user_analytic(cfg, s3, force=force, target_date=target_date, max_workers=max_workers)

    prompt_log_count = 0
    if dataset in ("all", "prompt_logs") or prompt_logs:
        prompt_log_files = sync_prompt_logs(cfg, s3, force=force, target_date=target_date, max_workers=max_workers)
        prompt_log_count = len(prompt_log_files)

    return {
        "account": cfg["account_id"],
        "label": cfg["label"],
        "dataset": dataset,
        "user_report_files": len(user_reports),
        "by_user_analytic_files": len(analytics),
        "prompt_log_files": prompt_log_count,
        "target_date": target_date,
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Kiro S3 Sync")
    parser.add_argument("--account", type=str, default=None,
                        help="AWS profile name to sync, or 'all' to sync all configured accounts. Defaults to DEFAULT_AWS_PROFILE.")
    parser.add_argument("--dataset", type=str, default="all",
                        choices=["all", "user_report", "by_user_analytic", "prompt_logs"],
                        help="Specific dataset to sync (default: all).")
    parser.add_argument("--force", action="store_true", help="Re-download files for target date")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD). Defaults to today with --force.")
    parser.add_argument("--prompt-logs", action="store_true",
                        help="Also download prompt logs (.json.gz). Use with --date to limit scope.")
    parser.add_argument("--workers", type=int, default=10,
                        help="Max concurrent download workers (default: 10).")
    args = parser.parse_args()

    # Reconcile dataset flag with legacy --prompt-logs
    if args.dataset != "all":
        effective_prompt_logs = (args.dataset == "prompt_logs")
    else:
        effective_prompt_logs = args.prompt_logs

    target_profiles = list(ACCOUNTS.keys()) if args.account == "all" else [args.account]

    for prof in target_profiles:
        try:
            res = sync_all(profile=prof, force=args.force, target_date=args.date,
                           prompt_logs=effective_prompt_logs, dataset=args.dataset,
                           max_workers=args.workers)
            print(f"Sync complete [{prof}]: {res}")
        except Exception as e:
            err_msg = str(e)
            if "ExpiredToken" in err_msg or "token has expired" in err_msg.lower():
                logger.error(
                    f"\n{'!'*60}\n"
                    f"AWS session token has expired for profile '{prof}'.\n"
                    f"Please refresh your AWS session: aws sso login --profile {prof}\n"
                    f"{'!'*60}\n"
                )
                sys.exit(1)
            elif "NoCredentialsError" in err_msg:
                logger.error(
                    f"\n{'!'*60}\n"
                    f"No AWS credentials found for profile '{prof}'.\n"
                    f"Please authenticate via AWS: aws sso login --profile {prof}\n"
                    f"{'!'*60}\n"
                )
                sys.exit(1)
            raise
