-- ============================================================================
-- Kiro Usage Analytics — SQL Reference
-- ============================================================================
-- Tables live in: your MySQL database (see conf/.env.kiro)
-- Use these queries directly in Grafana (MySQL datasource) or any SQL client.
--
-- Grafana template variable (add as dashboard variable, type=Query):
--   Name: account_label
--   Query: SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label
--
--   Name: user_email
--   Query: SELECT DISTINCT user_email FROM kiro_user_report WHERE account_label = '$account_label' ORDER BY user_email
--
--   Name: client_type
--   Query: SELECT DISTINCT client_type FROM kiro_user_report ORDER BY client_type
-- ============================================================================


-- ============================================================================
-- SECTION 1: TABLE CREATION (DDL)
-- ============================================================================

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


-- ============================================================================
-- SECTION 2: OVERVIEW & HEALTH CHECK QUERIES
-- ============================================================================

-- 2.1 Data coverage per account
SELECT
    aws_account_id,
    account_label,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT user_email) AS unique_users,
    MIN(report_date) AS earliest_date,
    MAX(report_date) AS latest_date
FROM kiro_user_report
GROUP BY aws_account_id, account_label;

-- 2.2 Daily active users (DAU) — Grafana time series panel
SELECT
    report_date AS time,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 2.3 Daily active users by client type — Grafana stacked bar
SELECT
    report_date AS time,
    client_type,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date, client_type
ORDER BY report_date;


-- ============================================================================
-- SECTION 3: CREDIT CONSUMPTION & BILLING ANALYSIS
-- ============================================================================

-- 3.1 Total daily credits consumed — Grafana time series
SELECT
    report_date AS time,
    SUM(credits_used) AS total_credits,
    SUM(overage_credits_used) AS overage_credits
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 3.2 Credits by subscription tier — Grafana stacked area
SELECT
    report_date AS time,
    subscription_tier,
    SUM(credits_used) AS credits
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date, subscription_tier
ORDER BY report_date;

-- 3.3 Top 10 credit consumers (current month) — Grafana table panel
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

-- 3.4 Users in overage (any day this month) — Grafana table/stat panel
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

-- 3.5 Monthly credit utilization per user (for tier-sizing) — Grafana table
-- Plan credits: PRO=1000, PRO_PLUS=2000, PRO_MAX=5000
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


-- ============================================================================
-- SECTION 4: MODEL USAGE BREAKDOWN
-- ============================================================================

-- 4.1 Messages by model per day — Grafana stacked area
SELECT
    report_date AS time,
    SUM(auto_messages) AS auto_model,
    SUM(claude_opus_4_6_messages) AS claude_opus_4_6,
    SUM(claude_opus_4_8_messages) AS claude_opus_4_8
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 4.2 Model preference per user (current month) — Grafana table
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


-- ============================================================================
-- SECTION 5: FEATURE ADOPTION (by_user_analytic)
-- ============================================================================

-- 5.1 Daily messages sent (chat) — Grafana time series
SELECT
    report_date AS time,
    SUM(chat_messages_sent) AS chat_messages,
    SUM(chat_ai_code_lines) AS ai_code_lines
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 5.2 Inline completions: suggestions vs acceptances — Grafana time series (acceptance rate)
SELECT
    report_date AS time,
    SUM(inline_suggestions_count) AS suggestions,
    SUM(inline_acceptance_count) AS acceptances,
    ROUND(SUM(inline_acceptance_count) / NULLIF(SUM(inline_suggestions_count), 0) * 100, 1) AS acceptance_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 5.3 Code review adoption — Grafana time series
SELECT
    report_date AS time,
    SUM(codereview_succeeded_count) AS reviews_succeeded,
    SUM(codereview_failed_count) AS reviews_failed,
    SUM(codereview_findings_count) AS findings
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 5.4 Test generation usage — Grafana time series
SELECT
    report_date AS time,
    SUM(testgen_event_count) AS test_gen_events,
    SUM(testgen_generated_tests) AS tests_generated,
    SUM(testgen_accepted_tests) AS tests_accepted
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 5.5 Doc generation usage — Grafana time series
SELECT
    report_date AS time,
    SUM(docgen_event_count) AS doc_gen_events,
    SUM(docgen_accepted_file_creations) AS files_created,
    SUM(docgen_accepted_line_additions) AS lines_added
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 5.6 InlineChat usage — Grafana time series
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

