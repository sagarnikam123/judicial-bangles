"""Configuration loader — reads .env.kiro for DB creds and accounts.json for the
per-account S3 bucket registry.

Multi-account support: each Kiro-enabled AWS account has its own S3 bucket layout.
Define your accounts in conf/accounts.json (see conf/accounts.json.example).
Select one at runtime via --account <profile_name> (see main.py / s3_sync.py).
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env from conf/.env.kiro
_env_path = Path(__file__).parent / ".env.kiro"
load_dotenv(_env_path)

AWS_REGION_DEFAULT = os.getenv("AWS_REGION_DEFAULT", "us-east-1")

# -- Account registry --
# Loaded from conf/accounts.json (gitignored). Falls back to accounts.json.example
# so the project runs out-of-the-box for docs/demo without real account data.
_accounts_path = Path(__file__).parent / "accounts.json"
if not _accounts_path.exists():
    _accounts_path = Path(__file__).parent / "accounts.json.example"

with open(_accounts_path) as _f:
    ACCOUNTS = json.load(_f)

DEFAULT_AWS_PROFILE = os.getenv("AWS_PROFILE") or (next(iter(ACCOUNTS)) if ACCOUNTS else None)


def get_account_config(profile: str | None = None) -> dict:
    """Resolve account config by AWS profile name. Falls back to DEFAULT_AWS_PROFILE."""
    profile = profile or DEFAULT_AWS_PROFILE
    if profile not in ACCOUNTS:
        raise ValueError(
            f"Unknown AWS profile '{profile}'. Registered profiles: {list(ACCOUNTS.keys())}"
        )
    cfg = dict(ACCOUNTS[profile])
    cfg["profile"] = profile
    cfg.setdefault("region", AWS_REGION_DEFAULT)
    return cfg


# MySQL
DB_HOST = os.getenv("TEST_DEVOPS_DB_HOST")
DB_NAME = os.getenv("TEST_DEVOPS_DB_NAME")
DB_PORT = int(os.getenv("TEST_DEVOPS_DB_PORT", "3306"))
DB_USER = os.getenv("TEST_DEVOPS_DB_USER")
DB_PASSWORD = os.getenv("TEST_DEVOPS_DB_PASSWORD")

# Local data root — per-account subfolders are created under here:
#   data/<account_id>/user_report/*.csv
#   data/<account_id>/by_user_analytic/*.csv
#   data/<account_id>/.sync_state.json
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def get_account_data_dir(account_id: str) -> Path:
    d = DATA_DIR / account_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# Data retention (days) — local files older than this are purged on sync
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "30"))
