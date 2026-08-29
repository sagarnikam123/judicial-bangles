# Judicial Bangles

Syncs Kiro (Amazon Q Developer) usage reports from S3 into MySQL for analysis and Grafana dashboards.

Two AWS accounts run Kiro independently (prod + dev), each writing daily CSV reports — and in one account, prompt logs — to their own S3 buckets. This project pulls both, tags every row with the source AWS account, and loads them into shared MySQL tables so Grafana can slice by account via a dropdown.

---

## AWS Accounts

Accounts are defined in `conf/accounts.json` (gitignored — copy `conf/accounts.json.example` and fill in your own). The account IDs below are **placeholders** for illustration.

| Profile | Account ID | Label |
|---|---|---|
| `111111111111_AdministratorAccess` | `111111111111` | **prod** |
| `222222222222_AdministratorAccess` | `222222222222` | **dev** |

If both accounts are wired to the same AWS IAM Identity Center directory, the same users appear in both — one workforce accessing two Kiro deployments (e.g. prod/dev), not two sets of users. The pipeline tags every row with its source `aws_account_id` so you can filter by account in Grafana.

---

## S3 Buckets & Folder Structure

Three buckets total, across two accounts. Grouped below so structurally similar buckets sit next to each other.

### Daily CSV reports — user_report & by_user_analytic

These two buckets share **identical folder structure** (only the account ID differs):

```
s3://my-org-kiro-usage-activity-report/              (prod · 111111111111)
s3://my-org-kiro-usage-report-dev/                    (dev  · 222222222222)
│
└── reports/
    └── AWSLogs/<account-id>/KiroLogs/
        │
        ├── user_report/us-east-1/<YYYY>/<MM>/<DD>/00/
        │   ├── KIRO_IDE_<account-id>_user_report_<YYYYMMDDHHmm>.csv
        │   ├── KIRO_CLI_<account-id>_user_report_<YYYYMMDDHHmm>.csv
        │   └── PLUGIN_<account-id>_user_report_<YYYYMMDDHHmm>.csv      (dev only — prod has no PLUGIN client type)
        │
        └── by_user_analytic/us-east-1/<YYYY>/<MM>/<DD>/00/
            └── <account-id>_by_user_analytic_<YYYYMMDDHHmm>_report.csv
```

**user_report columns:** `Date, UserId, Client_Type, Chat_Conversations, Credits_Used, Overage_Cap, Overage_Credits_Used, Overage_Enabled, ProfileId, Subscription_Tier, Total_Messages, New_User, User_Email, <model>_messages...`
(dev has more `<model>_messages` columns than prod — auto, claude_opus_4.6/4.8/5, claude_sonnet_4.5/4.6/5, gpt_5.6_luna/sol, qwen3_coder_next)

**by_user_analytic columns:** `UserId, Date, Chat_*, CodeFix_*, CodeReview_*, Dev_*, DocGeneration_*, InlineChat_*, Inline_*, TestGeneration_*, Transformation_*` (46 columns — feature-level usage detail)

### Prompt logs — full conversation content

These two buckets/prefixes share the **same downstream structure** (`GenerateAssistantResponse/`) but differ in top-level prefix naming and one has an extra event type:

```
s3://my-org-kiro-usage-report/                         (prod · 111111111111)
└── Prompt_Logging/Prompt_Logging/AWSLogs/111111111111/KiroLogs/
    └── GenerateAssistantResponse/us-east-1/<YYYY>/<MM>/<DD>/<HH>/
        └── 111111111111_GenerateAssistantResponse_<YYYYMMDDHHmm>_<id>.json.gz
        (STOPPED after 2026-07-31 — no new files since; console still shows enabled)

s3://my-org-kiro-usage-report-dev/                      (dev  · 222222222222)
└── prompt-logs/AWSLogs/222222222222/KiroLogs/
    ├── GenerateAssistantResponse/us-east-1/<YYYY>/<MM>/<DD>/<HH>/
    │   └── 222222222222_GenerateAssistantResponse_<YYYYMMDDHHmm>_<id>.json.gz
    │
    └── GenerateCompletions/us-east-1/<YYYY>/<MM>/<DD>/<HH>/           (dev only — inline completions)
        └── 222222222222_GenerateCompletions_<YYYYMMDDHHmm>_<id>.json.gz
```

