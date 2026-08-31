# Kiro Usage Analytics — MySQL Queries & Dashboard Blueprint

Reference guide and SQL query catalog for building Grafana dashboards from Kiro usage data.

---

## 🧭 Dashboard-Specific Dropdown Matrix

Each Grafana dashboard in the `Kiro AI Analytics/` folder should only include the relevant dropdown variables:

| Dashboard | Lookback Period | AWS Account (`$account_label`) | User Email (`$user_email`) | Subscription Tier (`$subscription_tier`) | Client Type (`$client_type`) | Model (`$model`) | Keyword Search (`$keyword`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **01 - Executive & Leadership Overview** | ✅ Native Time Range | ✅ Multi-select | ❌ | ✅ Multi-select | ❌ | ❌ | ❌ |
| **02 - Developer Productivity & Flow** | ✅ Native Time Range | ✅ Multi-select | ✅ Multi-select (Cascading) | ❌ | ✅ Multi-select | ❌ | ❌ |
| **03 - Team Enablement & Coaching** | ✅ Native Time Range | ✅ Multi-select | ✅ Multi-select | ✅ Multi-select | ❌ | ❌ | ❌ |
| **04 - FinOps & License Optimization** | ✅ Native Time Range | ✅ Multi-select | ✅ Multi-select | ✅ Multi-select | ❌ | ❌ | ❌ |
| **05 - Platform & SRE Reliability** | ✅ Native Time Range | ✅ Multi-select | ❌ | ❌ | ✅ Multi-select | ✅ Multi-select | ✅ Text Box |

---

### 🔧 Global Variable Definitions (Grafana Settings -> Variables)

| Variable | Type | Query / Config | Options |
| :--- | :--- | :--- | :--- |
| **`account_label`** | Query | `SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label` | Multi-select, Include All |
| **`user_email`** | Query | `SELECT DISTINCT user_email FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY user_email` | Multi-select, Include All |
| **`client_type`** | Query | `SELECT DISTINCT client_type FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY client_type` | Multi-select, Include All |
| **`subscription_tier`** | Query | `SELECT DISTINCT subscription_tier FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY subscription_tier` | Multi-select, Include All |
| **`model`** | Query | `SELECT DISTINCT model_id FROM kiro_prompt_log WHERE account_label IN ($account_label) ORDER BY model_id` | Multi-select, Include All |
| **`keyword`** | Text Box | User input filter for full-text search | Default: `""` |

---

## Section 1: TABLE CREATION (DDL)

```sql
CREATE TABLE IF NOT EXISTS kiro_user_report (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    aws_account_id VARCHAR(16) NOT NULL,
    account_label VARCHAR(32) NOT NULL,
    report_date DATE NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    user_email VARCHAR(255),
    client_type VARCHAR(32) NOT NULL,
    chat_conversations INT DEFAULT 0,
    credits_used DOUBLE DEFAULT 0,
    overage_cap DOUBLE DEFAULT 0,
    overage_credits_used DOUBLE DEFAULT 0,
    overage_enabled TINYINT(1) DEFAULT 0,
    profile_id VARCHAR(255),
    subscription_tier VARCHAR(32),
    total_messages INT DEFAULT 0,
    new_user TINYINT(1) DEFAULT 0,
    auto_messages INT DEFAULT 0,
    claude_opus_4_6_messages INT DEFAULT 0,
    claude_opus_4_8_messages INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_report (aws_account_id, report_date, user_id, client_type),
    INDEX idx_account (aws_account_id),
    INDEX idx_date (report_date),
    INDEX idx_email (user_email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

```sql
CREATE TABLE IF NOT EXISTS kiro_by_user_analytic (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    aws_account_id VARCHAR(16) NOT NULL,
    account_label VARCHAR(32) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    report_date DATE NOT NULL,
    chat_ai_code_lines INT DEFAULT 0,
    chat_messages_interacted INT DEFAULT 0,
    chat_messages_sent INT DEFAULT 0,
    codefix_acceptance_count INT DEFAULT 0,
    codefix_accepted_lines INT DEFAULT 0,
    codefix_generated_lines INT DEFAULT 0,
    codefix_generation_count INT DEFAULT 0,
    codereview_failed_count INT DEFAULT 0,
    codereview_findings_count INT DEFAULT 0,
    codereview_succeeded_count INT DEFAULT 0,
    dev_acceptance_count INT DEFAULT 0,
    dev_accepted_lines INT DEFAULT 0,
    dev_generated_lines INT DEFAULT 0,
    dev_generation_count INT DEFAULT 0,
    docgen_accepted_file_updates INT DEFAULT 0,
    docgen_accepted_file_creations INT DEFAULT 0,
    docgen_accepted_line_additions INT DEFAULT 0,
    docgen_accepted_line_updates INT DEFAULT 0,
    docgen_event_count INT DEFAULT 0,
    docgen_rejected_file_creations INT DEFAULT 0,
    docgen_rejected_file_updates INT DEFAULT 0,
    docgen_rejected_line_additions INT DEFAULT 0,
    docgen_rejected_line_updates INT DEFAULT 0,
    inlinechat_acceptance_count INT DEFAULT 0,
    inlinechat_accepted_line_additions INT DEFAULT 0,
    inlinechat_accepted_line_deletions INT DEFAULT 0,
    inlinechat_dismissal_count INT DEFAULT 0,
    inlinechat_dismissed_line_additions INT DEFAULT 0,
    inlinechat_dismissed_line_deletions INT DEFAULT 0,
    inlinechat_rejected_line_additions INT DEFAULT 0,
    inlinechat_rejected_line_deletions INT DEFAULT 0,
    inlinechat_rejection_count INT DEFAULT 0,
    inlinechat_total_count INT DEFAULT 0,
    inline_ai_code_lines INT DEFAULT 0,
    inline_acceptance_count INT DEFAULT 0,
    inline_suggestions_count INT DEFAULT 0,
    testgen_accepted_lines INT DEFAULT 0,
    testgen_accepted_tests INT DEFAULT 0,
    testgen_event_count INT DEFAULT 0,
    testgen_generated_lines INT DEFAULT 0,
    testgen_generated_tests INT DEFAULT 0,
    transformation_event_count INT DEFAULT 0,
    transformation_lines_generated INT DEFAULT 0,
    transformation_lines_ingested INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_by_user_analytic (aws_account_id, user_id, report_date),
    INDEX idx_account (aws_account_id),
    INDEX idx_date (report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## Section 2: OVERVIEW & HEALTH CHECK QUERIES

### 2.1 Data coverage per account

```sql
SELECT
    aws_account_id,
    account_label,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT user_email) AS unique_users,
    MIN(report_date) AS earliest_date,
    MAX(report_date) AS latest_date
FROM kiro_user_report
GROUP BY aws_account_id, account_label;
```

### 2.2 Daily active users (DAU) — Grafana time series panel

```sql
SELECT
    report_date AS time,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 2.3 Daily active users by client type — Grafana stacked bar

```sql
SELECT
    report_date AS time,
    client_type,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date, client_type
ORDER BY report_date;
```

## Section 3: CREDIT CONSUMPTION & BILLING ANALYSIS

### 3.1 Total daily credits consumed — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(credits_used) AS total_credits,
    SUM(overage_credits_used) AS overage_credits
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 3.2 Credits by subscription tier — Grafana stacked area

```sql
SELECT
    report_date AS time,
    subscription_tier,
    SUM(credits_used) AS credits
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date, subscription_tier
ORDER BY report_date;
```

### 3.3 Top 10 credit consumers (current month) — Grafana table panel

```sql
SELECT
    user_email,
    subscription_tier,
    SUM(credits_used) AS total_credits,
    SUM(total_messages) AS total_messages,
    ROUND(SUM(credits_used) / NULLIF(SUM(total_messages), 0), 4) AS credits_per_message
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY user_email, subscription_tier
ORDER BY total_credits DESC
LIMIT 10;
```

### 3.4 Users in overage (any day this month) — Grafana table/stat panel

```sql
SELECT
    user_email,
    subscription_tier,
    SUM(overage_credits_used) AS total_overage,
    COUNT(*) AS days_in_overage
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
  AND overage_credits_used > 0
GROUP BY user_email, subscription_tier
ORDER BY total_overage DESC;
```

### 3.5 Monthly credit utilization per user (for tier-sizing) — Grafana table

> Plan credits: PRO=1000, PRO_PLUS=2000, PRO_MAX=5000

```sql
SELECT
    user_email,
    subscription_tier,
    SUM(credits_used) AS monthly_credits,
    CASE subscription_tier
        WHEN 'PRO' THEN 1000
        WHEN 'PRO_PLUS' THEN 2000
        WHEN 'PRO_MAX' THEN 5000
        ELSE NULL
    END AS plan_credits,
    ROUND(SUM(credits_used) / CASE subscription_tier
        WHEN 'PRO' THEN 1000
        WHEN 'PRO_PLUS' THEN 2000
        WHEN 'PRO_MAX' THEN 5000
        ELSE NULL
    END * 100, 1) AS utilization_pct
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY user_email, subscription_tier
ORDER BY utilization_pct DESC;
```

## Section 4: MODEL USAGE BREAKDOWN

### 4.1 Messages by model per day — Grafana stacked area

```sql
SELECT
    report_date AS time,
    SUM(auto_messages) AS auto_model,
    SUM(claude_opus_4_6_messages) AS claude_opus_4_6,
    SUM(claude_opus_4_8_messages) AS claude_opus_4_8
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 4.2 Model preference per user (current month) — Grafana table

```sql
SELECT
    user_email,
    SUM(auto_messages) AS auto_msgs,
    SUM(claude_opus_4_6_messages) AS opus_4_6,
    SUM(claude_opus_4_8_messages) AS opus_4_8,
    SUM(total_messages) AS total
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY user_email
ORDER BY total DESC;
```

## Section 5: FEATURE ADOPTION (by_user_analytic)

### 5.1 Daily messages sent (chat) — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(chat_messages_sent) AS chat_messages,
    SUM(chat_ai_code_lines) AS ai_code_lines
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 5.2 Inline completions: suggestions vs acceptances — Grafana time series (acceptance rate)

```sql
SELECT
    report_date AS time,
    SUM(inline_suggestions_count) AS suggestions,
    SUM(inline_acceptance_count) AS acceptances,
    ROUND(SUM(inline_acceptance_count) / NULLIF(SUM(inline_suggestions_count), 0) * 100, 1) AS acceptance_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 5.3 Code review adoption — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(codereview_succeeded_count) AS reviews_succeeded,
    SUM(codereview_failed_count) AS reviews_failed,
    SUM(codereview_findings_count) AS findings
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 5.4 Test generation usage — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(testgen_event_count) AS test_gen_events,
    SUM(testgen_generated_tests) AS tests_generated,
    SUM(testgen_accepted_tests) AS tests_accepted
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 5.5 Doc generation usage — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(docgen_event_count) AS doc_gen_events,
    SUM(docgen_accepted_file_creations) AS files_created,
    SUM(docgen_accepted_line_additions) AS lines_added
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 5.6 InlineChat usage — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(inlinechat_total_count) AS inline_chat_events,
    SUM(inlinechat_acceptance_count) AS accepted,
    SUM(inlinechat_rejection_count) AS rejected,
    SUM(inlinechat_dismissal_count) AS dismissed
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 5.7 Feature usage heatmap — per user, total events across all features (current month)

> Grafana table

```sql
SELECT
    a.user_id,
    COALESCE(r.user_email, a.user_id) AS user,
    SUM(a.chat_messages_sent) AS chat,
    SUM(a.inline_suggestions_count) AS inline_suggest,
    SUM(a.inline_acceptance_count) AS inline_accept,
    SUM(a.codefix_generation_count) AS codefix,
    SUM(a.codereview_succeeded_count + a.codereview_failed_count) AS code_review,
    SUM(a.testgen_event_count) AS test_gen,
    SUM(a.docgen_event_count) AS doc_gen,
    SUM(a.inlinechat_total_count) AS inline_chat,
    SUM(a.transformation_event_count) AS transform
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report
    WHERE account_label = '$account_label'
) r ON r.user_id = a.user_id
WHERE a.account_label = '$account_label'
  AND a.report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY a.user_id, r.user_email
ORDER BY chat DESC;
```

## Section 6: INDIVIDUAL USER ANALYSIS

### 6.1 Specific user's daily credit usage — Grafana time series (use $user_email variable)

```sql
SELECT
    report_date AS time,
    client_type,
    credits_used,
    total_messages
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND user_email = '$user_email'
ORDER BY report_date;
```

### 6.2 Specific user's feature activity over time

```sql
SELECT
    a.report_date AS time,
    a.chat_messages_sent,
    a.chat_ai_code_lines,
    a.inline_suggestions_count,
    a.inline_acceptance_count,
    a.codefix_generation_count,
    a.testgen_event_count
FROM kiro_by_user_analytic a
JOIN (
    SELECT DISTINCT user_id
    FROM kiro_user_report
    WHERE user_email = '$user_email'
      AND account_label = '$account_label'
) u ON u.user_id = a.user_id
WHERE a.account_label = '$account_label'
ORDER BY a.report_date;
```

### 6.3 User's model preferences over time

```sql
SELECT
    report_date AS time,
    auto_messages,
    claude_opus_4_6_messages AS opus_4_6,
    claude_opus_4_8_messages AS opus_4_8,
    total_messages
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND user_email = '$user_email'
  AND client_type = 'KIRO_IDE'
ORDER BY report_date;
```

## Section 7: ADOPTION & GROWTH KPIs

### 7.1 New user adoption per day — Grafana stat/time series

```sql
SELECT
    report_date AS time,
    COUNT(*) AS new_users
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND new_user = 1
GROUP BY report_date
ORDER BY report_date;
```

### 7.2 Weekly active users (WAU) — Grafana time series

```sql
SELECT
    DATE(report_date - INTERVAL WEEKDAY(report_date) DAY) AS week_start,
    COUNT(DISTINCT user_email) AS weekly_active_users
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY week_start
ORDER BY week_start;
```

### 7.3 Subscription tier distribution (latest day) — Grafana pie chart

```sql
SELECT
    subscription_tier,
    COUNT(DISTINCT user_email) AS user_count
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date = (SELECT MAX(report_date) FROM kiro_user_report WHERE account_label = '$account_label')
GROUP BY subscription_tier;
```

### 7.4 Client type distribution (latest day) — Grafana pie chart

```sql
SELECT
    client_type,
    COUNT(DISTINCT user_email) AS user_count,
    SUM(total_messages) AS messages
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date = (SELECT MAX(report_date) FROM kiro_user_report WHERE account_label = '$account_label')
GROUP BY client_type;
```

## Section 8: CROSS-ACCOUNT COMPARISON

### 8.1 Side-by-side daily active users (both accounts) — Grafana time series with two queries

```sql
SELECT
    report_date AS time,
    account_label,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
GROUP BY report_date, account_label
ORDER BY report_date;
```

### 8.2 Total credits consumed per account per day

```sql
SELECT
    report_date AS time,
    account_label,
    SUM(credits_used) AS total_credits
FROM kiro_user_report
GROUP BY report_date, account_label
ORDER BY report_date;
```

### 8.3 Same user, both accounts — identify users active on both profiles

```sql
SELECT
    user_email,
    GROUP_CONCAT(DISTINCT account_label) AS accounts,
    GROUP_CONCAT(DISTINCT subscription_tier) AS tiers,
    SUM(credits_used) AS combined_credits
FROM kiro_user_report
WHERE report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY user_email
HAVING COUNT(DISTINCT aws_account_id) > 1
ORDER BY combined_credits DESC;
```

## Section 9: EFFICIENCY METRICS

### 9.1 Credits per message (efficiency) per day — Grafana time series

```sql
SELECT
    report_date AS time,
    ROUND(SUM(credits_used) / NULLIF(SUM(total_messages), 0), 4) AS avg_credits_per_message
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 9.2 Inline acceptance rate per user (current month) — Grafana table (spot low adopters)

```sql
SELECT
    a.user_id,
    COALESCE(r.user_email, a.user_id) AS user,
    SUM(a.inline_suggestions_count) AS suggestions,
    SUM(a.inline_acceptance_count) AS accepted,
    ROUND(SUM(a.inline_acceptance_count) / NULLIF(SUM(a.inline_suggestions_count), 0) * 100, 1) AS accept_rate_pct
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report
    WHERE account_label = '$account_label'
) r ON r.user_id = a.user_id
WHERE a.account_label = '$account_label'
  AND a.report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY a.user_id, r.user_email
HAVING suggestions > 0
ORDER BY accept_rate_pct ASC;
```

### 9.3 AI code lines generated per chat message (productivity proxy)

```sql
SELECT
    report_date AS time,
    ROUND(SUM(chat_ai_code_lines) / NULLIF(SUM(chat_messages_sent), 0), 1) AS code_lines_per_message
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 10: GRAFANA TEMPLATE & DROPDOWN VARIABLES

> Define these variables in Grafana Dashboard Settings -> Variables.

### 10.A GLOBAL & CORE VARIABLE DEFINITIONS (SQL Queries for Dropdowns)

> 1. Variable: account_label (Multi-select, Include All option enabled)
>    Query: SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label;
> 2. Variable: user_email (Multi-select, Include All option enabled, Cascades with account_label)
>    Query: SELECT DISTINCT user_email FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY user_email;
> 3. Variable: client_type (Multi-select, Include All option enabled)
>    Query: SELECT DISTINCT client_type FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY client_type;
> 4. Variable: subscription_tier (Multi-select, Include All option enabled)
>    Query: SELECT DISTINCT subscription_tier FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY subscription_tier;
> 5. Variable: model (Multi-select, Include All option enabled)
>    Query: SELECT DISTINCT model_id FROM kiro_prompt_log WHERE account_label IN ($account_label) ORDER BY model_id;
> 6. Variable: keyword (Text box variable for prompt conversation search)
>    Default: "" (empty string)
> 7. Variable: Time Range ($__timeFilter) — Built-in Grafana native time picker

### 10.B DASHBOARD-SPECIFIC DROPDOWN MATRIX

> 📊 Dashboard 1: Executive & Leadership Overview
>    • Lookback Period   : Native Grafana Time Range (e.g. This Month, Last 30d)
>    • AWS Account       : $account_label (Multi-select, All)
>    • Subscription Tier : $subscription_tier (Multi-select, All)
> 📊 Dashboard 2: Developer Productivity & Flow
>    • Lookback Period   : Native Grafana Time Range
>    • AWS Account       : $account_label (Multi-select, All)
>    • Developer / User  : $user_email (Multi-select, All, Cascades on $account_label)
>    • Client Type       : $client_type (Multi-select, All)
> 📊 Dashboard 3: Team Enablement & Coaching (Manager View)
>    • Lookback Period   : Native Grafana Time Range
>    • AWS Account       : $account_label (Multi-select, All)
>    • Developer / User  : $user_email (Multi-select, All)
>    • Subscription Tier : $subscription_tier (Multi-select, All)
> 📊 Dashboard 4: FinOps & License Optimization
>    • Lookback Period   : Native Grafana Time Range
>    • AWS Account       : $account_label (Multi-select, All)
>    • Subscription Tier : $subscription_tier (Multi-select, All)
>    • Developer / User  : $user_email (Multi-select, All)
> 📊 Dashboard 5: Platform & Infrastructure Reliability (SRE / DevOps View)
>    • Lookback Period   : Native Grafana Time Range
>    • AWS Account       : $account_label (Multi-select, All)
>    • AI Model          : $model (Multi-select, All)
>    • Client Type       : $client_type (Multi-select, All)
>    • Search Keyword    : $keyword (Text Box filter for prompt queries)

## Section 11: CODE GENERATION VOLUME & PRODUCTIVITY

### 11.1 Total AI code lines generated per day (chat + inline combined) — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(chat_ai_code_lines) AS chat_code_lines,
    SUM(inline_ai_code_lines) AS inline_code_lines,
    SUM(chat_ai_code_lines + inline_ai_code_lines) AS total_ai_code_lines
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 11.2 Top code generators this month — Grafana table

```sql
SELECT
    a.user_id,
    COALESCE(r.user_email, a.user_id) AS user,
    SUM(a.chat_ai_code_lines) AS chat_code,
    SUM(a.inline_ai_code_lines) AS inline_code,
    SUM(a.chat_ai_code_lines + a.inline_ai_code_lines) AS total_code_lines,
    SUM(a.chat_messages_sent) AS messages_sent
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report WHERE account_label = '$account_label'
) r ON r.user_id = a.user_id
WHERE a.account_label = '$account_label'
  AND a.report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY a.user_id, r.user_email
ORDER BY total_code_lines DESC
LIMIT 15;
```

### 11.3 Code fix effectiveness: generated vs accepted lines — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(codefix_generated_lines) AS lines_generated,
    SUM(codefix_accepted_lines) AS lines_accepted,
    ROUND(SUM(codefix_accepted_lines) / NULLIF(SUM(codefix_generated_lines), 0) * 100, 1) AS acceptance_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 11.4 Dev mode (autocomplete-triggered generation) — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(dev_generation_count) AS generations,
    SUM(dev_acceptance_count) AS acceptances,
    SUM(dev_generated_lines) AS lines_generated,
    SUM(dev_accepted_lines) AS lines_accepted
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 12: INLINE COMPLETIONS DEEP DIVE

### 12.1 Daily inline suggestion volume and acceptance — Grafana time series + bar overlay

```sql
SELECT
    report_date AS time,
    SUM(inline_suggestions_count) AS suggestions_shown,
    SUM(inline_acceptance_count) AS accepted_tab,
    SUM(inline_ai_code_lines) AS code_lines_from_inline
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 12.2 Per-user inline adoption (who's using Tab completions) — Grafana table

```sql
SELECT
    a.user_id,
    COALESCE(r.user_email, a.user_id) AS user,
    SUM(a.inline_suggestions_count) AS suggestions,
    SUM(a.inline_acceptance_count) AS accepted,
    ROUND(SUM(a.inline_acceptance_count) / NULLIF(SUM(a.inline_suggestions_count), 0) * 100, 1) AS rate_pct,
    SUM(a.inline_ai_code_lines) AS code_lines
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report WHERE account_label = '$account_label'
) r ON r.user_id = a.user_id
WHERE a.account_label = '$account_label'
  AND a.report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
  AND a.inline_suggestions_count > 0
GROUP BY a.user_id, r.user_email
ORDER BY suggestions DESC;
```

## Section 13: INLINE CHAT EFFECTIVENESS

### 13.1 InlineChat outcomes over time — Grafana stacked bar (accepted/rejected/dismissed)

```sql
SELECT
    report_date AS time,
    SUM(inlinechat_acceptance_count) AS accepted,
    SUM(inlinechat_rejection_count) AS rejected,
    SUM(inlinechat_dismissal_count) AS dismissed,
    ROUND(SUM(inlinechat_acceptance_count) / NULLIF(SUM(inlinechat_total_count), 0) * 100, 1) AS acceptance_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 13.2 InlineChat lines impact — Grafana time series (net lines added)

```sql
SELECT
    report_date AS time,
    SUM(inlinechat_accepted_line_additions) AS lines_added,
    SUM(inlinechat_accepted_line_deletions) AS lines_deleted,
    SUM(inlinechat_accepted_line_additions) - SUM(inlinechat_accepted_line_deletions) AS net_lines
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 14: CODE REVIEW INSIGHTS

### 14.1 Code review volume and finding rate — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(codereview_succeeded_count) AS reviews_completed,
    SUM(codereview_findings_count) AS findings,
    ROUND(SUM(codereview_findings_count) / NULLIF(SUM(codereview_succeeded_count), 0), 1) AS avg_findings_per_review
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 14.2 Who's running code reviews — Grafana table

```sql
SELECT
    a.user_id,
    COALESCE(r.user_email, a.user_id) AS user,
    SUM(a.codereview_succeeded_count) AS reviews,
    SUM(a.codereview_findings_count) AS findings,
    SUM(a.codereview_failed_count) AS failed
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report WHERE account_label = '$account_label'
) r ON r.user_id = a.user_id
WHERE a.account_label = '$account_label'
  AND a.report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
  AND (a.codereview_succeeded_count > 0 OR a.codereview_failed_count > 0)
GROUP BY a.user_id, r.user_email
ORDER BY reviews DESC;
```

## Section 15: TEST GENERATION ANALYSIS

### 15.1 Test generation over time — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(testgen_event_count) AS events,
    SUM(testgen_generated_tests) AS tests_generated,
    SUM(testgen_accepted_tests) AS tests_accepted,
    ROUND(SUM(testgen_accepted_tests) / NULLIF(SUM(testgen_generated_tests), 0) * 100, 1) AS accept_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 15.2 Test generation lines: generated vs accepted — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(testgen_generated_lines) AS lines_generated,
    SUM(testgen_accepted_lines) AS lines_accepted
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 16: DOC GENERATION ANALYSIS

### 16.1 Doc generation over time — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(docgen_event_count) AS events,
    SUM(docgen_accepted_file_creations + docgen_accepted_file_updates) AS files_modified,
    SUM(docgen_accepted_line_additions + docgen_accepted_line_updates) AS lines_written
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 16.2 Doc generation acceptance vs rejection — Grafana stacked bar

```sql
SELECT
    report_date AS time,
    SUM(docgen_accepted_file_creations) AS accepted_creates,
    SUM(docgen_rejected_file_creations) AS rejected_creates,
    SUM(docgen_accepted_file_updates) AS accepted_updates,
    SUM(docgen_rejected_file_updates) AS rejected_updates
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 17: TRANSFORMATION (REFACTORING) ANALYSIS

### 17.1 Transformation activity over time — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(transformation_event_count) AS events,
    SUM(transformation_lines_ingested) AS lines_input,
    SUM(transformation_lines_generated) AS lines_output,
    ROUND(SUM(transformation_lines_generated) / NULLIF(SUM(transformation_lines_ingested), 0), 2) AS expansion_ratio
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 18: USER ENGAGEMENT & RETENTION

### 18.1 User activity frequency (days active this month) — Grafana table

```sql
SELECT
    user_email,
    COUNT(DISTINCT report_date) AS days_active,
    SUM(credits_used) AS monthly_credits,
    SUM(total_messages) AS monthly_messages,
    ROUND(SUM(credits_used) / COUNT(DISTINCT report_date), 2) AS avg_credits_per_day
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY user_email
ORDER BY days_active DESC;
```

### 18.2 Inactive users (subscribed but no activity in last 7 days) — Grafana table

```sql
SELECT
    r.user_email,
    r.subscription_tier,
    MAX(r.report_date) AS last_active_date,
    DATEDIFF(CURDATE(), MAX(r.report_date)) AS days_inactive
FROM kiro_user_report r
WHERE r.account_label = '$account_label'
GROUP BY r.user_email, r.subscription_tier
HAVING MAX(r.report_date) < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
ORDER BY days_inactive DESC;
```

### 18.3 Daily conversations per user (engagement depth) — Grafana time series

```sql
SELECT
    report_date AS time,
    ROUND(SUM(chat_conversations) / NULLIF(COUNT(DISTINCT user_email), 0), 1) AS avg_conversations_per_user,
    MAX(chat_conversations) AS max_conversations_single_user
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

### 18.4 Power users (top 10% by messages) vs casual users — Grafana stat

```sql
SELECT
    CASE
        WHEN decile = 10 THEN 'Power (top 10%)'
        WHEN decile >= 5 THEN 'Regular'
        ELSE 'Light'
    END AS user_segment,
    COUNT(*) AS user_count,
    SUM(monthly_msgs) AS total_messages,
    SUM(monthly_credits) AS total_credits
FROM (
    SELECT
        user_email,
        SUM(total_messages) AS monthly_msgs,
        SUM(credits_used) AS monthly_credits,
        NTILE(10) OVER (ORDER BY SUM(total_messages)) AS decile
    FROM kiro_user_report
    WHERE account_label = '$account_label'
      AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
    GROUP BY user_email
) users
GROUP BY user_segment;
```

## Section 19: FEATURE ADOPTION FUNNEL

### 19.1 Feature adoption breadth — how many users tried each feature (current month)

> Grafana horizontal bar chart

```sql
SELECT 'Chat' AS feature,
    COUNT(DISTINCT CASE WHEN chat_messages_sent > 0 THEN user_id END) AS users
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Inline Completions',
    COUNT(DISTINCT CASE WHEN inline_suggestions_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Code Review',
    COUNT(DISTINCT CASE WHEN codereview_succeeded_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Code Fix',
    COUNT(DISTINCT CASE WHEN codefix_generation_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Test Generation',
    COUNT(DISTINCT CASE WHEN testgen_event_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Doc Generation',
    COUNT(DISTINCT CASE WHEN docgen_event_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Inline Chat',
    COUNT(DISTINCT CASE WHEN inlinechat_total_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
UNION ALL
SELECT 'Transformation',
    COUNT(DISTINCT CASE WHEN transformation_event_count > 0 THEN user_id END)
FROM kiro_by_user_analytic
WHERE account_label = '$account_label' AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01');
```

### 19.2 Feature adoption over time (weekly unique users per feature) — Grafana multi-series

```sql
SELECT
    DATE(report_date - INTERVAL WEEKDAY(report_date) DAY) AS week_start,
    COUNT(DISTINCT CASE WHEN chat_messages_sent > 0 THEN user_id END) AS chat_users,
    COUNT(DISTINCT CASE WHEN inline_suggestions_count > 0 THEN user_id END) AS inline_users,
    COUNT(DISTINCT CASE WHEN codereview_succeeded_count > 0 THEN user_id END) AS review_users,
    COUNT(DISTINCT CASE WHEN testgen_event_count > 0 THEN user_id END) AS testgen_users,
    COUNT(DISTINCT CASE WHEN inlinechat_total_count > 0 THEN user_id END) AS inlinechat_users
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY week_start
ORDER BY week_start;
```

## Section 20: COST vs VALUE ANALYSIS

### 20.1 Credits spent vs code generated (are credits turning into code?) — Grafana dual-axis

```sql
SELECT
    r.report_date AS time,
    SUM(r.credits_used) AS credits_used,
    COALESCE(SUM(a.chat_ai_code_lines + a.inline_ai_code_lines), 0) AS ai_code_lines
FROM kiro_user_report r
LEFT JOIN kiro_by_user_analytic a
    ON a.user_id = r.user_id AND a.report_date = r.report_date AND a.aws_account_id = r.aws_account_id
WHERE r.account_label = '$account_label'
GROUP BY r.report_date
ORDER BY r.report_date;
```

### 20.2 Cost per AI code line (lower = better efficiency) — Grafana time series

```sql
SELECT
    r.report_date AS time,
    ROUND(
        SUM(r.credits_used) / NULLIF(SUM(a.chat_ai_code_lines + a.inline_ai_code_lines), 0),
        4
    ) AS credits_per_code_line
FROM kiro_user_report r
LEFT JOIN kiro_by_user_analytic a
    ON a.user_id = r.user_id AND a.report_date = r.report_date AND a.aws_account_id = r.aws_account_id
WHERE r.account_label = '$account_label'
GROUP BY r.report_date
ORDER BY r.report_date;
```

### 20.3 Per-user ROI: credits spent vs code output (current month) — Grafana scatter/table

```sql
SELECT
    COALESCE(r.user_email, a.user_id) AS user,
    SUM(r.credits_used) AS credits,
    SUM(a.chat_ai_code_lines + a.inline_ai_code_lines) AS code_lines,
    ROUND(SUM(r.credits_used) / NULLIF(SUM(a.chat_ai_code_lines + a.inline_ai_code_lines), 0), 4) AS cost_per_line
FROM kiro_user_report r
JOIN kiro_by_user_analytic a
    ON a.user_id = r.user_id AND a.report_date = r.report_date AND a.aws_account_id = r.aws_account_id
WHERE r.account_label = '$account_label'
  AND r.report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY r.user_email, a.user_id
HAVING code_lines > 0
ORDER BY cost_per_line ASC;
```

## Section 21: DAILY EXECUTIVE DASHBOARD (single row per day — use for stat panels)

### 21.1 All KPIs for a single day — Grafana stat panels row

```sql
SELECT
    r.report_date,
    COUNT(DISTINCT r.user_email) AS active_users,
    SUM(r.credits_used) AS total_credits,
    SUM(r.total_messages) AS total_messages,
    SUM(r.chat_conversations) AS total_conversations,
    SUM(r.overage_credits_used) AS overage_credits,
    SUM(r.new_user) AS new_users
FROM kiro_user_report r
WHERE r.account_label = '$account_label'
  AND r.report_date = CURDATE() - INTERVAL 1 DAY
GROUP BY r.report_date;
```

### 21.2 Activity KPIs for same day

```sql
SELECT
    a.report_date,
    COUNT(DISTINCT a.user_id) AS active_devs,
    SUM(a.chat_messages_sent) AS chat_msgs,
    SUM(a.chat_ai_code_lines + a.inline_ai_code_lines) AS ai_code_lines,
    SUM(a.inline_suggestions_count) AS inline_suggestions,
    SUM(a.inline_acceptance_count) AS inline_accepted,
    SUM(a.codereview_succeeded_count) AS code_reviews,
    SUM(a.testgen_event_count) AS test_generations
FROM kiro_by_user_analytic a
WHERE a.account_label = '$account_label'
  AND a.report_date = CURDATE() - INTERVAL 1 DAY
GROUP BY a.report_date;
```

## Section 22: WEEK-OVER-WEEK TRENDS

### 22.1 This week vs last week comparison — Grafana table/stat

```sql
SELECT
    'This week' AS period,
    COUNT(DISTINCT user_email) AS users,
    SUM(credits_used) AS credits,
    SUM(total_messages) AS messages
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
UNION ALL
SELECT
    'Last week',
    COUNT(DISTINCT user_email),
    SUM(credits_used),
    SUM(total_messages)
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date >= DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) + 7 DAY)
  AND report_date < DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY);
```

### 22.2 Daily message trend with 7-day moving average — Grafana time series

```sql
SELECT
    report_date AS time,
    SUM(total_messages) AS daily_messages,
    AVG(SUM(total_messages)) OVER (ORDER BY report_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS moving_avg_7d
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;
```

## Section 23: PROMPT LOG METADATA (kiro_prompt_log)

> Populated by: python main.py --account <profile> --prompt-logs [--store-text]
> One row per request (requestId). prompt_text/response_text are NULL unless
> --store-text was used, read raw content from the .json.gz files otherwise.

### 23.0 Table DDL (also created automatically by init_schema)

```sql
CREATE TABLE IF NOT EXISTS kiro_prompt_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    aws_account_id VARCHAR(16) NOT NULL,
    account_label VARCHAR(32) NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    user_id_normalized VARCHAR(128) NOT NULL,
    event_time DATETIME(3) NOT NULL,
    event_date DATE NOT NULL,
    model_id VARCHAR(64),
    chat_trigger_type VARCHAR(32),
    prompt_length INT DEFAULT 0,
    user_message_length INT DEFAULT 0,
    response_length INT DEFAULT 0,
    has_code_in_response TINYINT(1) DEFAULT 0,
    code_reference_count INT DEFAULT 0,
    prompt_text MEDIUMTEXT NULL,
    response_text MEDIUMTEXT NULL,
    source_file VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_prompt_log (aws_account_id, request_id),
    INDEX idx_account_date (aws_account_id, event_date),
    INDEX idx_user_date (user_id_normalized, event_date),
    INDEX idx_model (model_id),
    INDEX idx_event_time (event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 23.1 Daily prompt request volume — Grafana time series

```sql
SELECT
    event_date AS time,
    COUNT(*) AS requests,
    COUNT(DISTINCT user_id_normalized) AS unique_users
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date
ORDER BY event_date;
```

### 23.2 Requests by model — Grafana pie / stacked bar

```sql
SELECT
    event_date AS time,
    model_id,
    COUNT(*) AS requests
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date, model_id
ORDER BY event_date;
```

### 23.3 Peak usage by hour of day — Grafana bar chart (heatmap of activity)

```sql
SELECT
    HOUR(event_time) AS hour_of_day,
    COUNT(*) AS requests
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY HOUR(event_time)
ORDER BY hour_of_day;
```

### 23.4 Average prompt & response size over time — Grafana time series

```sql
SELECT
    event_date AS time,
    ROUND(AVG(prompt_length)) AS avg_prompt_chars,
    ROUND(AVG(user_message_length)) AS avg_user_msg_chars,
    ROUND(AVG(response_length)) AS avg_response_chars
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date
ORDER BY event_date;
```

### 23.5 Percent of responses containing code — Grafana time series (gauge/stat)

```sql
SELECT
    event_date AS time,
    ROUND(SUM(has_code_in_response) / COUNT(*) * 100, 1) AS pct_with_code
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date
ORDER BY event_date;
```

### 23.6 Top users by request count (current month) — Grafana table (joins email)

```sql
SELECT
    COALESCE(r.user_email, p.user_id_normalized) AS user,
    COUNT(*) AS requests,
    ROUND(AVG(p.prompt_length)) AS avg_prompt_chars,
    ROUND(AVG(p.response_length)) AS avg_response_chars,
    SUM(p.has_code_in_response) AS responses_with_code
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report WHERE account_label = '$account_label'
) r ON r.user_id = p.user_id_normalized
WHERE p.account_label = '$account_label'
  AND p.event_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY user, p.user_id_normalized
ORDER BY requests DESC
LIMIT 20;
```

### 23.7 Chat trigger type breakdown — Grafana pie

```sql
SELECT
    chat_trigger_type,
    COUNT(*) AS requests
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY chat_trigger_type;
```

### 23.8 Full-text search on stored conversations (only if loaded with --store-text)

> Grafana table — filter by a keyword via a text variable $keyword

```sql
SELECT
    event_time AS time,
    COALESCE(r.user_email, p.user_id_normalized) AS user,
    p.model_id,
    LEFT(p.prompt_text, 200) AS prompt_preview,
    LEFT(p.response_text, 300) AS response_preview
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT DISTINCT user_id, user_email
    FROM kiro_user_report WHERE account_label = '$account_label'
) r ON r.user_id = p.user_id_normalized
WHERE p.account_label = '$account_label'
  AND (p.prompt_text LIKE CONCAT('%', '$keyword', '%')
       OR p.response_text LIKE CONCAT('%', '$keyword', '%'))
