# MySQL Deployment & Operations Guide

MySQL is the default relational storage backend for Judicial Bangles.

---

## 1. Local Quick Start (Docker Compose)

Launch a local MySQL 8.4 container pre-configured for Judicial Bangles:

```bash
docker compose -f deploy/compose/docker-compose.mysql.yml up -d
```

- **Host**: `localhost:3306`
- **Database**: `kiro`
- **User**: `root`
- **Password**: `root#123`

To stop:
```bash
docker compose -f deploy/compose/docker-compose.mysql.yml down
```

---

## 2. Local Native Start (macOS Homebrew)

```bash
brew install mysql
brew services start mysql
mysql -u root -e "CREATE DATABASE IF NOT EXISTS kiro;"
```

---

## 3. Configuration (`conf/.env.kiro`)

```bash
STORAGE_BACKEND=mysql

TEST_DEVOPS_DB_HOST=localhost
TEST_DEVOPS_DB_PORT=3306
TEST_DEVOPS_DB_NAME=kiro
TEST_DEVOPS_DB_USER=root
TEST_DEVOPS_DB_PASSWORD=root#123
```

---

## 4. Ingestion Commands

```bash
pip install -r requirements.txt

# Push all datasets for a specific date
python main.py --account <profile> --backend mysql --date 2026-08-22

# Push ONLY prompt logs
python main.py --account <profile> --backend mysql --dataset prompt_logs --date 2026-08-22

# Push existing local files without downloading from S3
python main.py --account <profile> --backend mysql --dataset user_report --load-only
```

---

## 5. CLI Connection

Connect via native client:
```bash
mysql -h 127.0.0.1 -P 3306 -u root -p'root#123' kiro
```

Or connect inside Docker:
```bash
docker exec -it kiro-mysql mysql -u root -p'root#123' kiro
```

---

## 6. Verification Commands

### Check tables and schemas:
```sql
SHOW TABLES;

DESCRIBE kiro_user_report;
DESCRIBE kiro_by_user_analytic;
DESCRIBE kiro_prompt_log;
```

### Check row counts across all datasets:
```sql
SELECT 'user_report' AS dataset, COUNT(*) AS count FROM kiro_user_report
UNION ALL
SELECT 'by_user_analytic', COUNT(*) FROM kiro_by_user_analytic
UNION ALL
SELECT 'prompt_log', COUNT(*) FROM kiro_prompt_log;
```

### Check distinct dates and accounts loaded:
```sql
SELECT aws_account_id, report_date, COUNT(*) AS users_tracked
FROM kiro_user_report
GROUP BY aws_account_id, report_date
ORDER BY report_date DESC;
```

---

## 7. Data Analysis Queries

### Top 10 users by credits consumed:
```sql
SELECT user_id, user_email, subscription_tier, client_type,
       SUM(credits_used) AS total_credits,
       SUM(total_messages) AS total_messages
FROM kiro_user_report
GROUP BY user_id, user_email, subscription_tier, client_type
ORDER BY total_credits DESC
LIMIT 10;
```

### Message volume breakdown by AI model:
```sql
SELECT
    SUM(auto_messages) AS auto,
    SUM(claude_sonnet_4_5_messages) AS sonnet_4_5,
    SUM(claude_opus_4_6_messages) AS opus_4_6,
    SUM(claude_opus_4_8_messages) AS opus_4_8,
    SUM(gpt_5_6_luna_messages) AS gpt_5_6_luna,
    SUM(deepseek_3_2_messages) AS deepseek_3_2,
    SUM(minimax_m2_5_messages) AS minimax_m2_5
FROM kiro_user_report;
```

### Cross-dataset join (Prompt activity correlated with user profile):
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
DELETE FROM kiro_prompt_log WHERE DATE(event_timestamp) = '2026-08-22';
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
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE kiro_user_report;
TRUNCATE TABLE kiro_by_user_analytic;
TRUNCATE TABLE kiro_prompt_log;
SET FOREIGN_KEY_CHECKS = 1;
```

---

## 9. Advanced & Production Deployments

For advanced production deployments, refer to the code samples repository:
👉 [sagarnikam123-blog-youtube-code-samples/mysql/install/](https://github.com/sagarnikam123/sagarnikam123-blog-youtube-code-samples/tree/main/mysql/install)

- **APT/DEB (Debian/Ubuntu)**: `mysql/install/deb/`
- **RPM (RHEL/Rocky/CentOS)**: `mysql/install/rpm/`
- **Homebrew (macOS)**: `mysql/install/brew/`
- **Kubernetes (Helm)**: `mysql/install/helm/` (Bitnami MySQL chart)
- **Kubernetes (Operator)**: `mysql/install/operator/` (Oracle MySQL Operator)