**JSON schema (gzipped):**
```json
{
  "records": [{
    "generateAssistantResponseEventRequest": {
      "prompt": "...",
      "chatTriggerType": "MANUAL",
      "userId": "<idc-user-id>",
      "timeStamp": "2026-07-18T00:22:17.156616451Z",
      "modelId": "claude-opus-4.6"
    },
    "generateAssistantResponseEventResponse": {
      "assistantResponse": "...",
      "codeReferenceEvents": [],
      "requestId": "<uuid>"
    }
  }]
}
```

> Note: dev's prompt-logs bucket is currently the only one with live prompt log data (245 MB / 313k+ files as of Aug 25, 2026). Use `--prompt-logs --date <YYYY-MM-DD>` to download a specific day's worth. Prompt logs are downloaded only, not loaded into MySQL (yet).

---

## Local Data Layout

The sync mirrors S3 into `data/`, scoped per account, flattened per report type (original AWS filenames preserved):

```
data/
├── 111111111111/                          # prod
│   ├── .sync_state.json                   # watermark + downloaded-file tracking
│   ├── user_report/
│   │   └── KIRO_IDE_111111111111_user_report_202607300000.csv
│   ├── by_user_analytic/
│   │   └── 111111111111_by_user_analytic_202608240000_report.csv
│   └── prompt_logs/                       # only if --prompt-logs was used
│       └── 111111111111_GenerateAssistantResponse_202607180022_3SOS7oQUc5UOH6k2.json.gz
│
└── 222222222222/                          # dev
    ├── .sync_state.json
    ├── user_report/
    │   ├── KIRO_IDE_222222222222_user_report_202608240000.csv
    │   ├── KIRO_CLI_222222222222_user_report_202608240000.csv
    │   └── PLUGIN_222222222222_user_report_202608240000.csv
    ├── by_user_analytic/
    │   └── 222222222222_by_user_analytic_202608240000_report.csv
    └── prompt_logs/                       # only if --prompt-logs was used
        └── 222222222222_GenerateAssistantResponse_202608220157_jx1201brM8o2tGoq.json.gz
```

Files older than `DATA_RETENTION_DAYS` (default 30, set in `conf/.env.kiro`) are purged automatically at the start of each sync.

---

## Data Flow

```
                    ┌──────────────────────┐        ┌──────────────────────┐
                    │   AWS Account: prod   │        │   AWS Account: dev    │
                    │    111111111111       │        │    222222222222       │
                    └──────────┬───────────┘        └──────────┬───────────┘
                               │                                │
                     Kiro writes daily CSVs              Kiro writes daily CSVs
                     (~2 AM UTC) + prompt logs            + prompt logs (live)
                               │                                │
                               ▼                                ▼
                    s3://my-org-kiro-        s3://my-org-kiro-usage-
                    usage-activity-report/         report-dev/
                    (+ ...usage-report/ for
                     prompt logs, stopped)
                               │                                │
                               └───────────────┬────────────────┘
                                                │
                                     python main.py --account <profile>
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        ▼                       ▼                       ▼
                 1. enforce_retention()   2. sync_all() (s3_sync.py)   (repeat per account)
                 delete local files       list S3 objects newer than
                 older than 30 days       watermark, skip files already
                 (per account dir)        on disk (idempotent),
                                          download to data/<account_id>/
                        │                       │
                        └───────────────────────┤
                                                 ▼
                                   3. load_all_local_csvs() (main.py)
                                   parse every local CSV with pandas,
                                   tag each row with aws_account_id +
                                   account_label
                                                 │
                                                 ▼
                                   4. upsert_*_rows() (db.py)
                                   ON DUPLICATE KEY UPDATE into MySQL
                                   (idempotent — safe to re-run)
                                                 │
                                                 ▼
                                   ┌─────────────────────────────┐
                                   │   MySQL (devops schema)      │
                                   │   kiro_user_report            │
                                   │   kiro_by_user_analytic       │
                                   │   (both indexed on            │
                                   │    aws_account_id)            │
                                   └──────────────┬───────────────┘
                                                  ▼
                                        Grafana (MySQL datasource)
                                        template variable:
                                        SELECT DISTINCT account_label
                                        FROM kiro_user_report
                                        → dropdown filters every panel
```

### Step-by-step