ORDER BY p.event_time DESC
LIMIT 100;
```

### 23.9 Requests vs credits correlation (join prompt volume to credit spend)

> Grafana dual-axis time series

```sql
SELECT
    p.event_date AS time,
    COUNT(*) AS prompt_requests,
    COALESCE(c.credits, 0) AS credits_used
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT report_date, SUM(credits_used) AS credits
    FROM kiro_user_report
    WHERE account_label = '$account_label'
    GROUP BY report_date
) c ON c.report_date = p.event_date
WHERE p.account_label = '$account_label'
GROUP BY p.event_date, c.credits
ORDER BY p.event_date;
```

## Section 24: CID-STYLE DASHBOARD BLUEPRINT (AWS Kiro User Activity)

> Mirrors the AWS Cloud Intelligence Dashboards "Kiro User Activity" layout
> (5 tabs). One query per panel, MySQL dialect, ready to paste into Grafana.
> CID control -> Grafana equivalent:
>   Lookback period  -> Grafana time range picker (use $__timeFilter(report_date))
>   AWS Account       -> variable $account_label   (All = remove the WHERE line)
>   User              -> variable $user_email
>   Model             -> variable $model            (kiro_prompt_log.model_id)
>   Client Type       -> variable $client_type
> Template variables to define in Grafana (type=Query, "Include All" enabled):
>   account_label : SELECT DISTINCT account_label FROM kiro_user_report ORDER BY 1
>   client_type   : SELECT DISTINCT client_type   FROM kiro_user_report ORDER BY 1
>   user_email    : SELECT DISTINCT user_email     FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY 1
>   model         : SELECT DISTINCT model_id       FROM kiro_prompt_log   WHERE account_label IN ($account_label) ORDER BY 1
> NOTE on models: the CID "Daily Messages by Model" (Auto/Claude/Deepseek/GLM/…)
> is driven by kiro_prompt_log.model_id (dynamic), NOT the fixed wide columns in
> kiro_user_report. Panels below use prompt_log for the model breakdown so any
> model appears automatically.
> ── TAB 1: EXECUTIVE SUMMARY ────────────────────────────────────────────────

### 24.1 Total Kiro Subscriptions (Stat) — distinct subscribed users in range

```sql
SELECT COUNT(DISTINCT user_email) AS total_subscriptions
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);
```

### 24.2 Total Active Kiro Users (Stat) — users with any message in range

```sql
SELECT COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND total_messages > 0;
```

### 24.3 Total Inactive Kiro Users (Stat) — subscribed but zero messages in range

```sql
SELECT COUNT(*) AS inactive_users FROM (
    SELECT user_email, SUM(total_messages) AS msgs
    FROM kiro_user_report
    WHERE $__timeFilter(report_date)
      AND account_label IN ($account_label)
    GROUP BY user_email
    HAVING msgs = 0
) t;
```

### 24.4 Total Messages (Stat)

```sql
SELECT SUM(total_messages) AS total_messages
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);
```

### 24.5 Credits Used (Stat)

```sql
SELECT ROUND(SUM(credits_used)) AS credits_used
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);
```

### 24.6 Overage Credits (Stat)

```sql
SELECT ROUND(SUM(overage_credits_used)) AS overage_credits
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);
```

### 24.7 Daily Active Users by Client Type (Donut) — distinct users per client type

```sql
SELECT client_type, COUNT(DISTINCT user_email) AS users
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND total_messages > 0
GROUP BY client_type;
```

### 24.8 Daily Active Users by Client Type (Stacked bar, time series)

```sql
SELECT
    report_date AS time,
    client_type,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND total_messages > 0
