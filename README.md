# Judicial Bangles

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tested with: pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC.svg?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Platform: AWS](https://img.shields.io/badge/platform-AWS%20S3-232F3E.svg?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)
[![AWS SDK: boto3](https://img.shields.io/badge/AWS%20SDK-boto3-FF9900.svg?logo=amazon-aws&logoColor=white)](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)
[![Telemetry: Amazon Q Developer](https://img.shields.io/badge/telemetry-Amazon%20Q%20Developer-7057ff.svg?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/q/developer/)
[![Backends: 5 Supported](https://img.shields.io/badge/backends-MySQL%20%7C%20Postgres%20%7C%20ClickHouse%20%7C%20OpenSearch-blue.svg)](#supported-storage-backends)
[![Dashboards: Grafana](https://img.shields.io/badge/dashboards-Grafana-F46800.svg?logo=grafana&logoColor=white)](dashboard/)
[![Architecture: Multi-Account](https://img.shields.io/badge/architecture-Multi--Account-success.svg)](#architecture--data-flow)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/sagarnikam123/judicial-bangles/pulls)

Syncs **Kiro (Amazon Q Developer)** usage reports and prompt logs from Amazon S3 into analytical backends for reporting and Grafana visualization.

The pipeline pulls data across multiple AWS accounts (e.g. `prod` and `dev`), normalizes and tags every record with `aws_account_id` and `account_label`, and streams them into your chosen backend so dashboards can dynamically slice and aggregate by account.

---

## Key Features

- **Multi-Account Aggregation**: Ingests daily usage CSVs and prompt logs across separate AWS accounts into a unified schema.
- **5 Supported Backends**: Store metrics and prompt logs in **MySQL**, **PostgreSQL**, **ClickHouse**, **OpenSearch**, or **Elasticsearch**.
- **Incremental & Idempotent**: State watermarking (`.sync_state.json`) prevents duplicate downloads. Upserts ensure safe re-runs.
- **Searchable Prompt Logging**: Opt-in prompt log indexing with full-text search capability.
- **Built-in Log Explorer**: Query user activity, credit consumption, and model conversations via the `read_logs.py` CLI.

---

## Architecture & Data Flow

```
   ┌───────────────────────────┐         ┌───────────────────────────┐
   │     AWS Account: prod     │         │     AWS Account: dev      │
   │       111111111111        │         │       222222222222        │
   └─────────────┬─────────────┘         └─────────────┬─────────────┘
                 │                                     │
       Kiro daily CSV reports                Kiro daily CSV reports
       + prompt logs (S3)                    + prompt logs (S3)
                 │                                     │
                 ▼                                     ▼
        s3://prod-kiro-bucket/                s3://dev-kiro-bucket/
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    │
                                    ▼
                          python main.py --account <profile>
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        ▼                                                       ▼
 1. Retention Sweep                                      2. Incremental Sync (s3_sync.py)
    Purge local files > 30 days                             Download new S3 objects to
                                                            data/<account_id>/
        │                                                       │
        └───────────────────────────┬───────────────────────────┘
                                    ▼
                         3. Parser & Normalizer (main.py)
                            Coerce types, tag with aws_account_id
                                    │
                                    ▼
                         4. Unified Writers (writers/)
                            Load into chosen backend
                                    │
        ┌──────────────┬────────────┼─────────────┬──────────────┐
        ▼              ▼            ▼             ▼              ▼
      MySQL        PostgreSQL   ClickHouse   OpenSearch   Elasticsearch
        └──────────────┴────────────┼─────────────┴──────────────┘
                                    ▼
                         Grafana Dashboards
                         Filter panels by $account_label dropdown
```

---

## Supported Storage Backends

Choose whichever storage backend matches your existing infrastructure:

| Backend | Flag (`--backend`) | Best for | Grafana Datasource | Extra Requirements |
|---|---|---|---|---|
| **MySQL** | `mysql` (default) | Relational metrics, user aggregation | Core (built-in) | Included in `requirements.txt` |
| **PostgreSQL** | `postgres` | Relational metrics, JSONB queries | Core (built-in) | `requirements-postgres.txt` |
| **ClickHouse** | `clickhouse` | High-volume columnar aggregation (300k+ rows) | Official plugin | `requirements-clickhouse.txt` |
| **OpenSearch** | `opensearch` | Full-text search on prompt/response text | Official plugin | `requirements-opensearch.txt` |
| **Elasticsearch**| `elasticsearch`| Full-text search and log analytics | Core (built-in) | `requirements-opensearch.txt` |

---

## Quickstart

### 1. Prerequisites & Dependencies

```bash
git clone https://github.com/your-org/judicial-bangles.git
cd judicial-bangles

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install base dependencies
pip install -r requirements.txt

# (Optional) Install driver for your chosen backend:
# pip install -r requirements-postgres.txt
# pip install -r requirements-opensearch.txt
# pip install -r requirements-clickhouse.txt
```

### 2. Configure Credentials

Copy the example configuration templates and set your values:

```bash
# 1. Database connection settings & retention policy
cp conf/.env.kiro.example conf/.env.kiro

# 2. AWS account registry & bucket mappings
cp conf/accounts.json.example conf/accounts.json
```

- **`conf/.env.kiro`**: Set credentials for your storage backend and default settings.
- **`conf/accounts.json`**: Map AWS profile names to account IDs, labels, and S3 bucket prefixes.

### 3. Run Your First Sync

```bash
# Authenticate with AWS SSO
aws sso login --profile <your_profile>

# Sync reports into MySQL (default backend)
python main.py --account <your_profile>

# Or sync and load into a specific backend
python main.py --account <your_profile> --backend postgres
```

---

## Common CLI Commands

### Full Pipeline (`main.py`: Download + Parse + Load)

```bash
# Standard daily sync (downloads new CSVs and upserts into default backend)
python main.py --account <profile>

# Sync into a specific backend
python main.py --account <profile> --backend clickhouse

# Sync CSVs AND prompt logs for a specific date
python main.py --account <profile> --prompt-logs --date 2026-08-22

# Store full prompt/response text in SQL backend (default stores metadata only)
python main.py --account <profile> --prompt-logs --date 2026-08-22 --store-text

# Force re-download and re-load for a specific date
python main.py --account <profile> --force --date 2026-08-20

# Re-parse ALL local CSVs into DB without touching S3
python main.py --account <profile> --full
```

### Download Only (`s3_sync.py`: No Database Changes)

```bash
# Download only new CSV reports locally
python s3_sync.py --account <profile>

# Download prompt logs for a specific date
python s3_sync.py --account <profile> --prompt-logs --date 2026-08-22
```

### Exploring Logs Locally (`read_logs.py`)

Inspect downloaded data without querying the database:

```bash
# Search prompt conversations for a specific user
python read_logs.py prompts --account <profile> --user jdoe

# Inspect credit usage for a user
python read_logs.py credits --account <profile> --user jdoe

# Show user activity breakdown
python read_logs.py activity --account <profile> --user jdoe
```

---

## Automation (Cron)

Schedule nightly execution after daily reports land in S3 (~02:00 UTC):

```bash
# Edit crontab
crontab -e

# Run at 03:00 UTC nightly (stagger multiple accounts by 5 minutes)
0 3 * * * cd /path/to/judicial-bangles && /path/to/.venv/bin/python main.py --account 111111111111_AdministratorAccess >> logs/prod.log 2>&1
5 3 * * * cd /path/to/judicial-bangles && /path/to/.venv/bin/python main.py --account 222222222222_AdministratorAccess >> logs/dev.log 2>&1
```

---

## Documentation Hub

For in-depth operational, deployment, and schema guides:

- 🚀 **[Backend Deployment Guides](deploy/backends/README.md)**: 1-command Docker Compose local spin-up, connection vars, and production patterns across all 5 backends.
- 📖 **[Operations Runbook](docs/operations.md)**: Complete step-by-step commands for starting backends, table creation, data loading, truncating, and verifying each backend.
- 🪣 **[S3 Buckets & Schemas](docs/s3-sources.md)**: S3 directory partition hierarchy, bucket paths, and raw `.json.gz` event structures.
- 🔑 **[UserId Format & Mapping](docs/user-id-mapping.md)**: IAM Identity Center user ID conversions, regex patterns, and cross-dataset SQL join examples.
- 📊 **[Data Dictionary](docs/data-dictionary.md)**: Comprehensive schema definitions, column data types, and descriptions for all 3 datasets.
- 📈 **[MySQL & Grafana Queries](docs/mysql-quries.md)**: Production-ready SQL queries for Grafana dashboard panels and operational reporting.