1. **Retention sweep** — before touching S3, delete local files in `data/<account_id>/` older than `DATA_RETENTION_DAYS` (default 30) and prune them from that account's `.sync_state.json`.
2. **Incremental S3 sync** (`s3_sync.py`) — list objects under the account's `user_report/` and `by_user_analytic/` prefixes, filtered by the last-synced watermark stored in `.sync_state.json`. Files already downloaded (tracked by path) are skipped — safe to run the script any number of times without re-downloading. `--force` (optionally with `--date`) clears that day's local files and re-pulls them from S3.
3. **Parse** (`main.py`) — every local CSV in `data/<account_id>/{user_report,by_user_analytic}/` is read with pandas, values are type-coerced (`_safe_int`, `_safe_float`, `_parse_bool`, `_parse_date`), and each row is tagged with `aws_account_id` + `account_label` so multiple accounts can share one table.
4. **Load** (`db.py`) — rows are batch-upserted into MySQL using `ON DUPLICATE KEY UPDATE`, keyed on `(aws_account_id, report_date, user_id, client_type)` for `kiro_user_report` and `(aws_account_id, user_id, report_date)` for `kiro_by_user_analytic`. Idempotent — re-running the same day's data just overwrites with identical values.
5. **Visualize** — Grafana connects to MySQL directly. A dashboard variable (`SELECT DISTINCT account_label FROM kiro_user_report`) becomes a dropdown; every panel query filters `WHERE account_label = '$account'`.

### Running it

See the full CLI reference below.

---

## CLI Usage

Both `main.py` (full pipeline: sync + parse + DB load) and `s3_sync.py` (download only, no DB) accept the same core flags.

### Arguments

| Flag | Description | Default |
|---|---|---|
| `--account <profile>` | AWS profile name (key in `conf/config.py` ACCOUNTS) | `111111111111_AdministratorAccess` (prod) |
| `--date <YYYY-MM-DD>` | Target a specific date (only syncs files for that day) | None (syncs all new files) |
| `--force` | Re-download files for the target date (deletes local copies first) | Off (incremental/idempotent) |
| `--prompt-logs` | Also download prompt log `.json.gz` files (opt-in, high file count) | Off (only CSVs) |
| `--full` | (main.py only) Re-parse ALL local CSVs into DB regardless of sync | Off |

### Examples

```bash
# ─────────────────────────────────────────────────────────────────────────────
# DAILY CRON — incremental sync + DB load (only new files since last run)
# ─────────────────────────────────────────────────────────────────────────────

# Sync prod account (CSVs only, load into MySQL)
python main.py --account 111111111111_AdministratorAccess

# Sync dev account
python main.py --account 222222222222_AdministratorAccess

# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD ONLY (no DB load) — just get files locally
# ─────────────────────────────────────────────────────────────────────────────

# Download only new CSVs (user_report + by_user_analytic) for dev
python s3_sync.py --account 222222222222_AdministratorAccess

# Download only new CSVs for prod
python s3_sync.py --account 111111111111_AdministratorAccess

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT LOGS — opt-in download (gzipped JSON, full conversations)
# ─────────────────────────────────────────────────────────────────────────────

# Download prompt logs for a specific date (recommended — limits file count)
python s3_sync.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22

# Download prompt logs for today
python s3_sync.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-25

# Download prompt logs for prod (only Jul 18-31 data exists)
python s3_sync.py --account 111111111111_AdministratorAccess --prompt-logs --date 2026-07-18

# Download ALL prompt logs incrementally (WARNING: 300k+ files in dev, ~245MB)
python s3_sync.py --account 222222222222_AdministratorAccess --prompt-logs

# Download prompt logs AND sync CSVs + load DB in one shot
python main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-22

# ─────────────────────────────────────────────────────────────────────────────
# FORCE RE-DOWNLOAD — re-fetch files for a specific date
# ─────────────────────────────────────────────────────────────────────────────

# Force re-download today's CSVs (deletes local copies for today, re-pulls)
python main.py --account 222222222222_AdministratorAccess --force

# Force re-download a specific day's CSVs
python main.py --account 222222222222_AdministratorAccess --force --date 2026-08-20

# Force re-download a specific day's prompt logs
python s3_sync.py --account 222222222222_AdministratorAccess --prompt-logs --force --date 2026-08-22

# ─────────────────────────────────────────────────────────────────────────────
# FULL DB RELOAD — re-parse ALL local CSVs into MySQL (idempotent upsert)
# ─────────────────────────────────────────────────────────────────────────────

# Useful after schema change or if DB was cleared
python main.py --account 111111111111_AdministratorAccess --full
python main.py --account 222222222222_AdministratorAccess --full

# ─────────────────────────────────────────────────────────────────────────────
# COMBINED — sync both accounts for a date, including prompt logs
# ─────────────────────────────────────────────────────────────────────────────

python main.py --account 111111111111_AdministratorAccess --prompt-logs --date 2026-07-30
python main.py --account 222222222222_AdministratorAccess --prompt-logs --date 2026-08-24

# ─────────────────────────────────────────────────────────────────────────────
# QUICK CHECK — see what's downloaded locally without hitting S3 or DB
# ─────────────────────────────────────────────────────────────────────────────

ls data/222222222222/user_report/ | wc -l         # count user_report CSVs
ls data/222222222222/prompt_logs/ | wc -l         # count downloaded prompt logs
gunzip -c data/222222222222/prompt_logs/<file>.json.gz | python -m json.tool | less  # read a prompt log
```