GROUP BY report_date, client_type
ORDER BY report_date;
```

> ── TAB 2: USER ENGAGEMENT ──────────────────────────────────────────────────

### 24.9 Top 50 Users by Message Count, split by model (horizontal stacked bar)

> Messages per user per model from prompt_log (the CID "by Model" split).

```sql
SELECT
    COALESCE(r.user_email, p.user_id_normalized) AS user,
    p.model_id,
    COUNT(*) AS messages
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report
    WHERE account_label IN ($account_label)
) r ON r.user_id = p.user_id_normalized
WHERE $__timeFilter(p.event_date)
  AND p.account_label IN ($account_label)
  AND p.model_id IN ($model)
GROUP BY user, p.model_id
ORDER BY messages DESC
LIMIT 50;
```

### 24.10 Users by Message Count over time (stacked bar by user)

```sql
SELECT
    p.event_date AS time,
    COALESCE(r.user_email, p.user_id_normalized) AS user,
    COUNT(*) AS messages
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report
    WHERE account_label IN ($account_label)
) r ON r.user_id = p.user_id_normalized
WHERE $__timeFilter(p.event_date)
  AND p.account_label IN ($account_label)
GROUP BY p.event_date, user
ORDER BY p.event_date;
```

> ── TAB 3: CREDIT & OVERAGE TRACKING ────────────────────────────────────────

### 24.11 Users at Risk (Stat) — ≥75% of plan credits consumed in range

> Plan credits: PRO=1000, PRO_PLUS=2000, PRO_MAX=5000 (adjust to your plans)

```sql
SELECT COUNT(*) AS users_at_risk FROM (
    SELECT user_email, subscription_tier, SUM(credits_used) AS used,
        CASE subscription_tier WHEN 'PRO' THEN 1000 WHEN 'PRO_PLUS' THEN 2000
             WHEN 'PRO_MAX' THEN 5000 ELSE NULL END AS plan
    FROM kiro_user_report
    WHERE $__timeFilter(report_date)
      AND account_label IN ($account_label)
    GROUP BY user_email, subscription_tier
    HAVING plan IS NOT NULL AND used >= 0.75 * plan
) t;
```

### 24.12 Users in Overage (Stat)

```sql
SELECT COUNT(DISTINCT user_email) AS users_in_overage
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND overage_credits_used > 0;
```

### 24.13 Daily Credits Used vs Overage (stacked bar) — CID's main credit chart

```sql
SELECT
    report_date AS time,
    SUM(credits_used) AS credits_used,
    SUM(overage_credits_used) AS overage_credits
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 24.14 Per-user plan utilization (table) — supports the "at risk" list

