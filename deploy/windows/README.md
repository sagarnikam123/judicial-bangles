# Local Setup (Windows)

> All commands are run from the repo root in **PowerShell**: `C:\path\to\judicial-bangles`

This project syncs Kiro usage reports from S3 into MySQL, then Grafana reads MySQL for dashboards. There's no server to run — just a Python script invoked by Task Scheduler (the Windows equivalent of cron). Grafana can be an existing instance pointed at your MySQL.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Install Tools](#step-1-install-tools)
- [Step 2: Configure AWS Credentials](#step-2-configure-aws-credentials)
- [Step 3: Clone & Set Up Python Environment](#step-3-clone--set-up-python-environment)
- [Step 4: Configure the Project](#step-4-configure-the-project)
- [Step 5: First Run (Manual)](#step-5-first-run-manual)
- [Step 6: Download Prompt Logs (Optional)](#step-6-download-prompt-logs-optional)
- [Step 7: Schedule via Task Scheduler](#step-7-schedule-via-task-scheduler)
- [Step 8: Connect Grafana](#step-8-connect-grafana)
- [Reading Data Locally](#reading-data-locally)
- [Uninstall](#uninstall)
- [Data Removal](#data-removal)
- [Troubleshooting](#troubleshooting)
- [Quick Reference](#quick-reference)

---

## Prerequisites

- Windows 10/11 or Windows Server with PowerShell 5.1+
- Access to the AWS account(s) where Kiro writes usage reports (via AWS IAM Identity Center / SSO)
- A reachable MySQL instance (8.x) with a database and write credentials
- (Optional) A Grafana instance to visualize — local or shared

---

## Step 1: Install Tools

Using [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/) (built into Windows 11 / modern Windows 10):

```powershell
winget install Python.Python.3.12
winget install Amazon.AWSCLI
winget install Git.Git
```

Close and reopen PowerShell, then verify:

```powershell
python --version       # 3.10+
aws --version
```

> If `python` isn't found, use `py --version` or add the Python install dir to PATH. The rest of this guide uses `python`; substitute `py` if that's what your system exposes.

---

## Step 2: Configure AWS Credentials

This project reads from S3 using named AWS profiles. If your org uses IAM Identity Center (SSO):

```powershell
aws configure sso
# Follow prompts — set the profile name to match the key in conf\accounts.json
# e.g. 111111111111_AdministratorAccess
```

Verify:

```powershell
aws sts get-caller-identity --profile 111111111111_AdministratorAccess
```

> SSO sessions expire. Re-run `aws sso login --profile <profile>` when you get an auth error.

---

## Step 3: Clone & Set Up Python Environment

```powershell
git clone <your-repo-url> judicial-bangles
cd judicial-bangles

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If activation is blocked by execution policy, run once (current user only):
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

Verify:

```powershell
python -c "import boto3, pymysql, pandas, dotenv; print('deps OK')"
```

---

## Step 4: Configure the Project

Two config files live in `conf\` — both are gitignored. Copy the `.example` versions:

```powershell
Copy-Item conf\.env.kiro.example conf\.env.kiro
Copy-Item conf\accounts.json.example conf\accounts.json
```

**Edit `conf\.env.kiro`** with your MySQL credentials:

```
TEST_DEVOPS_DB_HOST=your-mysql-host.example.com
TEST_DEVOPS_DB_NAME=your_database
TEST_DEVOPS_DB_PORT=3306
TEST_DEVOPS_DB_USER=your_db_user
TEST_DEVOPS_DB_PASSWORD=your_db_password

AWS_PROFILE=111111111111_AdministratorAccess
AWS_REGION_DEFAULT=us-east-1
DATA_RETENTION_DAYS=30
```

**Edit `conf\accounts.json`** with your real AWS account(s) and S3 bucket names. Each key is the AWS profile name you pass to `--account`:

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

```powershell
python -c "import sys; sys.path.insert(0,'.'); from db import get_connection; get_connection(); print('DB reachable')"
```

---

## Step 5: First Run (Manual)

Sync CSVs (user_report + by_user_analytic) and load into MySQL. This also creates the tables on first run.

```powershell
python main.py --account 111111111111_AdministratorAccess
```

Expected: log lines showing files downloaded and rows upserted, ending in `=== Done ===`.

Run once per account:

```powershell
python main.py --account 222222222222_AdministratorAccess
```

---

## Step 6: Download Prompt Logs (Optional)

Prompt logs are high-volume — always scope with `--date`. Metadata loads into `kiro_prompt_log`; add `--store-text` to also store full conversation text.

```powershell
# Metadata only, one day
python main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22

# With full prompt/response text
python main.py --account 222222222222_AdministratorAccess --prompt-logs --store-text --date 2026-08-22
```

---

## Step 7: Schedule via Task Scheduler

Reports land in S3 around 2 AM UTC. Schedule the sync at 3 AM nightly. Task Scheduler is the Windows equivalent of cron.

### Option A: PowerShell (register the task from a script)

Run PowerShell **as Administrator** from the repo root. Adjust the path and profile:

```powershell
$repo   = "C:\path\to\judicial-bangles"
$python = "$repo\.venv\Scripts\python.exe"

$action  = New-ScheduledTaskAction -Execute $python `
  -Argument "main.py --account 111111111111_AdministratorAccess" `
  -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM

Register-ScheduledTask -TaskName "KiroUsageSync-prod" `
  -Action $action -Trigger $trigger `
  -Description "Nightly Kiro usage report sync (prod account)" `
  -RunLevel Limited
```

Register a second task for another account with a slightly later time (e.g. `-At 3:05AM`) and a distinct `-TaskName`.

> The task runs the venv's `python.exe` directly, so dependencies resolve without activating the venv.
> Output isn't captured by default — wrap the command to log (see below) if you want a log file.

**Log to a file** (optional): use `cmd /c` as the executable so you can redirect:

```powershell
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
  -Argument "/c `"$python`" main.py --account 111111111111_AdministratorAccess >> logs\prod.log 2>&1" `
  -WorkingDirectory $repo
```

Create the logs dir first: `New-Item -ItemType Directory -Force logs`.

### Option B: Task Scheduler GUI

1. Open **Task Scheduler** → **Create Task**
2. **General:** name `KiroUsageSync-prod`; check *Run whether user is logged on or not*
3. **Triggers:** New → Daily → 3:00 AM
4. **Actions:** New → Program/script = `C:\path\to\judicial-bangles\.venv\Scripts\python.exe`; Arguments = `main.py --account 111111111111_AdministratorAccess`; Start in = `C:\path\to\judicial-bangles`
5. Save (enter your password if prompted)

Verify / run on demand:

```powershell
Get-ScheduledTask -TaskName "KiroUsageSync-prod"
Start-ScheduledTask -TaskName "KiroUsageSync-prod"
Get-ScheduledTaskInfo -TaskName "KiroUsageSync-prod"   # LastRunResult 0 = success
```

> **SSO note:** if the task runs while you're logged off, an interactive SSO token may be expired. For unattended Windows runs, prefer static credentials in a dedicated profile, or run the box under an account whose SSO token is refreshed on a schedule.

---

## Step 8: Connect Grafana

Point Grafana at your MySQL and use the queries in `docs\queries.sql`.

1. Grafana → Connections → Data sources → Add → **MySQL**
2. Host/DB/User/Password = same values as `conf\.env.kiro`
3. Save & Test
4. Add a dashboard variable `account_label`:
   `SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label`
5. Build panels from `docs\queries.sql` (Sections 1–23)

---

## Reading Data Locally

`read_logs.py` queries downloaded files without hitting S3 or the DB:

```powershell
# Prompts for a user on a date
python read_logs.py prompts --account 222222222222 --date 2026-08-22 --user jdoe

# Daily summary (all file types)
python read_logs.py summary --account 222222222222 --date 2026-08-24
```

---

## Uninstall

```powershell
# 1. Remove scheduled tasks
Unregister-ScheduledTask -TaskName "KiroUsageSync-prod" -Confirm:$false
Unregister-ScheduledTask -TaskName "KiroUsageSync-dev"  -Confirm:$false

# 2. Remove the venv
Remove-Item -Recurse -Force .venv

# 3. (Optional) remove the whole repo
cd ..; Remove-Item -Recurse -Force judicial-bangles
```

MySQL tables and Grafana are untouched. Drop tables manually if desired:

```sql
DROP TABLE kiro_user_report, kiro_by_user_analytic, kiro_prompt_log;
```

---

## Data Removal

```powershell
# Downloaded S3 files (safe — re-downloaded on next sync)
Remove-Item -Recurse -Force data

# Logs
Remove-Item -Recurse -Force logs

# Sync state only (forces full re-download next run)
Get-ChildItem data -Recurse -Filter .sync_state.json | Remove-Item -Force
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Can't connect to MySQL server ... timed out` | Check VPN / security group / host in `conf\.env.kiro` |
| `Unknown AWS profile` | Profile key in `conf\accounts.json` must match `--account` value |
| `ExpiredToken` / `Unauthorized` from S3 | `aws sso login --profile <profile>` |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `python` not found | Use `py`, or add Python to PATH |
| Scheduled task shows `LastRunResult` != 0 | Point Action at `.venv\Scripts\python.exe` (not system python); check `Start in` path |
| Prompt log sync hangs | You forgot `--date` — it's listing 300k+ objects. Ctrl-C and add `--date`. |

---

## Quick Reference

| Action | Command (PowerShell, from repo root) |
|--------|--------------------------|
| Set up venv | `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt` |
| SSO login | `aws sso login --profile <profile>` |
| Sync one account | `python main.py --account <profile>` |
| Force re-download a date | `python main.py --account <profile> --force --date 2026-08-20` |
| Download prompt logs (1 day) | `python main.py --account <profile> --prompt-logs --date 2026-08-22` |
| Read prompts locally | `python read_logs.py prompts --account <id> --date <date> --user <name>` |
| Daily summary | `python read_logs.py summary --account <id> --date <date>` |
| List scheduled task | `Get-ScheduledTask -TaskName "KiroUsageSync-prod"` |
| Run task now | `Start-ScheduledTask -TaskName "KiroUsageSync-prod"` |
| Check DB connectivity | `python -c "import sys;sys.path.insert(0,'.');from db import get_connection;get_connection();print('OK')"` |
