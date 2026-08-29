"""Incremental S3 sync — downloads only new files since last run, per AWS account.

Idempotency:
  - <account_data_dir>/.sync_state.json tracks last successful sync timestamp per report type.
  - Files already on disk are never re-downloaded (existence check).
  - Use --force to reset state and re-download (today, or a specific --date).

Retention:
  - On each sync start, local files older than DATA_RETENTION_DAYS are deleted.

Local layout (Option D): flat dirs per account with original AWS filenames.
  data/<account_id>/user_report/<original_filename>.csv
  data/<account_id>/by_user_analytic/<original_filename>.csv
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

from conf.config import (
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
            _save_state(account_data_dir, state)
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
                state.setdefault("files", {})[sub_dir] = sorted(str(f) for f in dir_path.iterdir() if f.is_file())
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
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if target_date:
                try:
                    dt = datetime.strptime(target_date, "%Y-%m-%d")
                    date_segment = f"/{dt.year}/{dt.month:02d}/{dt.day:02d}/"
                    if date_segment not in key:
                        continue
                except ValueError:
                    logger.error(f"Invalid --date format: {target_date}, expected YYYY-MM-DD")

            if after_date and not target_date:
                obj_modified = obj["LastModified"].isoformat()
                if obj_modified <= after_date:
                    continue

            objects.append(obj)
    return objects


def _download_objects(s3, bucket: str, objects: list[dict], dest_root: Path, file_type: str, force: bool = False) -> list[Path]:
    """Download objects flat into dest_root/ keeping original filename.

    Idempotent: skips files already on disk (tracked in state) unless force=True.
    Writes each file to disk immediately — you'll see files appear in real time.
    """
    downloaded = []
    dest_root.mkdir(parents=True, exist_ok=True)

    account_data_dir = dest_root.parent
    state = _load_state(account_data_dir)
    known_files = set(state.get("files", {}).get(file_type, []))

    total = len(objects)
    for i, obj in enumerate(objects, 1):
        key = obj["Key"]
        filename = key.rsplit("/", 1)[-1]
        if not filename:
            continue
        local_path = dest_root / filename
        local_path_str = str(local_path)

        if not force and local_path.exists() and local_path_str in known_files:
            continue

        s3.download_file(bucket, key, str(local_path))
        downloaded.append(local_path)
        known_files.add(local_path_str)
        logger.info(f"[{i}/{total}] {filename}")

    state.setdefault("files", {})[file_type] = sorted(known_files)
    _save_state(account_data_dir, state)

    return downloaded


def sync_user_reports(cfg: dict, s3=None, force: bool = False, target_date: str | None = None) -> list[Path]:
    """Sync user_report CSVs (credits/subscription data) for one account."""
    if s3 is None:
        s3 = _get_s3_client(cfg["profile"], cfg["region"])
    account_data_dir = get_account_data_dir(cfg["account_id"])
    state = _load_state(account_data_dir)

    after = None if force else state.get("user_report_last")
    prefix = cfg["user_report_prefix"] + "user_report/"
    objects = _list_objects(s3, cfg["user_report_bucket"], prefix, after, target_date=target_date)
    downloaded = _download_objects(s3, cfg["user_report_bucket"], objects, account_data_dir / "user_report", "user_report", force)

    if objects and not target_date:
        latest = max(o["LastModified"] for o in objects)
        state = _load_state(account_data_dir)
        state["user_report_last"] = latest.isoformat()
        _save_state(account_data_dir, state)

    logger.info(f"[{cfg['label']}] user_report: {len(downloaded)} new files downloaded")
    return downloaded


def sync_by_user_analytic(cfg: dict, s3=None, force: bool = False, target_date: str | None = None) -> list[Path]:
    """Sync by_user_analytic CSVs (detailed feature usage) for one account."""
    if s3 is None:
        s3 = _get_s3_client(cfg["profile"], cfg["region"])
    account_data_dir = get_account_data_dir(cfg["account_id"])
    state = _load_state(account_data_dir)

    after = None if force else state.get("by_user_analytic_last")
    prefix = cfg["user_report_prefix"] + "by_user_analytic/"
    objects = _list_objects(s3, cfg["user_report_bucket"], prefix, after, target_date=target_date)
    downloaded = _download_objects(s3, cfg["user_report_bucket"], objects, account_data_dir / "by_user_analytic", "by_user_analytic", force)

    if objects and not target_date:
        latest = max(o["LastModified"] for o in objects)
        state = _load_state(account_data_dir)
        state["by_user_analytic_last"] = latest.isoformat()
        _save_state(account_data_dir, state)

    logger.info(f"[{cfg['label']}] by_user_analytic: {len(downloaded)} new files downloaded")
    return downloaded


def sync_prompt_logs(cfg: dict, s3=None, force: bool = False, target_date: str | None = None) -> list[Path]:
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

    # Optimization: if target_date given, build a narrower S3 prefix to avoid listing 300k+ objects
    if target_date:
        try:
            dt = datetime.strptime(target_date, "%Y-%m-%d")
            # S3 path: .../GenerateAssistantResponse/us-east-1/YYYY/MM/DD/
            prefix = f"{base_prefix}us-east-1/{dt.year}/{dt.month:02d}/{dt.day:02d}/"
        except ValueError:
            prefix = base_prefix
        # No watermark filtering needed when targeting specific date
        objects = _list_objects(s3, cfg["prompt_log_bucket"], prefix, after_date=None, target_date=None)
    else:
        prefix = base_prefix
        objects = _list_objects(s3, cfg["prompt_log_bucket"], prefix, after_date=after, target_date=None)

    downloaded = _download_objects(s3, cfg["prompt_log_bucket"], objects, account_data_dir / "prompt_logs", "prompt_logs", force)

    if objects and not target_date:
        latest = max(o["LastModified"] for o in objects)
        state = _load_state(account_data_dir)
        state["prompt_log_last"] = latest.isoformat()
        _save_state(account_data_dir, state)

    logger.info(f"[{cfg['label']}] prompt_logs: {len(downloaded)} new files downloaded")
    return downloaded


def _remove_files_for_date(account_data_dir: Path, target_date: str):
    """Remove local files matching a target date (YYYYMMDD in filename) so --force re-downloads them."""
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    date_str = dt.strftime("%Y%m%d")
    removed = 0

    state = _load_state(account_data_dir)
    files = state.setdefault("files", {"user_report": [], "by_user_analytic": [], "prompt_logs": []})

    for sub_dir in ("user_report", "by_user_analytic", "prompt_logs"):
        dir_path = account_data_dir / sub_dir
        if not dir_path.exists():
            continue
        type_files = set(files.get(sub_dir, []))
        for f in dir_path.iterdir():
            if f.is_file() and date_str in f.name:
                type_files.discard(str(f))
                f.unlink()
                removed += 1
                logger.info(f"Removed for re-download: {f.name}")
        files[sub_dir] = sorted(type_files)

    _save_state(account_data_dir, state)
    logger.info(f"Removed {removed} files for date {target_date}")


def sync_all(profile: str | None = None, force: bool = False, target_date: str | None = None, prompt_logs: bool = False) -> dict:
    """Run full sync for one AWS account/profile: retention cleanup then incremental download.

    profile: AWS profile name (key in conf.config.ACCOUNTS). Defaults to DEFAULT_AWS_PROFILE.
    force: re-download files (for target_date, or today if --date not set)
    target_date: YYYY-MM-DD — only sync files for that specific day
    prompt_logs: if True, also download prompt log .json.gz files (opt-in, high file count)
    """
    cfg = get_account_config(profile)
    account_data_dir = get_account_data_dir(cfg["account_id"])

    enforce_retention(account_data_dir)

    s3 = _get_s3_client(cfg["profile"], cfg["region"])

    if force and not target_date:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.info(f"--force without --date: targeting today ({target_date})")

    if force:
        _remove_files_for_date(account_data_dir, target_date)

    user_reports = sync_user_reports(cfg, s3, force=force, target_date=target_date)
    analytics = sync_by_user_analytic(cfg, s3, force=force, target_date=target_date)

    prompt_log_count = 0
    if prompt_logs:
        prompt_log_files = sync_prompt_logs(cfg, s3, force=force, target_date=target_date)
        prompt_log_count = len(prompt_log_files)

    return {
        "account": cfg["account_id"],
        "label": cfg["label"],
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
                        help="AWS profile name to sync (see conf/config.py ACCOUNTS). Defaults to DEFAULT_AWS_PROFILE.")
    parser.add_argument("--force", action="store_true", help="Re-download files for target date")
    parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD). Defaults to today with --force.")
    parser.add_argument("--prompt-logs", action="store_true",
                        help="Also download prompt logs (.json.gz). Use with --date to limit scope (otherwise downloads ALL).")
    args = parser.parse_args()

    result = sync_all(profile=args.account, force=args.force, target_date=args.date, prompt_logs=args.prompt_logs)
    print(f"Sync complete: {result}")