```sql
SELECT
    user_email,
    subscription_tier,
    ROUND(SUM(credits_used)) AS credits_used,
    CASE subscription_tier WHEN 'PRO' THEN 1000 WHEN 'PRO_PLUS' THEN 2000
         WHEN 'PRO_MAX' THEN 5000 ELSE NULL END AS plan_credits,
    ROUND(SUM(credits_used) / CASE subscription_tier WHEN 'PRO' THEN 1000
         WHEN 'PRO_PLUS' THEN 2000 WHEN 'PRO_MAX' THEN 5000 ELSE NULL END * 100, 1) AS utilization_pct
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY user_email, subscription_tier
ORDER BY utilization_pct DESC;
```

> ── TAB 4: MODEL & CLIENT BREAKDOWN ─────────────────────────────────────────

### 24.15 Daily Messages by Model (stacked bar) — CID's headline model chart

> Uses prompt_log.model_id so every model (Auto, Claude*, Deepseek, GLM, Qwen…)
> shows up automatically without schema changes.

```sql
SELECT
    event_date AS time,
    model_id,
    COUNT(*) AS messages
FROM kiro_prompt_log
WHERE $__timeFilter(event_date)
  AND account_label IN ($account_label)
  AND model_id IN ($model)
GROUP BY event_date, model_id
ORDER BY event_date;
```

