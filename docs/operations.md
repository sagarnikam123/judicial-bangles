# Operations Runbook

End-to-end operational commands for the Kiro usage pipeline across all five backends:
**MySQL, PostgreSQL, ClickHouse, OpenSearch, Elasticsearch.**

Work one backend at a time. Pick your backend, run its column throughout.

## Contents

1. [Download data from S3](#1-download-data-from-s3)
2. [Start a backend (one at a time)](#2-start-a-backend-one-at-a-time)
3. [Create tables / prerequisite setup](#3-create-tables--prerequisite-setup)
4. [Load data into a backend](#4-load-data-into-a-backend)
5. [Instant analysis queries (no Grafana)](#5-instant-analysis-queries-no-grafana)
6. [Truncate data (keep structure)](#6-truncate-data-keep-structure)
7. [Drop tables (delete structure)](#7-drop-tables-delete-structure)

**The three datasets / tables / indexes** (same names everywhere):

| Dataset | Table / index | Unique key | Date column |
|---|---|---|---|
| user reports | `kiro_user_report` | account+date+user+client | `report_date` |
| per-user analytics | `kiro_by_user_analytic` | account+user+date | `report_date` |
| prompt logs | `kiro_prompt_log` | account+request_id | `event_date` |

> Connection settings for every backend live in `conf/.env.kiro` (see `.env.kiro.example`).
> On macOS the client tools are under `/opt/homebrew/opt/<tool>/bin` — commands below assume they're on PATH.

> **Local test accounts** (full admin, created on all SQL/ClickHouse backends):
> `root` / `root#123` and `admin` / `admin#123`. Commands below use `root`.
> **OpenSearch/Elasticsearch** (brew) run with the **security plugin disabled** — no
> auth, the endpoint is open, so no username/password is needed (or possible).

---

## 1. Download data from S3

Downloads raw files to `data/<account_id>/{user_report,by_user_analytic,prompt_logs}/`.
Requires AWS SSO/creds (and VPN if the buckets are private). This step is **backend-independent** — download once, load into any backend after.

```bash
# Log in first (SSO)
aws sso login --profile 853268358782_AdministratorAccess

# Incremental CSV sync (only new files since last run — idempotent via .sync_state.json)
python3 s3_sync.py --account 853268358782_AdministratorAccess

# Prompt logs are high-volume — always scope with --date
python3 s3_sync.py --account 853268358782_AdministratorAccess --prompt-logs --date 2026-08-22

# Force re-download a specific day
python3 s3_sync.py --account 853268358782_AdministratorAccess --force --date 2026-08-20
```

### Once vs cron

```bash
# One-off, full pipeline (download + load into default backend)
python3 main.py --account 853268358782_AdministratorAccess

# Cron — nightly at 03:00 (reports land ~02:00 UTC). Edit with `crontab -e`:
0 3 * * * cd /Users/snikam/Documents/git/judicial-bangles && /usr/bin/python3 main.py --account 853268358782_AdministratorAccess >> logs/cron.log 2>&1
```

> `download only` = `s3_sync.py`; `download + load` = `main.py`. See [Section 4](#4-load-data-into-a-backend).

---

## 2. Start a backend (one at a time)

Run only the backend you're using. All bind to localhost.

### MySQL
```bash
brew services start mysql
mysqladmin -u root ping          # -> "mysqld is alive"
```

### PostgreSQL
```bash
brew services start postgresql@18
pg_isready -h 127.0.0.1 -p 5432  # -> "accepting connections"
```

### ClickHouse
```bash
# No brew service — run the binary (background). Data in ~/clickhouse-data.
mkdir -p ~/clickhouse-data
( cd ~/clickhouse-data && clickhouse server > ~/clickhouse-data/server.log 2>&1 & )
curl -s http://localhost:8123/ping   # -> "Ok."
```

### OpenSearch
```bash
brew services start opensearch
curl -s http://localhost:9200 | grep number   # -> "number" : "3.8.0"
```

### Elasticsearch
```bash
# ES defaults to 9200 too — stop OpenSearch first, or run ES on another port.
brew services start elasticsearch          # or: elasticsearch -Ehttp.port=9201
curl -s http://localhost:9200              # cluster info JSON
```

> **Stop** any backend: `brew services stop <name>` (MySQL/PG/OpenSearch/ES).
> ClickHouse: `pkill -f "clickhouse server"`.

---

## 3. Create tables / prerequisite setup

**You do not need to pre-create tables** — every writer runs `init_schema()` lazily on first write, generating the correct DDL/mapping per backend. Section 4 creates them automatically.

Prerequisites are just the target database existing (the `root`/`admin` accounts
already have full access; the writer auto-creates the `kiro` database on ClickHouse).

### MySQL
```bash
mysql -u root -p'root#123' -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS kiro CHARACTER SET utf8mb4;"
```

### PostgreSQL
```bash
PGPASSWORD='root#123' createdb -U root -h 127.0.0.1 kiro 2>/dev/null || true
```

### ClickHouse
```bash
# The writer auto-creates it; to do it manually:
curl -s http://localhost:8123/ --user "root:root#123" -d "CREATE DATABASE IF NOT EXISTS kiro"
```

<details><summary>Create the two test accounts (already done on your machine)</summary>

```bash
# MySQL
mysql -u root -e "
ALTER USER 'root'@'localhost' IDENTIFIED BY 'root#123';
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY 'root#123';
CREATE USER IF NOT EXISTS 'admin'@'127.0.0.1' IDENTIFIED BY 'admin#123';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1', 'admin'@'127.0.0.1' WITH GRANT OPTION;
FLUSH PRIVILEGES;"

# PostgreSQL
psql -d postgres -c "CREATE ROLE root  LOGIN SUPERUSER PASSWORD 'root#123';"
psql -d postgres -c "CREATE ROLE admin LOGIN SUPERUSER PASSWORD 'admin#123';"

# ClickHouse (default user has access management in the brew/cask build)
curl -s http://localhost:8123/ -d "CREATE USER IF NOT EXISTS root  IDENTIFIED BY 'root#123'"
curl -s http://localhost:8123/ -d "CREATE USER IF NOT EXISTS admin IDENTIFIED BY 'admin#123'"
curl -s http://localhost:8123/ -d "GRANT CURRENT GRANTS ON *.* TO root  WITH GRANT OPTION"
curl -s http://localhost:8123/ -d "GRANT CURRENT GRANTS ON *.* TO admin WITH GRANT OPTION"
curl -s http://localhost:8123/ -d "GRANT ACCESS MANAGEMENT ON *.* TO root, admin"
```
</details>

### OpenSearch / Elasticsearch
No setup needed — indexes (`kiro-kiro_user_report`, etc.) are created on first write with generated field mappings.

> To inspect the exact generated DDL without loading anything:
> ```bash
> python3 -c "from writers.mysql_writer import MySQLWriter; from writers.base import DATASETS;
> w=MySQLWriter();
> print(chr(10).join(w._ddl(d) for d in DATASETS.values()))"
> ```
> (swap `MySQLWriter`→`PostgresWriter`/`ClickHouseWriter` for other dialects)

---

## 4. Load data into a backend

Loads already-downloaded local files. Pick **one** `--backend`. `user_report` + `by_user_analytic` always load; add `--prompt-logs` for prompt data.

```bash
# Full pipeline: download from S3 THEN load into the chosen backend
python3 main.py --account 853268358782_AdministratorAccess --backend mysql
python3 main.py --account 853268358782_AdministratorAccess --backend postgres
python3 main.py --account 853268358782_AdministratorAccess --backend clickhouse    --prompt-logs --date 2026-08-22
python3 main.py --account 853268358782_AdministratorAccess --backend opensearch    --prompt-logs --date 2026-08-22
python3 main.py --account 853268358782_AdministratorAccess --backend elasticsearch --prompt-logs --date 2026-08-22
```

### Load-only (skip S3 — reuse local files, no VPN)

```bash
# Loads data/<account_id>/... into <backend> without touching S3
python3 -c "
from main import load_all
print(load_all('853268358782', 'prod', backend='clickhouse', prompt_logs=True))
"
```

All loads are **idempotent** — re-running upserts on the unique key (SQL), overwrites by deterministic `_id` (search), or dedups via `ReplacingMergeTree` (ClickHouse). Re-run safely.

> `--store-text` (SQL backends): also store full prompt/response text (default: metadata only). Search backends always index the text.

---

## 5. Instant analysis queries (no Grafana)

Quick CLI checks. Full analytics library is in [`queries.sql`](queries.sql) (MySQL/Postgres SQL).

### Row / doc counts (sanity check after a load)

**MySQL**
```bash
mysql -u root -p'root#123' -h 127.0.0.1 kiro -e "
SELECT 'user_report' t, COUNT(*) FROM kiro_user_report
UNION ALL SELECT 'by_user_analytic', COUNT(*) FROM kiro_by_user_analytic
UNION ALL SELECT 'prompt_log', COUNT(*) FROM kiro_prompt_log;"
```

**PostgreSQL**
```bash
PGPASSWORD='root#123' psql -U root -h 127.0.0.1 -d kiro -c "
SELECT 'user_report' t, COUNT(*) FROM kiro_user_report
UNION ALL SELECT 'by_user_analytic', COUNT(*) FROM kiro_by_user_analytic
UNION ALL SELECT 'prompt_log', COUNT(*) FROM kiro_prompt_log;"
```

**ClickHouse** (use `FINAL` for the deduped view)
```bash
curl -s http://localhost:8123/ --user "root:root#123" -d "
SELECT 'user_report' t, count() FROM kiro.kiro_user_report FINAL
UNION ALL SELECT 'by_user_analytic', count() FROM kiro.kiro_by_user_analytic FINAL
UNION ALL SELECT 'prompt_log', count() FROM kiro.kiro_prompt_log FINAL FORMAT PrettyCompact"
```

**OpenSearch / Elasticsearch**
```bash
curl -s "http://localhost:9200/_cat/indices/kiro-*?v&h=index,docs.count&s=index"
```

### Example analytics

**Top credit consumers this month (MySQL/Postgres)**
```sql
SELECT user_email, SUM(credits_used) AS credits, SUM(total_messages) AS msgs
FROM kiro_user_report
WHERE report_date >= DATE_TRUNC('month', CURRENT_DATE)   -- MySQL: DATE_FORMAT(CURDATE(),'%Y-%m-01')
GROUP BY user_email ORDER BY credits DESC LIMIT 10;
```

**Prompt requests by model (ClickHouse)**
```bash
curl -s http://localhost:8123/ --user "root:root#123" -d "
SELECT model_id, count() reqs FROM kiro.kiro_prompt_log FINAL
GROUP BY model_id ORDER BY reqs DESC FORMAT PrettyCompact"
```

**Full-text search prompts for a keyword (OpenSearch — its strength)**
```bash
curl -s "http://localhost:9200/kiro-kiro_prompt_log/_search?size=5" -H 'Content-Type: application/json' -d '{
  "query": { "match": { "prompt_text": "terraform" } },
  "_source": ["event_time","user_id_normalized","model_id"]
}'
```

**Aggregation: requests per day (OpenSearch)**
```bash
curl -s "http://localhost:9200/kiro-kiro_prompt_log/_search?size=0" -H 'Content-Type: application/json' -d '{
  "aggs": { "per_day": { "date_histogram": { "field": "event_date", "calendar_interval": "day" } } }
}'
```

---

## 6. Truncate data (keep structure)

Empties tables/indexes but keeps schema — re-loadable immediately.

### MySQL
```bash
mysql -u root -p'root#123' -h 127.0.0.1 kiro -e "
TRUNCATE TABLE kiro_user_report;
TRUNCATE TABLE kiro_by_user_analytic;
TRUNCATE TABLE kiro_prompt_log;"
```

### PostgreSQL
```bash
PGPASSWORD='root#123' psql -U root -h 127.0.0.1 -d kiro -c "
TRUNCATE kiro_user_report, kiro_by_user_analytic, kiro_prompt_log RESTART IDENTITY;"
```

### ClickHouse
```bash
for t in kiro_user_report kiro_by_user_analytic kiro_prompt_log; do
  curl -s http://localhost:8123/ --user "root:root#123" -d "TRUNCATE TABLE kiro.$t"; done
```

### OpenSearch / Elasticsearch
No `TRUNCATE` — delete all docs but keep the index + mapping:
```bash
for i in kiro-kiro_user_report kiro-kiro_by_user_analytic kiro-kiro_prompt_log; do
  curl -s -XPOST "http://localhost:9200/$i/_delete_by_query" -H 'Content-Type: application/json' \
    -d '{"query":{"match_all":{}}}'; done
```

---

## 7. Drop tables (delete structure)

Removes tables/indexes entirely. Next load recreates them (Section 4).

### MySQL
```bash
mysql -u root -p'root#123' -h 127.0.0.1 kiro -e "
DROP TABLE IF EXISTS kiro_user_report, kiro_by_user_analytic, kiro_prompt_log;"
```

### PostgreSQL
```bash
PGPASSWORD='root#123' psql -U root -h 127.0.0.1 -d kiro -c "
DROP TABLE IF EXISTS kiro_user_report, kiro_by_user_analytic, kiro_prompt_log;"
```

### ClickHouse
```bash
for t in kiro_user_report kiro_by_user_analytic kiro_prompt_log; do
  curl -s http://localhost:8123/ --user "root:root#123" -d "DROP TABLE IF EXISTS kiro.$t"; done
# Drop the whole database instead:
# curl -s http://localhost:8123/ --user "root:root#123" -d "DROP DATABASE IF EXISTS kiro"
```

### OpenSearch / Elasticsearch
```bash
curl -s -XDELETE "http://localhost:9200/kiro-kiro_user_report,kiro-kiro_by_user_analytic,kiro-kiro_prompt_log"
```

> ⚠️ Sections 6 and 7 are destructive. Data can be reloaded from `data/` (or re-downloaded from S3), so local files are your backup — don't delete `data/` unless you've re-synced.
