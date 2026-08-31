# Production Deployment (Linux / EC2)

> All commands are run from the repo root: `/path/to/judicial-bangles`

This project syncs Kiro usage reports from S3 into MySQL, then Grafana reads MySQL for dashboards. On Linux it runs as a nightly cron job. No long-running server process.

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

- A Linux host (EC2 or on-prem) with network reach to your S3 buckets and MySQL
- AWS credentials (SSO profile, EC2 instance role, or access keys)
- MySQL 8.x with a database and write credentials
- (Optional) Grafana instance to visualize

Verify base tools:

```bash
uname -m               # x86_64 or aarch64
python3 --version      # 3.10+
aws --version
```

---

## Step 1: Install Tools

**Debian / Ubuntu:**

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip
# AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install && rm -rf awscliv2.zip aws
```

**RHEL / CentOS / Amazon Linux:**

```bash
sudo yum install -y python3 python3-pip
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip awscliv2.zip && sudo ./aws/install && rm -rf awscliv2.zip aws
```

> For ARM hosts (Graviton), use `awscli-exe-linux-aarch64.zip`.

---

## Step 2: Configure AWS Credentials

Pick the method that matches your environment:

**A) IAM Identity Center (SSO):**

```bash
aws configure sso
# Set the profile name to match the key in conf/accounts.json
aws sts get-caller-identity --profile 111111111111_AdministratorAccess
```

**B) EC2 instance role (recommended for unattended cron):**

Attach an IAM role to the instance with `s3:GetObject` + `s3:ListBucket` on the Kiro buckets. Then in `conf/accounts.json` you can omit profiles and rely on the default credential chain — or keep the profile keys and ensure the role is assumable. No token expiry to manage.

**C) Static access keys** (least preferred):

```bash
aws configure --profile 111111111111_AdministratorAccess
```

---

## Step 3: Clone & Set Up Python Environment

```bash
git clone <your-repo-url> judicial-bangles
cd judicial-bangles

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 -c "import boto3, pymysql, pandas, dotenv; print('deps OK')"
```

---

## Step 4: Configure the Project

```bash
cp conf/.env.kiro.example conf/.env.kiro
cp conf/accounts.json.example conf/accounts.json
```

Edit `conf/.env.kiro` (MySQL creds + default profile) and `conf/accounts.json` (AWS accounts + bucket names) — see the macOS guide Step 4 for field details.

Verify MySQL connectivity:

```bash
python3 -c "import sys; sys.path.insert(0,'.'); from db import get_connection; get_connection(); print('DB reachable')"
```

---

## Step 5: First Run (Manual)

```bash
python3 main.py --account 111111111111_AdministratorAccess
```

Creates tables on first run, downloads CSVs, upserts to MySQL. Run once per account.

---

## Step 6: Download Prompt Logs (Optional)

Always scope with `--date` (high volume).

```bash
python3 main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22
# add --store-text to also store full conversation text
```

---

## Step 7: Schedule via Cron

```bash
mkdir -p logs
crontab -e
```

```
# Kiro usage sync — 3 AM UTC nightly, one entry per account (staggered)
0 3 * * * cd /path/to/judicial-bangles && /path/to/judicial-bangles/.venv/bin/python3 main.py --account 111111111111_AdministratorAccess >> logs/prod.log 2>&1
5 3 * * * cd /path/to/judicial-bangles && /path/to/judicial-bangles/.venv/bin/python3 main.py --account 222222222222_AdministratorAccess >> logs/dev.log 2>&1
```

> Use the **absolute path** to the venv python — cron has a minimal PATH.
> If using SSO (not an instance role), tokens expire; an EC2 instance role (Step 2B) is the robust choice for unattended cron.

Verify:

```bash
crontab -l
grep CRON /var/log/syslog     # Debian/Ubuntu
# or
grep CROND /var/log/cron      # RHEL/CentOS
```

---

## Step 8: Connect Grafana

Point Grafana at your MySQL (host/db/user/pass from `conf/.env.kiro`), then build panels from `docs/queries.sql`. Add an `account_label` dashboard variable:

```sql
SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label
```

---

## Reading Data Locally

```bash
python3 read_logs.py summary --account 222222222222 --date 2026-08-24
python3 read_logs.py prompts --account 222222222222 --date 2026-08-22 --user jdoe
```

---

## Uninstall

```bash
crontab -e            # delete the sync lines
rm -rf .venv
cd .. && rm -rf judicial-bangles   # optional
```

Drop tables if desired:

```sql
DROP TABLE kiro_user_report, kiro_by_user_analytic, kiro_prompt_log;
```

---

## Data Removal

```bash
rm -rf data/                    # downloaded S3 files (re-downloaded next sync)
rm -rf logs/                    # logs
rm -f data/*/.sync_state.json   # force full re-download next run
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| MySQL connect timeout | Check security group / VPC route / host value |
| `Unknown AWS profile` | Key in `conf/accounts.json` must match `--account` |
| `ExpiredToken` in cron | Use an EC2 instance role instead of SSO for unattended runs |
| `ModuleNotFoundError` in cron | Use absolute venv python path in crontab |
| cron didn't run | `grep CROND /var/log/cron` (RHEL) or `grep CRON /var/log/syslog` (Debian) |
| Prompt log sync hangs | Missing `--date` — it's listing the full bucket. Add `--date`. |

---

## Quick Reference

| Action | Command (from repo root) |
|--------|--------------------------|
| Set up venv | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| Sync one account | `python3 main.py --account <profile>` |
| Force re-download a date | `python3 main.py --account <profile> --force --date 2026-08-20` |
| Prompt logs (1 day) | `python3 main.py --account <profile> --prompt-logs --date 2026-08-22` |
| Read prompts locally | `python3 read_logs.py prompts --account <id> --date <date> --user <name>` |
| Daily summary | `python3 read_logs.py summary --account <id> --date <date>` |
| Check DB connectivity | `python3 -c "import sys;sys.path.insert(0,'.');from db import get_connection;get_connection();print('OK')"` |