### 24.16 Message share by model (pie) — totals over the range

```sql
SELECT model_id, COUNT(*) AS messages
FROM kiro_prompt_log
WHERE $__timeFilter(event_date)
  AND account_label IN ($account_label)
GROUP BY model_id
ORDER BY messages DESC;
```

### 24.17 Daily messages by client type (stacked bar) — from report table

```sql
SELECT
    report_date AS time,
    client_type,
    SUM(total_messages) AS messages
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND client_type IN ($client_type)
GROUP BY report_date, client_type
ORDER BY report_date;
```

### 24.18 Client type share (pie)

```sql
SELECT client_type, SUM(total_messages) AS messages
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY client_type;
```

> ── TAB 5 / EXTRA: PROMPT ACTIVITY (Grafana-native, not in QuickSight CID) ──
> The CID has no prompt-content tab (QuickSight can't index text). These add
> value the original couldn't — full-text on the stored conversations.

### 24.19 Responses containing code, % over time (gauge/time series)

```sql
SELECT
    event_date AS time,
    ROUND(SUM(has_code_in_response) / COUNT(*) * 100, 1) AS pct_with_code
FROM kiro_prompt_log
WHERE $__timeFilter(event_date)
  AND account_label IN ($account_label)
GROUP BY event_date
ORDER BY event_date;
```

### 24.20 Prompt search (table) — needs --store-text, filter via a text var $keyword

```sql
SELECT
    event_time AS time,
    COALESCE(r.user_email, p.user_id_normalized) AS user,
    p.model_id,
    LEFT(p.prompt_text, 200) AS prompt_preview,
    LEFT(p.response_text, 300) AS response_preview
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report
    WHERE account_label IN ($account_label)
) r ON r.user_id = p.user_id_normalized
WHERE $__timeFilter(p.event_time)
  AND p.account_label IN ($account_label)
  AND (p.prompt_text LIKE CONCAT('%', '$keyword', '%')
       OR p.response_text LIKE CONCAT('%', '$keyword', '%'))
ORDER BY p.event_time DESC
LIMIT 100;
```

## Section 25: DEVELOPER & ENGINEERING PRODUCTIVITY (DEVELOPER VIEW)

> Focus: Individual and team coding flow, inline suggestion acceptance speed,
> AI code output vs manual typing, test/doc coverage acceleration.

### 25.1 Developer AI Velocity: Lines Generated vs Lines Accepted (Time Series)

> Panel: Grafana Time Series with Dual Bar / Line Overlay

```sql
SELECT
    report_date AS time,
    SUM(inline_ai_code_lines + chat_ai_code_lines + dev_accepted_lines + codefix_accepted_lines) AS total_accepted_ai_lines,
    SUM(dev_generated_lines + codefix_generated_lines) AS total_generated_candidate_lines,
    ROUND(SUM(inline_ai_code_lines + chat_ai_code_lines + dev_accepted_lines + codefix_accepted_lines) /
          NULLIF(SUM(dev_generated_lines + codefix_generated_lines + inline_ai_code_lines + chat_ai_code_lines), 0) * 100, 1) AS overall_acceptance_yield_pct
FROM kiro_by_user_analytic
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 25.2 Inline Completion Tab Flow: Suggestions vs Keystroke Acceptances (Time Series + Gauge)

> Panel: Grafana Time Series (Acceptance Rate) + Stat Gauge (Avg Yield)

```sql
SELECT
    report_date AS time,
    SUM(inline_suggestions_count) AS tab_suggestions_offered,
    SUM(inline_acceptance_count) AS tab_suggestions_accepted,
    SUM(inline_ai_code_lines) AS code_lines_tabbed_in,
    ROUND(SUM(inline_acceptance_count) / NULLIF(SUM(inline_suggestions_count), 0) * 100, 1) AS tab_acceptance_rate_pct
FROM kiro_by_user_analytic
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 25.3 Developer Feature Multi-Tooling Activity Breakdown (Stacked Bar)

> Panel: Grafana Stacked Bar showing how developers mix AI modalities

```sql
SELECT
    report_date AS time,
    SUM(chat_messages_sent) AS chat_prompts,
    SUM(inline_acceptance_count) AS inline_completions,
    SUM(codefix_generation_count) AS codefixes,
    SUM(codereview_succeeded_count) AS code_reviews,
    SUM(testgen_event_count) AS unit_tests_gen,
    SUM(docgen_event_count) AS docstrings_gen,
    SUM(transformation_event_count) AS refactors
FROM kiro_by_user_analytic
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 25.4 Inline Chat Yield: Net Code Delivered (Lines Added vs Lines Deleted)

> Panel: Grafana Bar Chart / Diverging Bar

```sql
SELECT
    report_date AS time,
    SUM(inlinechat_accepted_line_additions) AS additions_accepted,
    SUM(inlinechat_accepted_line_deletions) AS deletions_accepted,
    SUM(inlinechat_accepted_line_additions) - SUM(inlinechat_accepted_line_deletions) AS net_code_delta,
    SUM(inlinechat_total_count) AS inlinechat_prompts
FROM kiro_by_user_analytic
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 25.5 Test Suite & Documentation Generation Velocity (Time Series)

> Panel: Grafana Multi-axis Time Series

```sql
SELECT
    report_date AS time,
    SUM(testgen_generated_tests) AS tests_synthesized,
    SUM(testgen_accepted_tests) AS tests_committed,
    SUM(docgen_accepted_file_creations + docgen_accepted_file_updates) AS doc_files_updated,
    SUM(docgen_accepted_line_additions + docgen_accepted_line_updates) AS doc_lines_written
FROM kiro_by_user_analytic
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

## Section 26: EXECUTIVE & LEADERSHIP DASHBOARD (STAKEHOLDER / VP / CTO VIEW)

> Focus: Organizational adoption rate, license efficiency, ROI / Dev Hours saved,
> strategic growth across business units/accounts.

### 26.1 AI License Adoption & Seat Utilization Funnel (Stat Panels & Bar Gauge)

> Panel: Grafana Stat / Bar Gauge

```sql
SELECT
    COUNT(DISTINCT r.user_email) AS total_subscribed_seats,
    COUNT(DISTINCT CASE WHEN r.total_messages > 0 THEN r.user_email END) AS active_seats,
    COUNT(DISTINCT CASE WHEN r.total_messages = 0 THEN r.user_email END) AS dormant_seats,
    ROUND(COUNT(DISTINCT CASE WHEN r.total_messages > 0 THEN r.user_email END) / NULLIF(COUNT(DISTINCT r.user_email), 0) * 100, 1) AS seat_utilization_rate_pct,
    COUNT(DISTINCT CASE WHEN r.new_user = 1 THEN r.user_email END) AS newly_onboarded_devs
FROM kiro_user_report r
WHERE $__timeFilter(r.report_date)
  AND r.account_label IN ($account_label);
```

### 26.2 Estimated Engineering Hours Saved (ROI Proxy Metric)

> Assumptions:
>   - 1 accepted inline completion saves ~30 seconds (0.0083 hrs)
>   - 10 lines of generated/accepted AI code save ~10 minutes (0.166 hrs)
>   - 1 test synthesized & accepted saves ~15 minutes (0.25 hrs)
>   - 1 code review conducted saves ~20 minutes (0.333 hrs)
> Panel: Grafana Stat Card with Trend

```sql
SELECT
    ROUND(
        (SUM(a.inline_acceptance_count) * 0.0083) +
        ((SUM(a.chat_ai_code_lines + a.inline_ai_code_lines + a.dev_accepted_lines + a.codefix_accepted_lines) / 10.0) * 0.166) +
        (SUM(a.testgen_accepted_tests) * 0.25) +
        (SUM(a.codereview_succeeded_count) * 0.333)
    , 1) AS estimated_hours_saved,
    ROUND(
        ((SUM(a.inline_acceptance_count) * 0.0083) +
         ((SUM(a.chat_ai_code_lines + a.inline_ai_code_lines + a.dev_accepted_lines + a.codefix_accepted_lines) / 10.0) * 0.166) +
         (SUM(a.testgen_accepted_tests) * 0.25) +
         (SUM(a.codereview_succeeded_count) * 0.333)) / NULLIF(COUNT(DISTINCT a.user_id), 0)
    , 1) AS avg_hours_saved_per_dev
FROM kiro_by_user_analytic a
WHERE $__timeFilter(a.report_date)
  AND a.account_label IN ($account_label);
```

### 26.3 Month-over-Month (MoM) Organizational Growth (Table / Stat)

> Panel: Grafana Table

```sql
SELECT
    DATE_FORMAT(report_date, '%Y-%m') AS month,
    COUNT(DISTINCT user_email) AS total_users,
    SUM(total_messages) AS monthly_messages,
    ROUND(SUM(credits_used)) AS total_credits_spent,
    ROUND(SUM(overage_credits_used)) AS total_overage_credits
FROM kiro_user_report
WHERE account_label IN ($account_label)
GROUP BY DATE_FORMAT(report_date, '%Y-%m')
ORDER BY month DESC;
```

### 26.4 Multi-Account Portfolio Spend & Capacity (Pie / Donut + Table)

> Panel: Grafana Pie Chart / Table

```sql
SELECT
    account_label,
    aws_account_id,
    COUNT(DISTINCT user_email) AS provisioned_seats,
    ROUND(SUM(credits_used)) AS total_credits_consumed,
    ROUND(SUM(overage_credits_used)) AS total_overage_credits,
    ROUND(SUM(overage_credits_used) / NULLIF(SUM(credits_used), 0) * 100, 1) AS overage_pct_of_total
FROM kiro_user_report
WHERE $__timeFilter(report_date)
GROUP BY account_label, aws_account_id
ORDER BY total_credits_consumed DESC;
```

## Section 27: ENGINEERING MANAGEMENT & TEAM LEAD DASHBOARD (MANAGER VIEW)

> Focus: Team enablement, adoption depth, developer coaching opportunities,
> code review hygiene, and sprint-level engagement consistency.

### 27.1 Team Feature Maturity & Adoption Matrix (Table with Cell Highlights)

> Identifies if devs are only using Chat vs full toolkit (Completions, Tests, Reviews)
> Panel: Grafana Table

```sql
SELECT
    COALESCE(r.user_email, a.user_id) AS developer,
    SUM(a.chat_messages_sent) AS chat_prompts,
    SUM(a.inline_acceptance_count) AS inline_accepted,
    SUM(a.testgen_accepted_tests) AS tests_created,
    SUM(a.codereview_succeeded_count) AS reviews_run,
    SUM(a.codefix_acceptance_count) AS codefixes_accepted,
    SUM(a.docgen_event_count) AS docgens_run,
    CASE
        WHEN SUM(a.testgen_accepted_tests) > 0 AND SUM(a.codereview_succeeded_count) > 0 AND SUM(a.inline_acceptance_count) > 50 THEN 'Champion (Full Suite)'
        WHEN SUM(a.inline_acceptance_count) > 20 THEN 'Adopter (Chat + Inline)'
        WHEN SUM(a.chat_messages_sent) > 0 THEN 'Novice (Chat Only)'
        ELSE 'Inactive'
    END AS maturity_tier
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report WHERE account_label IN ($account_label)
) r ON r.user_id = a.user_id
WHERE $__timeFilter(a.report_date)
  AND a.account_label IN ($account_label)
