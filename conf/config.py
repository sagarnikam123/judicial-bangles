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


# MySQL (also the default target for prompt-log ingestion)
DB_HOST = os.getenv("TEST_DEVOPS_DB_HOST")
DB_NAME = os.getenv("TEST_DEVOPS_DB_NAME")
DB_PORT = int(os.getenv("TEST_DEVOPS_DB_PORT", "3306"))
DB_USER = os.getenv("TEST_DEVOPS_DB_USER")
DB_PASSWORD = os.getenv("TEST_DEVOPS_DB_PASSWORD")

# -- Prompt-log storage backend --
# Which store to load prompt logs into: mysql | postgres | opensearch | elasticsearch | clickhouse
# (CSV report tables always go to MySQL — only prompt logs are backend-selectable.)
PROMPT_LOG_BACKEND = os.getenv("PROMPT_LOG_BACKEND", "mysql")

# PostgreSQL
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "kiro")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

# OpenSearch / Elasticsearch (same client, same options)
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "https://localhost:9200")
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "kiro-prompt-log")
OPENSEARCH_VERIFY_CERTS = os.getenv("OPENSEARCH_VERIFY_CERTS", "false").lower() == "true"

# ClickHouse
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "kiro")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_TABLE = os.getenv("CLICKHOUSE_TABLE", "kiro_prompt_log")

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