### Cron setup (example)

Run once at 3 AM UTC nightly — both accounts, staggered by 5 minutes:

```bash
# Open your crontab for editing
crontab -e

# Paste these two lines:
0 3 * * * cd /path/to/kiro-usage-analytics && /opt/homebrew/bin/python3 main.py --account 111111111111_AdministratorAccess >> logs/prod.log 2>&1
5 3 * * * cd /path/to/kiro-usage-analytics && /opt/homebrew/bin/python3 main.py --account 222222222222_AdministratorAccess >> logs/dev.log 2>&1
```

> Use full path to python (`/opt/homebrew/bin/python3`) because cron doesn't load your shell profile.
> Create the logs dir first: `mkdir -p /path/to/kiro-usage-analytics/logs`

Verify it saved:

```bash
crontab -l
```

### Local file output

After running, files land at:

```
data/<account_id>/
├── .sync_state.json           # tracks watermark + downloaded files (do not edit)
├── user_report/               # daily credit/subscription CSVs
│   └── KIRO_IDE_<id>_user_report_<YYYYMMDDHHmm>.csv
├── by_user_analytic/          # daily feature-usage CSVs
│   └── <id>_by_user_analytic_<YYYYMMDDHHmm>_report.csv
└── prompt_logs/               # gzipped JSON (only if --prompt-logs was used)
    └── <id>_GenerateAssistantResponse_<YYYYMMDDHHmm>_<uid>.json.gz
```

### Idempotency rules

| Scenario | Behavior |
|---|---|
| Run same command twice | Zero extra downloads — files on disk + tracked in state = skipped |
| Run with `--force` | Deletes local files matching target date's YYYYMMDD, re-downloads from S3 |
| Run with `--force --date 2026-08-20` | Only touches Aug 20 files, leaves everything else intact |
| DB upserts | Keyed on `(aws_account_id, report_date, user_id, client_type)` — idempotent overwrite |
| Retention | Files older than `DATA_RETENTION_DAYS` (default 30) auto-deleted at start of each sync |
| Prompt logs without `--date` | Downloads ALL new files since last watermark (could be 300k+ in dev — use `--date`!) |

---

## MySQL Schema

Target: existing shared MySQL instance, credentials in `conf/.env.kiro` (`TEST_DEVOPS_DB_*`).

| Table | Grain | Key columns |
|---|---|---|
| `kiro_user_report` | 1 row per account + date + user + client_type | `credits_used`, `subscription_tier`, `total_messages`, per-model message counts |
| `kiro_by_user_analytic` | 1 row per account + date + user | 46 feature-usage columns (chat, code fix, code review, inline, doc gen, test gen, transformation) |

Both tables carry `aws_account_id` + `account_label` (indexed) for Grafana filtering, and a unique key including `aws_account_id` so the same `user_id` can appear in both accounts without collision.

---

## UserId Format & Cross-File Matching

The same user has **different userId formats** across the three file types. This is critical when joining data or filtering by user.

### Formats per file type

| File type | userId example | Format |
|---|---|---|
| `user_report` CSV | `d0d0d0d0d0-aaaaaaaa-1111-2222-3333-444444444444` | `<idc_instance_id>-<user_uuid>` |
| `by_user_analytic` CSV | `d0d0d0d0d0-aaaaaaaa-1111-2222-3333-444444444444` | Same as user_report |
| `prompt_logs` JSON | `d-d0d0d0d0d0.aaaaaaaa-1111-2222-3333-444444444444` | `d-<idc_instance_id>.<user_uuid>` |