-- 5.7 Feature usage heatmap — per user, total events across all features (current month)
-- Grafana table
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


-- ============================================================================
-- SECTION 6: INDIVIDUAL USER ANALYSIS
-- ============================================================================

-- 6.1 Specific user's daily credit usage — Grafana time series (use $user_email variable)
SELECT
    report_date AS time,
    client_type,
    credits_used,
    total_messages
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND user_email = '$user_email'
ORDER BY report_date;

-- 6.2 Specific user's feature activity over time
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

-- 6.3 User's model preferences over time
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


-- ============================================================================
-- SECTION 7: ADOPTION & GROWTH KPIs
-- ============================================================================

-- 7.1 New user adoption per day — Grafana stat/time series
SELECT
    report_date AS time,
    COUNT(*) AS new_users
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND new_user = 1
GROUP BY report_date
ORDER BY report_date;

-- 7.2 Weekly active users (WAU) — Grafana time series
SELECT
    DATE(report_date - INTERVAL WEEKDAY(report_date) DAY) AS week_start,
    COUNT(DISTINCT user_email) AS weekly_active_users
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY week_start
ORDER BY week_start;

-- 7.3 Subscription tier distribution (latest day) — Grafana pie chart
SELECT
    subscription_tier,
    COUNT(DISTINCT user_email) AS user_count
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date = (SELECT MAX(report_date) FROM kiro_user_report WHERE account_label = '$account_label')
GROUP BY subscription_tier;

-- 7.4 Client type distribution (latest day) — Grafana pie chart
SELECT
    client_type,
    COUNT(DISTINCT user_email) AS user_count,
    SUM(total_messages) AS messages
FROM kiro_user_report
WHERE account_label = '$account_label'
  AND report_date = (SELECT MAX(report_date) FROM kiro_user_report WHERE account_label = '$account_label')
GROUP BY client_type;


-- ============================================================================
-- SECTION 8: CROSS-ACCOUNT COMPARISON
-- ============================================================================

-- 8.1 Side-by-side daily active users (both accounts) — Grafana time series with two queries
SELECT
    report_date AS time,
    account_label,
    COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
GROUP BY report_date, account_label
ORDER BY report_date;

-- 8.2 Total credits consumed per account per day
SELECT
    report_date AS time,
    account_label,
    SUM(credits_used) AS total_credits
FROM kiro_user_report
GROUP BY report_date, account_label
ORDER BY report_date;

-- 8.3 Same user, both accounts — identify users active on both profiles
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


-- ============================================================================
-- SECTION 9: EFFICIENCY METRICS
-- ============================================================================

-- 9.1 Credits per message (efficiency) per day — Grafana time series
SELECT
    report_date AS time,
    ROUND(SUM(credits_used) / NULLIF(SUM(total_messages), 0), 4) AS avg_credits_per_message
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 9.2 Inline acceptance rate per user (current month) — Grafana table (spot low adopters)
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

-- 9.3 AI code lines generated per chat message (productivity proxy)
SELECT
    report_date AS time,
    ROUND(SUM(chat_ai_code_lines) / NULLIF(SUM(chat_messages_sent), 0), 1) AS code_lines_per_message
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;


-- ============================================================================
-- SECTION 10: GRAFANA VARIABLE QUERIES
-- ============================================================================
-- Copy these into Grafana dashboard variable definitions (type: Query)

-- Variable: account_label (dropdown for account selection)
-- SELECT DISTINCT account_label FROM kiro_user_report ORDER BY account_label;

-- Variable: user_email (depends on account_label)
-- SELECT DISTINCT user_email FROM kiro_user_report WHERE account_label = '$account_label' ORDER BY user_email;

