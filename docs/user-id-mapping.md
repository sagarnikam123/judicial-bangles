# UserId Format & Cross-File Matching

Reference guide for IAM Identity Center UserId representation across CSV reports and JSON prompt logs, conversion rules, and SQL joins.

---

## Overview

The same IAM Identity Center user has **different `userId` formats** depending on the source file type. When joining tables or correlating prompt logs with user profiles, you must account for these format differences.

### Formats per File Type

Depending on the AWS account configuration, `userId` in CSV reports can appear in two variants:
1. **Prefixed variant**: `<idc_instance_id>-<user_uuid>` (e.g. `9a672808d8-6c616e13-93df-45c6-8821-72243fe61ffc`)
2. **Pure UUID variant**: `<user_uuid>` (e.g. `010b05c0-f021-703d-8018-d2d050779a5c`)

In `prompt_logs`, the format is always `d-<idc_instance_id>.<user_id_in_csv>`.

| File type | `userId` example | Format pattern |
|---|---|---|
| `user_report` CSV | `9a672808d8-aaaa...` or `010b05c0-...` | `<idc_instance_id>-<uuid>` or `<uuid>` |
| `by_user_analytic` CSV | `9a672808d8-aaaa...` or `010b05c0-...` | Same as user_report |
| `prompt_logs` JSON | `d-9a672808d8.010b05c0-...` | `d-<idc_instance_id>.<user_id_in_csv>` |

---

## Anatomy of the ID

```
prompt_logs format:   d-9a672808d8.010b05c0-f021-703d-8018-d2d050779a5c
                      ├┘├────────┘ ├──────────────────────────────────┘
                    prefix  IdC ID  Exact userId as stored in user_report
```

- **Extraction rule:** The string following the first dot (`.`) in `prompt_logs.userId` matches `user_report.UserId` directly in 100% of cases.
- In `kiro_prompt_log`, this is stored as `user_id_normalized` for direct, high-speed joins.

---

## How `read_logs.py` Resolves Users

When invoking `read_logs.py --user <name_or_email>`:

1. Scans `user_report` CSV files to find matching `User_Email`.
2. Resolves the user's `userId` in `user_report` format (e.g. `d0d0d0d0d0-aaaaaaaa-...`).
3. Computes both representations (`user_report` and `prompt_logs` format).
4. Matches records against either representation across prompts, credit reports, and activity logs.

This allows CLI filtering by email/username without manually looking up Identity Center UUIDs.

---

## SQL & Grafana Joins

To join `kiro_user_report` with `kiro_prompt_log` in SQL:

```sql
-- MySQL / ClickHouse / PostgreSQL:
SELECT 
    r.user_email,
    p.event_timestamp,
    p.model_id,
    p.request_id,
    p.prompt_text,
    p.response_text
FROM kiro_prompt_log p
JOIN kiro_user_report r
  ON r.user_id = REPLACE(REPLACE(p.user_id, 'd-', ''), '.', '-')
  AND r.aws_account_id = p.aws_account_id
WHERE r.account_label = '$account_label'
ORDER BY p.event_timestamp DESC
LIMIT 100;
```