GROUP BY developer
ORDER BY chat_prompts DESC;
```

### 27.2 Enablement & Coaching Detector (Low Acceptance / High Rejection)

> Flags engineers who may struggle with prompt engineering or context window sizing
> Panel: Grafana Table

```sql
SELECT
    COALESCE(r.user_email, a.user_id) AS developer,
    SUM(a.inline_suggestions_count) AS inline_suggestions,
    SUM(a.inline_acceptance_count) AS inline_accepted,
    ROUND(SUM(a.inline_acceptance_count) / NULLIF(SUM(a.inline_suggestions_count), 0) * 100, 1) AS inline_accept_rate_pct,
    SUM(a.inlinechat_total_count) AS inlinechat_total,
    ROUND(SUM(a.inlinechat_rejection_count + a.inlinechat_dismissal_count) / NULLIF(SUM(a.inlinechat_total_count), 0) * 100, 1) AS inlinechat_reject_rate_pct,
    CASE
        WHEN SUM(a.inline_suggestions_count) >= 50 AND (SUM(a.inline_acceptance_count) / SUM(a.inline_suggestions_count)) < 0.05
            THEN 'Needs Prompt / Context Training (Low Inline Yield)'
        WHEN SUM(a.inlinechat_total_count) >= 10 AND ((SUM(a.inlinechat_rejection_count) + SUM(a.inlinechat_dismissal_count)) / SUM(a.inlinechat_total_count)) > 0.70
            THEN 'High Chat Rejections (Review Prompting Style)'
        ELSE 'Healthy Flow'
    END AS coaching_signal
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report WHERE account_label IN ($account_label)
) r ON r.user_id = a.user_id
WHERE $__timeFilter(a.report_date)
  AND a.account_label IN ($account_label)