-- Variable: client_type
-- SELECT DISTINCT client_type FROM kiro_user_report WHERE account_label = '$account_label' ORDER BY client_type;

-- Variable: subscription_tier
-- SELECT DISTINCT subscription_tier FROM kiro_user_report WHERE account_label = '$account_label' ORDER BY subscription_tier;

-- Variable: date_range (auto — just use Grafana's built-in time range picker with report_date column)


-- ============================================================================
-- SECTION 11: CODE GENERATION VOLUME & PRODUCTIVITY
-- ============================================================================

-- 11.1 Total AI code lines generated per day (chat + inline combined) — Grafana time series
SELECT
    report_date AS time,
    SUM(chat_ai_code_lines) AS chat_code_lines,
    SUM(inline_ai_code_lines) AS inline_code_lines,
    SUM(chat_ai_code_lines + inline_ai_code_lines) AS total_ai_code_lines
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 11.2 Top code generators this month — Grafana table
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

-- 11.3 Code fix effectiveness: generated vs accepted lines — Grafana time series
SELECT
    report_date AS time,
    SUM(codefix_generated_lines) AS generated,
    SUM(codefix_accepted_lines) AS accepted,
    ROUND(SUM(codefix_accepted_lines) / NULLIF(SUM(codefix_generated_lines), 0) * 100, 1) AS acceptance_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 11.4 Dev mode (autocomplete-triggered generation) — Grafana time series
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


-- ============================================================================
-- SECTION 12: INLINE COMPLETIONS DEEP DIVE
-- ============================================================================

-- 12.1 Daily inline suggestion volume and acceptance — Grafana time series + bar overlay
SELECT
    report_date AS time,
    SUM(inline_suggestions_count) AS suggestions_shown,
    SUM(inline_acceptance_count) AS accepted_tab,
    SUM(inline_ai_code_lines) AS code_lines_from_inline
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 12.2 Per-user inline adoption (who's using Tab completions) — Grafana table
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


-- ============================================================================
-- SECTION 13: INLINE CHAT EFFECTIVENESS
-- ============================================================================

-- 13.1 InlineChat outcomes over time — Grafana stacked bar (accepted/rejected/dismissed)
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

-- 13.2 InlineChat lines impact — Grafana time series (net lines added)
SELECT
    report_date AS time,
    SUM(inlinechat_accepted_line_additions) AS lines_added,
    SUM(inlinechat_accepted_line_deletions) AS lines_deleted,
    SUM(inlinechat_accepted_line_additions) - SUM(inlinechat_accepted_line_deletions) AS net_lines
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;


-- ============================================================================
-- SECTION 14: CODE REVIEW INSIGHTS
-- ============================================================================

-- 14.1 Code review volume and finding rate — Grafana time series
SELECT
    report_date AS time,
    SUM(codereview_succeeded_count) AS reviews_completed,
    SUM(codereview_findings_count) AS findings,
    ROUND(SUM(codereview_findings_count) / NULLIF(SUM(codereview_succeeded_count), 0), 1) AS avg_findings_per_review
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 14.2 Who's running code reviews — Grafana table
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


-- ============================================================================
-- SECTION 15: TEST GENERATION ANALYSIS
-- ============================================================================

-- 15.1 Test generation over time — Grafana time series
SELECT
    report_date AS time,
    SUM(testgen_event_count) AS events,
    SUM(testgen_generated_tests) AS generated,
    SUM(testgen_accepted_tests) AS accepted,
    ROUND(SUM(testgen_accepted_tests) / NULLIF(SUM(testgen_generated_tests), 0) * 100, 1) AS accept_rate_pct
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 15.2 Test generation lines: generated vs accepted — Grafana time series
SELECT
    report_date AS time,
    SUM(testgen_generated_lines) AS lines_generated,
    SUM(testgen_accepted_lines) AS lines_accepted
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;


-- ============================================================================
-- SECTION 16: DOC GENERATION ANALYSIS
-- ============================================================================

-- 16.1 Doc generation over time — Grafana time series
SELECT
    report_date AS time,
    SUM(docgen_event_count) AS events,
    SUM(docgen_accepted_file_creations + docgen_accepted_file_updates) AS files_modified,
    SUM(docgen_accepted_line_additions + docgen_accepted_line_updates) AS lines_written
FROM kiro_by_user_analytic
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 16.2 Doc generation acceptance vs rejection — Grafana stacked bar
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


-- ============================================================================
-- SECTION 17: TRANSFORMATION (REFACTORING) ANALYSIS
-- ============================================================================

-- 17.1 Transformation activity over time — Grafana time series
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


-- ============================================================================
-- SECTION 18: USER ENGAGEMENT & RETENTION
-- ============================================================================

-- 18.1 User activity frequency (days active this month) — Grafana table
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

-- 18.2 Inactive users (subscribed but no activity in last 7 days) — Grafana table
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

-- 18.3 Daily conversations per user (engagement depth) — Grafana time series
SELECT
    report_date AS time,
    ROUND(SUM(chat_conversations) / NULLIF(COUNT(DISTINCT user_email), 0), 1) AS avg_conversations_per_user,
    MAX(chat_conversations) AS max_conversations_single_user
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;

-- 18.4 Power users (top 10% by messages) vs casual users — Grafana stat
SELECT
    CASE
        WHEN monthly_msgs >= p90 THEN 'Power (top 10%)'
        WHEN monthly_msgs >= p50 THEN 'Regular'
        ELSE 'Light'
    END AS user_segment,
    COUNT(*) AS user_count,
    SUM(monthly_msgs) AS total_messages,
    SUM(monthly_credits) AS total_credits
FROM (
    SELECT
        user_email,
        SUM(total_messages) AS monthly_msgs,
        SUM(credits_used) AS monthly_credits
    FROM kiro_user_report
    WHERE account_label = '$account_label'
      AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
    GROUP BY user_email
) users
CROSS JOIN (
    SELECT
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY monthly_msgs) OVER () AS p90,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY monthly_msgs) OVER () AS p50
    FROM (
        SELECT SUM(total_messages) AS monthly_msgs
        FROM kiro_user_report
        WHERE account_label = '$account_label'
          AND report_date >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
        GROUP BY user_email
    ) t
    LIMIT 1
) pcts
GROUP BY user_segment;