### Anatomy

```
user_report format:     d0d0d0d0d0-aaaaaaaa-1111-2222-3333-444444444444
                        ├─────────┘ ├──────────────────────────────────┘
                        IdC instance ID     User UUID (from Identity Center)

prompt_logs format:   d-d0d0d0d0d0.aaaaaaaa-1111-2222-3333-444444444444
                      ├┘├─────────┘├┘├──────────────────────────────────┘
                      prefix  IdC ID separator   Same User UUID
```

- `d0d0d0d0d0` = your IAM Identity Center instance ID (shared across all users in your org)
- `aaaaaaaa-1111-2222-3333-444444444444` = the user's actual unique ID within Identity Center
- The `d-` prefix and `.` separator are only used in prompt_logs

### Conversion rules

```
prompt_logs → user_report:  strip "d-" prefix, replace first "." with "-"
user_report → prompt_logs:  split on first "-" (10-char prefix), prepend "d-", join with "."
```

### How `read_logs.py` handles this

When you pass `--user jdoe` (or any email/name fragment):
1. Searches `user_report` CSVs for matching `User_Email`
2. Gets the user_report-format userId (e.g., `d0d0d0d0d0-aaaaaaaa-...`)
3. Generates BOTH formats (user_report + prompt_logs) for matching
4. Filters records by checking if either format appears in the record's userId field

This means `--user jdoe` works transparently across all three commands (`prompts`, `credits`, `activity`) without you needing to know the format.

### For SQL / Grafana JOINs

To join `kiro_user_report` with prompt log metadata (if loaded to DB in future):

```sql
-- prompt_logs userId: d-d0d0d0d0d0.aaaaaaaa-1111-2222-3333-444444444444
-- user_report userId: d0d0d0d0d0-aaaaaaaa-1111-2222-3333-444444444444
-- Conversion: REPLACE(REPLACE(prompt_log_user_id, 'd-', ''), '.', '-')

SELECT r.user_email, p.*
FROM kiro_prompt_log p
JOIN kiro_user_report r
  ON r.user_id = REPLACE(REPLACE(p.user_id, 'd-', ''), '.', '-')
WHERE r.account_label = '$account_label';
```

---

## Configuration

Two config files live in `conf/` — both are gitignored; copy the `.example` versions and fill in your own values.

**1. `conf/.env.kiro`** (DB credentials + settings) — copy from `conf/.env.kiro.example`:

```bash
TEST_DEVOPS_DB_HOST=your-mysql-host.example.com
TEST_DEVOPS_DB_NAME=your_database
TEST_DEVOPS_DB_PORT=3306
TEST_DEVOPS_DB_USER=your_db_user
TEST_DEVOPS_DB_PASSWORD=your_db_password

AWS_PROFILE=111111111111_AdministratorAccess   # default profile (key in accounts.json)
AWS_REGION_DEFAULT=us-east-1
DATA_RETENTION_DAYS=30
```

**2. `conf/accounts.json`** (AWS account/bucket registry) — copy from `conf/accounts.json.example`:

Maps each AWS profile name → account ID, label, region, and S3 bucket/prefix paths. Add a new account by adding an entry. The profile name is what you pass to `--account`.

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

### Setup

```bash
cp conf/.env.kiro.example conf/.env.kiro          # then edit with your DB creds
cp conf/accounts.json.example conf/accounts.json  # then edit with your AWS accounts
pip install -r requirements.txt
python main.py --account <your_profile_name>
```

---

## Roadmap / Not Yet Implemented

- **Prompt log DB ingestion** — prompt logs can be downloaded (`--prompt-logs`) but are NOT loaded into MySQL yet. They're gzipped JSON with full conversation content — needs a flattened metadata table or document store if you want to query them from Grafana. For now, read them locally with `gunzip -c <file> | python -m json.tool`.
- **GenerateCompletions** — dev account also has inline completion logs (`GenerateCompletions/`), not yet synced. Same format as `GenerateAssistantResponse` but for autocomplete events.
- **Grafana dashboard** — not yet provisioned; `queries.sql` has all the panel queries ready to copy-paste.