GROUP BY developer
HAVING inline_suggestions >= 20 OR inlinechat_total >= 5
ORDER BY inline_accept_rate_pct ASC;
```

### 27.3 Team Code Review Quality & Finding Yield (Stacked Bar / Table)

> Panel: Grafana Stacked Bar (Reviews Completed vs Failed, Findings)

```sql
SELECT
    COALESCE(r.user_email, a.user_id) AS developer,
    SUM(a.codereview_succeeded_count) AS reviews_succeeded,
    SUM(a.codereview_failed_count) AS reviews_failed,
    SUM(a.codereview_findings_count) AS total_findings_flagged,
    ROUND(SUM(a.codereview_findings_count) / NULLIF(SUM(a.codereview_succeeded_count), 0), 1) AS avg_findings_per_review
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report WHERE account_label IN ($account_label)
) r ON r.user_id = a.user_id
WHERE $__timeFilter(a.report_date)
  AND a.account_label IN ($account_label)
GROUP BY developer
HAVING reviews_succeeded > 0 OR reviews_failed > 0
ORDER BY reviews_succeeded DESC;
```

### 27.4 Developer Active Days & Sprint Cadence Consistency (Heatmap / Table)

> Panel: Grafana Heatmap or Table

```sql
SELECT
    COALESCE(r.user_email, a.user_id) AS developer,
    COUNT(DISTINCT a.report_date) AS active_days_in_period,
    ROUND(SUM(a.chat_messages_sent) / COUNT(DISTINCT a.report_date), 1) AS avg_prompts_per_active_day,
    ROUND(SUM(a.chat_ai_code_lines + a.inline_ai_code_lines) / COUNT(DISTINCT a.report_date), 1) AS avg_ai_code_lines_per_day
FROM kiro_by_user_analytic a
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report WHERE account_label IN ($account_label)
) r ON r.user_id = a.user_id
WHERE $__timeFilter(a.report_date)
  AND a.account_label IN ($account_label)
GROUP BY developer
ORDER BY active_days_in_period DESC;
```

## Section 28: FINOPS & COST OPTIMIZATION DASHBOARD (FINOPS VIEW)

> Focus: Overage projections, shelfware reduction, plan tier right-sizing,
> unit cost per line of code, and budget anomaly detection.

### 28.1 Month-End Overage Spend Run-Rate & Projections (Stat Panel)

> Projects expected total credits by month end based on current day of month
> Panel: Grafana Stat Panel (Current MTD vs Projected EOM)

```sql
SELECT
    ROUND(SUM(credits_used)) AS mtd_credits_consumed,
    ROUND(SUM(overage_credits_used)) AS mtd_overage_credits_consumed,
    ROUND((SUM(credits_used) / DAY(MAX(report_date))) * DAY(LAST_DAY(MAX(report_date)))) AS projected_eom_total_credits,
    ROUND((SUM(overage_credits_used) / DAY(MAX(report_date))) * DAY(LAST_DAY(MAX(report_date)))) AS projected_eom_overage_credits
FROM kiro_user_report
WHERE account_label IN ($account_label)
  AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01');