-- ============================================================================
-- SECTION 19: FEATURE ADOPTION FUNNEL
-- ============================================================================

-- 19.1 Feature adoption breadth — how many users tried each feature (current month)
-- Grafana horizontal bar chart
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

-- 19.2 Feature adoption over time (weekly unique users per feature) — Grafana multi-series
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


-- ============================================================================
-- SECTION 20: COST vs VALUE ANALYSIS
-- ============================================================================

-- 20.1 Credits spent vs code generated (are credits turning into code?) — Grafana dual-axis
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

-- 20.2 Cost per AI code line (lower = better efficiency) — Grafana time series
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

-- 20.3 Per-user ROI: credits spent vs code output (current month) — Grafana scatter/table
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


-- ============================================================================
-- SECTION 21: DAILY EXECUTIVE DASHBOARD (single row per day — use for stat panels)
-- ============================================================================

-- 21.1 All KPIs for a single day — Grafana stat panels row
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

-- 21.2 Activity KPIs for same day
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


-- ============================================================================
-- SECTION 22: WEEK-OVER-WEEK TRENDS
-- ============================================================================

-- 22.1 This week vs last week comparison — Grafana table/stat
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

-- 22.2 Daily message trend with 7-day moving average — Grafana time series
SELECT
    report_date AS time,
    SUM(total_messages) AS daily_messages,
    AVG(SUM(total_messages)) OVER (ORDER BY report_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS moving_avg_7d
FROM kiro_user_report
WHERE account_label = '$account_label'
GROUP BY report_date
ORDER BY report_date;


-- ============================================================================
-- SECTION 23: PROMPT LOG METADATA (kiro_prompt_log)
-- ============================================================================
-- Populated by: python main.py --account <profile> --prompt-logs [--store-text]
-- One row per request (requestId). prompt_text/response_text are NULL unless
-- --store-text was used; read raw content from the .json.gz files otherwise.

-- 23.0 Table DDL (also created automatically by init_schema)
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

-- 23.1 Daily prompt request volume — Grafana time series
SELECT
    event_date AS time,
    COUNT(*) AS requests,
    COUNT(DISTINCT user_id_normalized) AS unique_users
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date
ORDER BY event_date;

-- 23.2 Requests by model — Grafana pie / stacked bar
SELECT
    event_date AS time,
    model_id,
    COUNT(*) AS requests
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date, model_id
ORDER BY event_date;

-- 23.3 Peak usage by hour of day — Grafana bar chart (heatmap of activity)
SELECT
    HOUR(event_time) AS hour_of_day,
    COUNT(*) AS requests
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY HOUR(event_time)
ORDER BY hour_of_day;

-- 23.4 Average prompt & response size over time — Grafana time series
SELECT
    event_date AS time,
    ROUND(AVG(prompt_length)) AS avg_prompt_chars,
    ROUND(AVG(user_message_length)) AS avg_user_msg_chars,
    ROUND(AVG(response_length)) AS avg_response_chars
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date
ORDER BY event_date;

-- 23.5 Percent of responses containing code — Grafana time series (gauge/stat)
SELECT
    event_date AS time,
    ROUND(SUM(has_code_in_response) / COUNT(*) * 100, 1) AS pct_with_code
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY event_date
ORDER BY event_date;

-- 23.6 Top users by request count (current month) — Grafana table (joins email)
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

-- 23.7 Chat trigger type breakdown — Grafana pie
SELECT
    chat_trigger_type,
    COUNT(*) AS requests
FROM kiro_prompt_log
WHERE account_label = '$account_label'
GROUP BY chat_trigger_type;

-- 23.8 Full-text search on stored conversations (only if loaded with --store-text)
-- Grafana table — filter by a keyword via a text variable $keyword
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

-- 23.9 Requests vs credits correlation (join prompt volume to credit spend)
-- Grafana dual-axis time series
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


-- ============================================================================
-- SECTION 24: CID-STYLE DASHBOARD BLUEPRINT (AWS Kiro User Activity)
-- ============================================================================
-- Mirrors the AWS Cloud Intelligence Dashboards "Kiro User Activity" layout
-- (5 tabs). One query per panel, MySQL dialect, ready to paste into Grafana.
--
-- CID control -> Grafana equivalent:
--   Lookback period  -> Grafana time range picker (use $__timeFilter(report_date))
--   AWS Account       -> variable $account_label   (All = remove the WHERE line)
--   User              -> variable $user_email
--   Model             -> variable $model            (kiro_prompt_log.model_id)
--   Client Type       -> variable $client_type
--
-- Template variables to define in Grafana (type=Query, "Include All" enabled):
--   account_label : SELECT DISTINCT account_label FROM kiro_user_report ORDER BY 1
--   client_type   : SELECT DISTINCT client_type   FROM kiro_user_report ORDER BY 1
--   user_email    : SELECT DISTINCT user_email     FROM kiro_user_report WHERE account_label IN ($account_label) ORDER BY 1
--   model         : SELECT DISTINCT model_id       FROM kiro_prompt_log   WHERE account_label IN ($account_label) ORDER BY 1
--
-- NOTE on models: the CID "Daily Messages by Model" (Auto/Claude/Deepseek/GLM/…)
-- is driven by kiro_prompt_log.model_id (dynamic), NOT the fixed wide columns in
-- kiro_user_report. Panels below use prompt_log for the model breakdown so any
-- model appears automatically.


-- ── TAB 1: EXECUTIVE SUMMARY ────────────────────────────────────────────────

-- 24.1 Total Kiro Subscriptions (Stat) — distinct subscribed users in range
SELECT COUNT(DISTINCT user_email) AS total_subscriptions
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);

