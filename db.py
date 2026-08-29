"""MySQL schema creation and upsert logic for Kiro usage data."""

import logging

import pymysql

from conf.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)


def get_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )


# -- Schema DDL --

CREATE_USER_REPORT = """
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
    INDEX idx_account (aws_account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_BY_USER_ANALYTIC = """
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
    INDEX idx_account (aws_account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def init_schema():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_USER_REPORT)
            cur.execute(CREATE_BY_USER_ANALYTIC)
        logger.info("Schema initialized")
    finally:
        conn.close()


# -- Upsert logic --

UPSERT_USER_REPORT = """
INSERT INTO kiro_user_report (
    aws_account_id, account_label, report_date, user_id, user_email, client_type, chat_conversations,
    credits_used, overage_cap, overage_credits_used, overage_enabled,
    profile_id, subscription_tier, total_messages, new_user,
    auto_messages, claude_opus_4_6_messages, claude_opus_4_8_messages
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
) ON DUPLICATE KEY UPDATE
    account_label = VALUES(account_label),
    user_email = VALUES(user_email),
    chat_conversations = VALUES(chat_conversations),
    credits_used = VALUES(credits_used),
    overage_cap = VALUES(overage_cap),
    overage_credits_used = VALUES(overage_credits_used),
    overage_enabled = VALUES(overage_enabled),
    profile_id = VALUES(profile_id),
    subscription_tier = VALUES(subscription_tier),
    total_messages = VALUES(total_messages),
    new_user = VALUES(new_user),
    auto_messages = VALUES(auto_messages),
    claude_opus_4_6_messages = VALUES(claude_opus_4_6_messages),
    claude_opus_4_8_messages = VALUES(claude_opus_4_8_messages);
"""

UPSERT_BY_USER_ANALYTIC = """
INSERT INTO kiro_by_user_analytic (
    aws_account_id, account_label, user_id, report_date, chat_ai_code_lines, chat_messages_interacted,
    chat_messages_sent, codefix_acceptance_count, codefix_accepted_lines,
    codefix_generated_lines, codefix_generation_count, codereview_failed_count,
    codereview_findings_count, codereview_succeeded_count, dev_acceptance_count,
    dev_accepted_lines, dev_generated_lines, dev_generation_count,
    docgen_accepted_file_updates, docgen_accepted_file_creations,
    docgen_accepted_line_additions, docgen_accepted_line_updates, docgen_event_count,
    docgen_rejected_file_creations, docgen_rejected_file_updates,
    docgen_rejected_line_additions, docgen_rejected_line_updates,
    inlinechat_acceptance_count, inlinechat_accepted_line_additions,
    inlinechat_accepted_line_deletions, inlinechat_dismissal_count,
    inlinechat_dismissed_line_additions, inlinechat_dismissed_line_deletions,
    inlinechat_rejected_line_additions, inlinechat_rejected_line_deletions,
    inlinechat_rejection_count, inlinechat_total_count, inline_ai_code_lines,
    inline_acceptance_count, inline_suggestions_count, testgen_accepted_lines,
    testgen_accepted_tests, testgen_event_count, testgen_generated_lines,
    testgen_generated_tests, transformation_event_count,
    transformation_lines_generated, transformation_lines_ingested
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
) ON DUPLICATE KEY UPDATE
    account_label = VALUES(account_label),
    chat_ai_code_lines = VALUES(chat_ai_code_lines),
    chat_messages_interacted = VALUES(chat_messages_interacted),
    chat_messages_sent = VALUES(chat_messages_sent),
    codefix_acceptance_count = VALUES(codefix_acceptance_count),
    codefix_accepted_lines = VALUES(codefix_accepted_lines),
    codefix_generated_lines = VALUES(codefix_generated_lines),
    codefix_generation_count = VALUES(codefix_generation_count),
    codereview_failed_count = VALUES(codereview_failed_count),
    codereview_findings_count = VALUES(codereview_findings_count),
    codereview_succeeded_count = VALUES(codereview_succeeded_count),
    dev_acceptance_count = VALUES(dev_acceptance_count),
    dev_accepted_lines = VALUES(dev_accepted_lines),
    dev_generated_lines = VALUES(dev_generated_lines),
    dev_generation_count = VALUES(dev_generation_count),
    docgen_accepted_file_updates = VALUES(docgen_accepted_file_updates),
    docgen_accepted_file_creations = VALUES(docgen_accepted_file_creations),
    docgen_accepted_line_additions = VALUES(docgen_accepted_line_additions),
    docgen_accepted_line_updates = VALUES(docgen_accepted_line_updates),
    docgen_event_count = VALUES(docgen_event_count),
    docgen_rejected_file_creations = VALUES(docgen_rejected_file_creations),
    docgen_rejected_file_updates = VALUES(docgen_rejected_file_updates),
    docgen_rejected_line_additions = VALUES(docgen_rejected_line_additions),
    docgen_rejected_line_updates = VALUES(docgen_rejected_line_updates),
    inlinechat_acceptance_count = VALUES(inlinechat_acceptance_count),
    inlinechat_accepted_line_additions = VALUES(inlinechat_accepted_line_additions),
    inlinechat_accepted_line_deletions = VALUES(inlinechat_accepted_line_deletions),
    inlinechat_dismissal_count = VALUES(inlinechat_dismissal_count),
    inlinechat_dismissed_line_additions = VALUES(inlinechat_dismissed_line_additions),
    inlinechat_dismissed_line_deletions = VALUES(inlinechat_dismissed_line_deletions),
    inlinechat_rejected_line_additions = VALUES(inlinechat_rejected_line_additions),
    inlinechat_rejected_line_deletions = VALUES(inlinechat_rejected_line_deletions),
    inlinechat_rejection_count = VALUES(inlinechat_rejection_count),
    inlinechat_total_count = VALUES(inlinechat_total_count),
    inline_ai_code_lines = VALUES(inline_ai_code_lines),
    inline_acceptance_count = VALUES(inline_acceptance_count),
    inline_suggestions_count = VALUES(inline_suggestions_count),
    testgen_accepted_lines = VALUES(testgen_accepted_lines),
    testgen_accepted_tests = VALUES(testgen_accepted_tests),
    testgen_event_count = VALUES(testgen_event_count),
    testgen_generated_lines = VALUES(testgen_generated_lines),
    testgen_generated_tests = VALUES(testgen_generated_tests),
    transformation_event_count = VALUES(transformation_event_count),
    transformation_lines_generated = VALUES(transformation_lines_generated),
    transformation_lines_ingested = VALUES(transformation_lines_ingested);
"""


def upsert_user_report_rows(rows: list[tuple], conn=None):
    """Batch upsert rows into kiro_user_report.

    Pass an existing `conn` to reuse a connection across multiple calls
    (avoids reconnect overhead when loading many files in a loop).
    """
    if not rows:
        return
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_USER_REPORT, rows)
        logger.info(f"Upserted {len(rows)} rows into kiro_user_report")
    finally:
        if owns_conn:
            conn.close()


def upsert_by_user_analytic_rows(rows: list[tuple], conn=None):
    """Batch upsert rows into kiro_by_user_analytic.

    Pass an existing `conn` to reuse a connection across multiple calls.
    """
    if not rows:
        return
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.executemany(UPSERT_BY_USER_ANALYTIC, rows)
        logger.info(f"Upserted {len(rows)} rows into kiro_by_user_analytic")
    finally:
        if owns_conn:
            conn.close()
