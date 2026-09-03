# ClickHouse Deployment & Operations Guide

ClickHouse is an open-source, columnar database management system engineered for blazing-fast analytics over millions of prompt logs and high-volume usage events.

---

## 1. Local Quick Start (Docker Compose)

Launch a local ClickHouse 25.5 server:

```bash
docker compose -f deploy/compose/docker-compose.clickhouse.yml up -d
```

- **HTTP API**: `http://localhost:8123`
- **Native Port**: `9000`
- **Database**: `kiro`
- **User**: `root`
- **Password**: `root#123`

To stop:
```bash
docker compose -f deploy/compose/docker-compose.clickhouse.yml down
```

---

## 2. Local Native Start (macOS Homebrew / Binary)

```bash
brew install clickhouse
mkdir -p ~/clickhouse-data
( cd ~/clickhouse-data && clickhouse server > ~/clickhouse-data/server.log 2>&1 & )

# Verify:
curl -s http://localhost:8123/ping   # -> Ok.
```

---

## 3. Configuration (`conf/.env.kiro`)

```bash
STORAGE_BACKEND=clickhouse

CLICKHOUSE_HOST='localhost'
CLICKHOUSE_PORT='8123'
CLICKHOUSE_DB='kiro'
CLICKHOUSE_USER='root'
CLICKHOUSE_PASSWORD='root#123'
```

---

## 4. Ingestion Commands

```bash
pip install -r requirements-clickhouse.txt

# Push all datasets for a specific date
python main.py --account <profile> --backend clickhouse --date 2026-08-22

# Push ONLY prompt logs
python main.py --account <profile> --backend clickhouse --dataset prompt_logs --date 2026-08-22

# Push existing local files without S3 download
python main.py --account <profile> --backend clickhouse --dataset prompt_logs --load-only
```

---

## 5. CLI Connection

Connect via native `clickhouse-client`:
```bash
clickhouse-client --host 127.0.0.1 --port 9000 --user root --password 'root#123' --database kiro
```

Or connect inside Docker:
```bash
docker exec -it kiro-clickhouse clickhouse-client --user root --password 'root#123' --database kiro
```

Or execute queries via HTTP `curl`:
```bash
curl -s -u 'root:root#123' 'http://localhost:8123/' --data 'SELECT count() FROM kiro.kiro_prompt_log'
```

---

## 6. Verification Commands

### Check tables and engines:
```sql
SHOW TABLES FROM kiro;

DESCRIBE TABLE kiro_prompt_log;
```

### Check record counts across all datasets:
```sql
SELECT 'user_report' AS dataset, count() AS total FROM kiro.kiro_user_report
UNION ALL
SELECT 'by_user_analytic', count() FROM kiro.kiro_by_user_analytic
UNION ALL
SELECT 'prompt_log', count() FROM kiro.kiro_prompt_log;
```

### Check partition parts and disk sizes:
```sql
SELECT table, count() AS parts, formatReadableSize(sum(bytes_on_disk)) AS size_on_disk
FROM system.parts
WHERE database = 'kiro' AND active = 1
GROUP BY table;
```

---

## 7. High-Performance Analytical Queries

### Prompt volume, token/char metrics, and latency by model:
```sql
SELECT
    model_id,
    count() AS total_invocations,
    sum(has_code_in_response) AS responses_with_code,
    round(avg(prompt_char_count)) AS avg_prompt_len,
    round(avg(response_char_count)) AS avg_response_len,
    quantile(0.95)(prompt_char_count) AS p95_prompt_len
FROM kiro.kiro_prompt_log
GROUP BY model_id
ORDER BY total_invocations DESC;
```

### Daily usage trends across models:
```sql
SELECT
    toDate(event_timestamp) AS day,
    model_id,
    count() AS requests
FROM kiro.kiro_prompt_log
GROUP BY day, model_id
ORDER BY day DESC, requests DESC;
```

### Top active users across Identity Center:
```sql
SELECT
    user_id_normalized,
    count() AS prompts_sent,
    sum(has_code_in_response) AS code_blocks_generated
FROM kiro.kiro_prompt_log
GROUP BY user_id_normalized
ORDER BY prompts_sent DESC
LIMIT 10;
```

---

## 8. Data Deletion Commands

ClickHouse executes row deletions as asynchronous lightweight mutations:

### Delete data for a specific date:
```sql
ALTER TABLE kiro.kiro_user_report DELETE WHERE report_date = '2026-08-22';
ALTER TABLE kiro.kiro_by_user_analytic DELETE WHERE report_date = '2026-08-22';
ALTER TABLE kiro.kiro_prompt_log DELETE WHERE toDate(event_timestamp) = '2026-08-22';
```

### Delete data for a specific AWS account:
```sql
ALTER TABLE kiro.kiro_user_report DELETE WHERE aws_account_id = '073885930324';
ALTER TABLE kiro.kiro_by_user_analytic DELETE WHERE aws_account_id = '073885930324';
ALTER TABLE kiro.kiro_prompt_log DELETE WHERE aws_account_id = '073885930324';
```

### Purge / Truncate all data in a single pass:
```sql
TRUNCATE TABLE kiro.kiro_user_report;
TRUNCATE TABLE kiro.kiro_by_user_analytic;
TRUNCATE TABLE kiro.kiro_prompt_log;
```

---

## 9. Advanced & Production Deployments

For advanced production deployments, refer to the code samples repository:
👉 [sagarnikam123-blog-youtube-code-samples/clickhouse/install/](https://github.com/sagarnikam123/sagarnikam123-blog-youtube-code-samples/tree/main/clickhouse/install)

- **APT/DEB (Debian/Ubuntu)**: `clickhouse/install/deb/`
- **RPM (RHEL/Rocky/CentOS)**: `clickhouse/install/rpm/`
- **Homebrew (macOS)**: `clickhouse/install/brew/`
- **Kubernetes (Helm)**: `clickhouse/install/helm/` (Bitnami ClickHouse chart)
- **Kubernetes (Operator)**: `clickhouse/install/operator/` (Altinity ClickHouse Operator)