-- 24.2 Total Active Kiro Users (Stat) — users with any message in range
SELECT COUNT(DISTINCT user_email) AS active_users
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND total_messages > 0;

-- 24.3 Total Inactive Kiro Users (Stat) — subscribed but zero messages in range
SELECT COUNT(*) AS inactive_users FROM (
    SELECT user_email, SUM(total_messages) AS msgs
    FROM kiro_user_report
    WHERE $__timeFilter(report_date)
      AND account_label IN ($account_label)
    GROUP BY user_email
    HAVING msgs = 0
) t;

-- 24.4 Total Messages (Stat)
SELECT SUM(total_messages) AS total_messages
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);

-- 24.5 Credits Used (Stat)
SELECT ROUND(SUM(credits_used)) AS credits_used
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);

-- 24.6 Overage Credits (Stat)
SELECT ROUND(SUM(overage_credits_used)) AS overage_credits
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label);

-- 24.7 Daily Active Users by Client Type (Donut) — distinct users per client type
SELECT client_type, COUNT(DISTINCT user_email) AS users
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND total_messages > 0
GROUP BY client_type;

-- 24.8 Daily Active Users by Client Type (Stacked bar, time series)
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


-- ── TAB 2: USER ENGAGEMENT ──────────────────────────────────────────────────

