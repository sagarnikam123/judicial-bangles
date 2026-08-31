# Local Setup (macOS)

> All commands are run from the repo root: `/path/to/judicial-bangles`

This project syncs Kiro usage reports from S3 into MySQL, then Grafana reads MySQL for dashboards. There's no server to run — just a Python script invoked by cron. Grafana can be an existing instance pointed at your MySQL.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Install Tools](#step-1-install-tools)
- [Step 2: Configure AWS Credentials](#step-2-configure-aws-credentials)
- [Step 3: Clone & Set Up Python Environment](#step-3-clone--set-up-python-environment)
- [Step 4: Configure the Project](#step-4-configure-the-project)
- [Step 5: First Run (Manual)](#step-5-first-run-manual)
- [Step 6: Download Prompt Logs (Optional)](#step-6-download-prompt-logs-optional)
- [Step 7: Schedule via Cron](#step-7-schedule-via-cron)
- [Step 8: Connect Grafana](#step-8-connect-grafana)
- [Reading Data Locally](#reading-data-locally)
- [Uninstall](#uninstall)
- [Data Removal](#data-removal)
- [Troubleshooting](#troubleshooting)
- [Quick Reference](#quick-reference)

---

## Prerequisites

- macOS with [Homebrew](https://brew.sh/)
- Access to the AWS account(s) where Kiro writes usage reports (via AWS IAM Identity Center / SSO)
- A reachable MySQL instance (8.x) with a database and write credentials
- (Optional) A Grafana instance to visualize — can be local or shared

---

## Step 1: Install Tools

```bash
brew install python@3.12 awscli
```

Verify:

```bash
python3 --version      # 3.10+
aws --version
```

---

## Step 2: Configure AWS Credentials

This project reads from S3 using named AWS profiles. If your org uses IAM Identity Center (SSO):

```bash
aws configure sso
# Follow prompts — set the profile name to match the key in conf/accounts.json
# e.g. 111111111111_AdministratorAccess
```

Verify the profile works:

```bash
aws sts get-caller-identity --profile 111111111111_AdministratorAccess
```

> SSO sessions expire. Re-run `aws sso login --profile <profile>` when you get an auth error.

---

## Step 3: Clone & Set Up Python Environment

```bash
git clone <your-repo-url> judicial-bangles
cd judicial-bangles

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify:

```bash
python3 -c "import boto3, pymysql, pandas, dotenv; print('deps OK')"
```

---

## Step 4: Configure the Project

Two config files live in `conf/` — both are gitignored. Copy the `.example` versions:

```bash
cp conf/.env.kiro.example conf/.env.kiro
cp conf/accounts.json.example conf/accounts.json
```

**Edit `conf/.env.kiro`** with your MySQL credentials:

```bash
TEST_DEVOPS_DB_HOST=your-mysql-host.example.com
TEST_DEVOPS_DB_NAME=your_database
TEST_DEVOPS_DB_PORT=3306
TEST_DEVOPS_DB_USER=your_db_user
TEST_DEVOPS_DB_PASSWORD=your_db_password

AWS_PROFILE=111111111111_AdministratorAccess
AWS_REGION_DEFAULT=us-east-1
DATA_RETENTION_DAYS=30
```

**Edit `conf/accounts.json`** with your real AWS account(s) and S3 bucket names. Each key is the AWS profile name you pass to `--account`:

```json
{
  "111111111111_AdministratorAccess": {
    "account_id": "111111111111",
    "label": "prod",
    "region": "us-east-1",
    "user_report_bucket": "my-org-kiro-usage-activity-report",
    "user_report_prefix": "reports/AWSLogs/111111111111/KiroLogs/",
    "prompt_log_bucket": "my-org-kiro-usage-report",
    "prompt_log_prefix": "Prompt_Logging/Prompt_Logging/AWSLogs/111111111111/KiroLogs/"
  }
}
```

Verify MySQL connectivity:

```bash
python3 -c "import sys; sys.path.insert(0,'.'); from db import get_connection; get_connection(); print('DB reachable')"
```

---

## Step 5: First Run (Manual)

Sync CSVs (user_report + by_user_analytic) and load into MySQL. This also creates the tables on first run.

```bash
python3 main.py --account 111111111111_AdministratorAccess
```

Expected: log lines showing files downloaded and rows upserted, ending in `=== Done ===`.

For multiple accounts, run once per account:

```bash
python3 main.py --account 222222222222_AdministratorAccess
```

---

## Step 6: Download Prompt Logs (Optional)

Prompt logs are high-volume — always scope with `--date`. Metadata loads into `kiro_prompt_log`; add `--store-text` to also store full conversation text.

```bash
# Metadata only, one day
python3 main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22

# With full prompt/response text
python3 main.py --account 222222222222_AdministratorAccess --prompt-logs --store-text --date 2026-08-22
```

---

## Step 7: Schedule via Cron

Reports land in S3 around 2 AM UTC. Schedule the sync at 3 AM UTC nightly.

```bash
mkdir -p logs
crontab -e
```

Add (adjust the repo path and profile names):

```
# Kiro usage sync — 3 AM UTC nightly, one entry per account (staggered)
0 3 * * * cd /path/to/judicial-bangles && .venv/bin/python3 main.py --account 111111111111_AdministratorAccess >> logs/prod.log 2>&1
5 3 * * * cd /path/to/judicial-bangles && .venv/bin/python3 main.py --account 222222222222_AdministratorAccess >> logs/dev.log 2>&1
```

> Use the venv's python (`.venv/bin/python3`) so cron gets the installed deps. Cron doesn't load your shell profile, so AWS SSO creds must be non-interactive or refreshed separately (see Troubleshooting).

Verify it saved:

```bash
crontab -l
```

> **macOS Ventura+:** Grant **Full Disk Access** to `/usr/sbin/cron` in System Settings → Privacy & Security → Full Disk Access, otherwise cron silently fails.

---

## Step 8: Connect Grafana

Point Grafana at your MySQL and use the queries in `docs/queries.sql`.

1. Grafana → Connections → Data sources → Add → **MySQL**
2. Host/DB/User/Password = same values as `conf/.env.kiro`
3. Save & Test
4. Create a dashboard variable `account_label` with query:
   `SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label`
5. Build panels from `docs/queries.sql` (Sections 1–23)

---

## Reading Data Locally

`read_logs.py` queries downloaded files without hitting S3 or the DB:

```bash
# Prompts for a user on a date
python3 read_logs.py prompts --account 222222222222 --date 2026-08-22 --user jdoe

# Daily summary (all file types)
python3 read_logs.py summary --account 222222222222 --date 2026-08-24
```

---

## Uninstall

```bash
# 1. Remove cron entries
crontab -e   # delete the sync lines

# 2. Remove the venv
rm -rf .venv

# 3. (Optional) remove the whole repo
cd .. && rm -rf judicial-bangles
```

MySQL tables and Grafana are untouched. Drop tables manually if desired:

```sql
DROP TABLE kiro_user_report, kiro_by_user_analytic, kiro_prompt_log;
```

---

## Data Removal

```bash
# Downloaded S3 files (safe — re-downloaded on next sync)
rm -rf data/

# Logs
rm -rf logs/

# Sync state only (forces full re-download next run)
rm -f data/*/.sync_state.json
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Can't connect to MySQL server ... timed out` | Check VPN / security group / host in `conf/.env.kiro` |
| `Unknown AWS profile` | Profile key in `conf/accounts.json` must match `--account` value |
| `ExpiredToken` / `Unauthorized` from S3 | `aws sso login --profile <profile>` |
| `ModuleNotFoundError` in cron | Use `.venv/bin/python3` in the crontab, not bare `python3` |
| cron not running (macOS) | Grant Full Disk Access to `/usr/sbin/cron` |
| Prompt log sync hangs | You forgot `--date` — it's listing 300k+ objects. Ctrl-C and add `--date`. |

---

## Quick Reference

| Action | Command (from repo root) |
|--------|--------------------------|
| Set up venv | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| SSO login | `aws sso login --profile <profile>` |
| Sync one account | `python3 main.py --account <profile>` |
| Force re-download a date | `python3 main.py --account <profile> --force --date 2026-08-20` |
| Download prompt logs (1 day) | `python3 main.py --account <profile> --prompt-logs --date 2026-08-22` |
| Read prompts locally | `python3 read_logs.py prompts --account <id> --date <date> --user <name>` |
| Daily summary | `python3 read_logs.py summary --account <id> --date <date>` |
| Check DB connectivity | `python3 -c "import sys;sys.path.insert(0,'.');from db import get_connection;get_connection();print('OK')"` |