```

### 28.2 Shelfware & License Waste: Inactive / Underutilized Seats (Table)

> Highlights allocated seats that have spent zero or near-zero credits in the last 14/30 days
> Panel: Grafana Table

```sql
SELECT
    user_email,
    subscription_tier,
    MAX(report_date) AS last_active_date,
    DATEDIFF(CURDATE(), MAX(report_date)) AS days_since_last_activity,
    ROUND(SUM(credits_used), 2) AS total_credits_used_mtd,
    CASE
        WHEN DATEDIFF(CURDATE(), MAX(report_date)) >= 30 THEN 'Reclaim License (Dormant > 30d)'
        WHEN DATEDIFF(CURDATE(), MAX(report_date)) >= 14 THEN 'At Risk (Inactive > 14d)'
        ELSE 'Light Usage'
    END AS finops_action
FROM kiro_user_report
WHERE account_label IN ($account_label)
GROUP BY user_email, subscription_tier
HAVING days_since_last_activity >= 14 OR total_credits_used_mtd < 50
ORDER BY days_since_last_activity DESC;
```

### 28.3 Unit Economics: Cost (Credits) Per 1,000 Accepted AI Code Lines (Time Series)

> Panel: Grafana Time Series (Target is decreasing trend)

```sql
SELECT
    r.report_date AS time,
    ROUND(
        SUM(r.credits_used) /
        NULLIF(SUM(a.inline_ai_code_lines + a.chat_ai_code_lines + a.dev_accepted_lines + a.codefix_accepted_lines), 0) * 1000
    , 2) AS credits_per_1k_accepted_lines
FROM kiro_user_report r
JOIN kiro_by_user_analytic a
  ON a.user_id = r.user_id AND a.report_date = r.report_date AND a.aws_account_id = r.aws_account_id
WHERE $__timeFilter(r.report_date)
  AND r.account_label IN ($account_label)
GROUP BY r.report_date
ORDER BY r.report_date;
```

### 28.4 Tier Right-Sizing Advisor: Upgrade vs Downgrade Recommendations (Table)

> Evaluates tier threshold capacity vs actual consumption and overage exposure
> Panel: Grafana Table with Color Rules

```sql
SELECT
    user_email,
    subscription_tier,
    ROUND(SUM(credits_used), 1) AS credits_consumed,
    ROUND(SUM(overage_credits_used), 1) AS overage_credits,
    CASE subscription_tier
        WHEN 'PRO' THEN 1000
        WHEN 'PRO_PLUS' THEN 2000
        WHEN 'PRO_MAX' THEN 5000
        ELSE 1000
    END AS plan_quota,
    ROUND(SUM(credits_used) / CASE subscription_tier WHEN 'PRO' THEN 1000 WHEN 'PRO_PLUS' THEN 2000 WHEN 'PRO_MAX' THEN 5000 ELSE 1000 END * 100, 1) AS quota_utilization_pct,
    CASE
        WHEN SUM(overage_credits_used) > 500 THEN 'UPGRADE TIER (Chronic High Overage)'
        WHEN SUM(overage_credits_used) > 0 THEN 'MONITOR (Occasional Overage)'
        WHEN SUM(credits_used) / CASE subscription_tier WHEN 'PRO' THEN 1000 WHEN 'PRO_PLUS' THEN 2000 WHEN 'PRO_MAX' THEN 5000 ELSE 1000 END < 0.20 THEN 'DOWNGRADE / UNASSIGN (Under 20% Utilization)'
        ELSE 'OPTIMAL (Right-Sized)'
    END AS tier_rightsizing_recommendation
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY user_email, subscription_tier
ORDER BY overage_credits DESC, quota_utilization_pct DESC;
```

## Section 29: PLATFORM & DEVOPS DASHBOARD (PLATFORM / TOOLING VIEW)

> Focus: Tooling client modalities (CLI vs IDE vs Plugins), CI/CD agentic script
> usage, context retrieval effectiveness, prompt payload token sizing.

### 29.1 Client Workflow Modality Evolution: CLI vs IDE vs Plugin (Time Series)

> Identifies shifts between interactive in-editor usage and automated terminal/CLI scripting
> Panel: Grafana Stacked Area Chart

```sql
SELECT
    report_date AS time,
    SUM(CASE WHEN client_type = 'KIRO_IDE' THEN total_messages ELSE 0 END) AS ide_messages,
    SUM(CASE WHEN client_type = 'KIRO_CLI' THEN total_messages ELSE 0 END) AS cli_messages,
    SUM(CASE WHEN client_type = 'PLUGIN' THEN total_messages ELSE 0 END) AS plugin_messages,
    ROUND(SUM(CASE WHEN client_type = 'KIRO_CLI' THEN total_messages ELSE 0 END) / NULLIF(SUM(total_messages), 0) * 100, 1) AS cli_automation_share_pct
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 29.2 Prompt Context Retrieval & Code Reference Utilization (Bar / Gauge)

> Tracks how often developers provide codebase context / file attachments
> Panel: Grafana Bar Gauge / Stat

```sql
SELECT
    p.model_id,
    COUNT(*) AS total_prompts,
    SUM(CASE WHEN p.code_reference_count > 0 THEN 1 ELSE 0 END) AS prompts_with_code_references,
    ROUND(SUM(CASE WHEN p.code_reference_count > 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS context_enrichment_pct,
    ROUND(AVG(p.prompt_length)) AS avg_prompt_characters,
    ROUND(AVG(p.response_length)) AS avg_response_characters
FROM kiro_prompt_log p
WHERE $__timeFilter(p.event_date)
  AND p.account_label IN ($account_label)
GROUP BY p.model_id
ORDER BY total_prompts DESC;
```

### 29.3 Prompt Payload vs Response Density Ratio (Scatter Plot / Time Series)

> Evaluates token density: small prompt triggering large code generation vs verbose prompt
> Panel: Grafana Time Series

```sql
SELECT
    p.event_date AS time,
    ROUND(AVG(p.prompt_length)) AS avg_input_chars,
    ROUND(AVG(p.response_length)) AS avg_output_chars,
    ROUND(AVG(p.response_length) / NULLIF(AVG(p.prompt_length), 0), 2) AS expansion_density_ratio
FROM kiro_prompt_log p
WHERE $__timeFilter(p.event_date)
  AND p.account_label IN ($account_label)
GROUP BY p.event_date
ORDER BY p.event_date;
```

## Section 30: INFRASTRUCTURE & RELIABILITY DASHBOARD (INFRA / SRE VIEW)

> Focus: Peak traffic shaping, hourly heatmaps, model routing reliability,
> code review/transformation error rates, and payload anomaly detection.

### 30.1 Hourly Traffic Load Heatmap (Capacity Planning & Peak Hours)

> Panel: Grafana Heatmap (X-axis: Hour of Day 0-23, Y-axis: Day of Week)

```sql
SELECT
    HOUR(event_time) AS hour_of_day,
    DAYNAME(event_date) AS day_of_week,
    COUNT(*) AS request_count
FROM kiro_prompt_log
WHERE $__timeFilter(event_date)
  AND account_label IN ($account_label)
GROUP BY hour_of_day, day_of_week
ORDER BY hour_of_day, FIELD(day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday');
```

### 30.2 Dynamic Model Routing & Fallback Share (Stacked Bar Time Series)

> Evaluates Claude 3.5 Sonnet vs Claude Opus 4.6 vs Opus 4.8 vs DeepSeek vs Auto routing
> Panel: Grafana Stacked Bar Chart

```sql
SELECT
    p.event_date AS time,
    p.model_id,
    COUNT(*) AS request_count,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY p.event_date) * 100, 1) AS model_traffic_share_pct
FROM kiro_prompt_log p
WHERE $__timeFilter(p.event_date)
  AND p.account_label IN ($account_label)
GROUP BY p.event_date, p.model_id
ORDER BY p.event_date;
```

### 30.3 Quality & Reliability Anomaly Tracking: Code Review Failures (Time Series)

> Alerts if backend reviews or AST transformations fail to complete
> Panel: Grafana Time Series with Alert Thresholds

```sql
SELECT
    report_date AS time,
    SUM(codereview_succeeded_count) AS reviews_succeeded,
    SUM(codereview_failed_count) AS reviews_failed,
    ROUND(SUM(codereview_failed_count) / NULLIF(SUM(codereview_succeeded_count + codereview_failed_count), 0) * 100, 2) AS codereview_failure_rate_pct,
    SUM(transformation_event_count) AS transformations_attempted
FROM kiro_by_user_analytic
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;
```

### 30.4 Context Payload Heavy Hitters & Outliers (Table)

> Spots outlier requests with massive context payloads that consume excessive credits or cause latency
> Panel: Grafana Table

```sql
SELECT
    p.event_time AS timestamp,
    COALESCE(r.user_email, p.user_id_normalized) AS user,
    p.model_id,
    p.prompt_length AS prompt_char_size,
    p.response_length AS response_char_size,
    p.code_reference_count,
    p.has_code_in_response,
    p.source_file
FROM kiro_prompt_log p
LEFT JOIN (
    SELECT DISTINCT user_id, user_email FROM kiro_user_report WHERE account_label IN ($account_label)
) r ON r.user_id = p.user_id_normalized
WHERE $__timeFilter(p.event_time)
  AND p.account_label IN ($account_label)
ORDER BY p.prompt_length DESC
LIMIT 50;
```