-- 24.9 Top 50 Users by Message Count, split by model (horizontal stacked bar)
-- Messages per user per model from prompt_log (the CID "by Model" split).
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

-- 24.10 Users by Message Count over time (stacked bar by user)
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


-- ── TAB 3: CREDIT & OVERAGE TRACKING ────────────────────────────────────────

-- 24.11 Users at Risk (Stat) — ≥75% of plan credits consumed in range
-- Plan credits: PRO=1000, PRO_PLUS=2000, PRO_MAX=5000 (adjust to your plans)
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

-- 24.12 Users in Overage (Stat)
SELECT COUNT(DISTINCT user_email) AS users_in_overage
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
  AND overage_credits_used > 0;

-- 24.13 Daily Credits Used vs Overage (stacked bar) — CID's main credit chart
SELECT
    report_date AS time,
    SUM(credits_used) AS credits_used,
    SUM(overage_credits_used) AS overage_credits
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY report_date
ORDER BY report_date;

-- 24.14 Per-user plan utilization (table) — supports the "at risk" list
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


-- ── TAB 4: MODEL & CLIENT BREAKDOWN ─────────────────────────────────────────

-- 24.15 Daily Messages by Model (stacked bar) — CID's headline model chart
-- Uses prompt_log.model_id so every model (Auto, Claude*, Deepseek, GLM, Qwen…)
-- shows up automatically without schema changes.
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

-- 24.16 Message share by model (pie) — totals over the range
SELECT model_id, COUNT(*) AS messages
FROM kiro_prompt_log
WHERE $__timeFilter(event_date)
  AND account_label IN ($account_label)
GROUP BY model_id
ORDER BY messages DESC;

-- 24.17 Daily messages by client type (stacked bar) — from report table
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

-- 24.18 Client type share (pie)
SELECT client_type, SUM(total_messages) AS messages
FROM kiro_user_report
WHERE $__timeFilter(report_date)
  AND account_label IN ($account_label)
GROUP BY client_type;


-- ── TAB 5 / EXTRA: PROMPT ACTIVITY (Grafana-native, not in QuickSight CID) ──
-- The CID has no prompt-content tab (QuickSight can't index text). These add
-- value the original couldn't — full-text on the stored conversations.

-- 24.19 Responses containing code, % over time (gauge/time series)
SELECT
    event_date AS time,
    ROUND(SUM(has_code_in_response) / COUNT(*) * 100, 1) AS pct_with_code
FROM kiro_prompt_log
WHERE $__timeFilter(event_date)
  AND account_label IN ($account_label)
GROUP BY event_date
ORDER BY event_date;

-- 24.20 Prompt search (table) — needs --store-text; filter via a text var $keyword
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
