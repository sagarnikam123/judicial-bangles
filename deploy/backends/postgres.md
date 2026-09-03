# PostgreSQL Deployment & Operations Guide

PostgreSQL provides a robust relational backend well-suited for organizations with existing Postgres infrastructure and advanced analytical requirements.

---

## 1. Local Quick Start (Docker Compose)

Launch a local PostgreSQL 17 container pre-configured for Judicial Bangles:

```bash
docker compose -f deploy/compose/docker-compose.postgres.yml up -d
```

- **Host**: `localhost:5432`
- **Database**: `kiro`
- **User**: `root`
- **Password**: `root#123`

To stop:
```bash
docker compose -f deploy/compose/docker-compose.postgres.yml down
```

---

## 2. Local Native Start (macOS Homebrew)

```bash
brew install postgresql@17
brew services start postgresql@17
createdb kiro
```

---

## 3. Configuration (`conf/.env.kiro`)

```bash
STORAGE_BACKEND=postgres

PG_HOST='localhost'
PG_PORT='5432'
PG_DB='kiro'
PG_USER='root'
PG_PASSWORD='root#123'
```

---

## 4. Ingestion Commands

```bash
pip install -r requirements-postgres.txt

# Push all datasets for a specific date
python main.py --account <profile> --backend postgres --date 2026-08-22

# Push ONLY user_report CSVs
python main.py --account <profile> --backend postgres --dataset user_report --date 2026-08-22

# Push existing local files without S3 download
python main.py --account <profile> --backend postgres --load-only
```

---

## 5. CLI Connection

Connect via native `psql`:
```bash
PGPASSWORD='root#123' psql -h 127.0.0.1 -p 5432 -U root -d kiro
```

Or connect inside Docker:
```bash
docker exec -it kiro-postgres psql -U root -d kiro
```

---

## 6. Verification Commands

### Check tables and schemas:
```sql
\dt

\d kiro_user_report
\d kiro_by_user_analytic
\d kiro_prompt_log
```

### Check row counts across all datasets:
```sql
SELECT 'user_report' AS dataset, count(*) FROM kiro_user_report
UNION ALL
SELECT 'by_user_analytic', count(*) FROM kiro_by_user_analytic
UNION ALL
SELECT 'prompt_log', count(*) FROM kiro_prompt_log;
```

### Check daily activity summary:
```sql
SELECT aws_account_id, report_date, count(*) AS active_users
FROM kiro_user_report
GROUP BY aws_account_id, report_date
ORDER BY report_date DESC;
```

---

## 7. Data Analysis Queries

### Top 10 users by total credit consumption:
```sql
SELECT user_id, user_email, subscription_tier, client_type,
       SUM(credits_used) AS total_credits,
       SUM(total_messages) AS total_messages
FROM kiro_user_report
GROUP BY user_id, user_email, subscription_tier, client_type
ORDER BY total_credits DESC
LIMIT 10;
```

### Granular feature activity (CodeFix, Chat, Tests):
```sql
SELECT user_id, report_date,
       chat_conversations_started,
       code_fix_applied_count,
       test_generation_count,
       dev_cycle_duration_seconds
FROM kiro_by_user_analytic
ORDER BY code_fix_applied_count DESC
LIMIT 15;
```

### Cross-table join (Prompt conversations correlated with user emails):
```sql
SELECT p.event_timestamp, u.user_email, p.model_id, p.prompt_char_count, p.response_char_count
FROM kiro_prompt_log p
JOIN kiro_user_report u
  ON p.user_id_normalized = u.user_id
 AND p.aws_account_id = u.aws_account_id
ORDER BY p.event_timestamp DESC
LIMIT 20;
```

---

## 8. Data Deletion Commands

### Delete data for a specific date:
```sql
DELETE FROM kiro_user_report WHERE report_date = '2026-08-22';
DELETE FROM kiro_by_user_analytic WHERE report_date = '2026-08-22';
DELETE FROM kiro_prompt_log WHERE event_timestamp::date = '2026-08-22';
```

### Delete data for a specific AWS account:
```sql
DELETE FROM kiro_user_report WHERE aws_account_id = '073885930324';
DELETE FROM kiro_by_user_analytic WHERE aws_account_id = '073885930324';
DELETE FROM kiro_prompt_log WHERE aws_account_id = '073885930324';
```

### Delete data for a specific user:
```sql
DELETE FROM kiro_user_report WHERE user_id = '51cbc5b0-8091-7097-879b-d425da780157';
DELETE FROM kiro_by_user_analytic WHERE user_id = '51cbc5b0-8091-7097-879b-d425da780157';
DELETE FROM kiro_prompt_log WHERE user_id_normalized = '51cbc5b0-8091-7097-879b-d425da780157';
```

### Purge / Truncate all data in a single pass:
```sql
TRUNCATE TABLE kiro_user_report, kiro_by_user_analytic, kiro_prompt_log RESTART IDENTITY CASCADE;
```

---

## 9. Advanced & Production Deployments

For advanced production deployments, refer to the code samples repository:
👉 [sagarnikam123-blog-youtube-code-samples/postgres/install/](https://github.com/sagarnikam123/sagarnikam123-blog-youtube-code-samples/tree/main/postgres/install)

- **APT/DEB (Debian/Ubuntu)**: `postgres/install/deb/`
- **RPM (RHEL/Rocky/CentOS)**: `postgres/install/rpm/`
- **Homebrew (macOS)**: `postgres/install/brew/`
- **Kubernetes (Helm)**: `postgres/install/helm/` (Bitnami PostgreSQL chart)
- **Kubernetes (Operator)**: `postgres/install/operator/` (CloudNativePG Operator)
