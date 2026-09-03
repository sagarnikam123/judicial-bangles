#!/usr/bin/env python3
"""Read, search, and analyze downloaded Kiro data locally — 100% offline (no DB or S3 needed).

Overview:
  This tool provides instant CLI inspection and analytical queries over raw telemetry files
  stored on local disk (`data/<account_id>/...`). It requires neither active AWS credentials
  nor running database servers.

What it reads:
  1. prompts (prompt_logs/*.json.gz):
     - Inspect raw conversation requests, prompts, and assistant responses.
     - Filter by user (email or UUID), AI model, and keyword full-text search.
     - Toggle verbose mode (-v) to view full multiline prompt and response text.
  2. credits (user_report/*.csv):
     - View per-user daily credit consumption, plan tiers (PRO, PRO_PLUS, PRO_MAX),
       overage limits, client surfaces (IDE, CLI, PLUGIN), and model usage counts.
  3. activity (by_user_analytic/*.csv):
     - Inspect developer feature telemetry across 46 metrics (CodeFix, DocGeneration,
       TestGeneration, Chat, Inline suggestions, Dev cycles).
  4. summary (all datasets):
     - Generate instant statistical overviews: total credits consumed, top users,
       message breakdown across all 20 AI models, and average token/character sizes.

How user resolution works (Cross-file correlation):
  In AWS IAM Identity Center:
    - user_report CSVs store: <user_uuid> (or <idc_instance_id>-<user_uuid>) alongside User_Email.
    - prompt_logs JSONs store: d-<idc_instance_id>.<user_uuid>.
  When you pass `--user <email>` (e.g. `--user kyadav`):
    `_resolve_user_filter_to_ids()` scans the local `user_report/*.csv` files to match the email,
    retrieves the user's UUID, and automatically matches their conversation events in prompt_logs.

CLI Subcommands & Examples:
  # Search prompt logs for a keyword on a specific date
  python read_logs.py prompts --account <account_id> --date 2026-08-22 --search "kubectl"

  # Filter prompt logs by user email and model
  python read_logs.py prompts --account <account_id> --date 2026-08-22 --user jdoe --model claude-opus

  # View full prompt + response conversation text
  python read_logs.py prompts --account <account_id> --date 2026-08-22 --user jdoe -v

  # Output prompt logs as JSON (pipe to jq)
  python read_logs.py prompts --account <account_id> --date 2026-08-22 --output json | jq .

  # View daily credit usage per user
  python read_logs.py credits --account <account_id> --date 2026-08-22

  # View developer feature activity (CodeFix, Tests, DocGen)
  python read_logs.py activity --account <account_id> --date 2026-08-22 --user jdoe

  # Generate full statistical summary across all datasets
  python read_logs.py summary --account <account_id> --date 2026-08-22
"""

import argparse
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from conf.config import ACCOUNTS, get_account_data_dir


def _user_matches(user_id: str, user_filter: str) -> bool:
    """Check if a userId matches the filter (substring, case-insensitive)."""
    return user_filter.lower() in user_id.lower()


def _resolve_user_filter_to_ids(account_id: str, user_filter: str) -> set:
    """Resolve an email or username string to all matching Identity Center user IDs.

    Scans local `user_report/*.csv` files to map user emails (e.g. 'kyadav@securonix.com')
    to user UUIDs (e.g. '51cbc5b0-8091-7097-879b-d425da780157').
    Returns a set containing:
      1. Raw CSV user ID (e.g. UUID or 10-char prefixed ID)
      2. Pure UUID suffix
      3. Dot-separated prompt_log format: 'd-<idc>.<uuid>'
    This enables seamless cross-file user matching in prompt logs without requiring
    the caller to know the internal Identity Center instance ID.
    """
    user_report_dir = get_account_data_dir(account_id) / "user_report"
    if not user_report_dir.exists():
        return set()

    user_ids = set()
    for f in user_report_dir.glob("*.csv"):
        try:
            df = pd.read_csv(f, dtype=str, usecols=["UserId", "User_Email"])
            # Match by email OR userId substring
            mask = (
                df["User_Email"].str.contains(user_filter, case=False, na=False) |
                df["UserId"].str.contains(user_filter, case=False, na=False)
            )
            matches = df[mask]
            for uid in matches["UserId"].str.strip('"').tolist():
                user_ids.add(uid)
                # If uid contains an IdC prefix (e.g. 9a672808d8-uuid), add both the pure UUID and prompt_log dot format
                if "-" in uid:
                    parts = uid.split("-", 1)
                    user_ids.add(parts[1])
                    user_ids.add(f"d-{parts[0]}.{parts[1]}")
        except Exception:
            continue
    return user_ids


# -- Prompt log reader --

def read_prompt_logs(account_id: str, date: str | None = None, user: str | None = None,
                     model: str | None = None, search: str | None = None,
                     output: str = "text", limit: int | None = 50) -> list[dict]:
    """Search and filter prompt conversation logs from local disk (.json.gz).

    Traverses data/<account_id>/prompt_logs/, streaming JSON records.
    Applies filters:
      - date: YYYY-MM-DD (filters files by date segment in filename)
      - user: email substring, full email, or user UUID (resolved via _resolve_user_filter_to_ids)
      - model: modelId substring (e.g. 'claude-opus', 'auto')
      - search: case-insensitive keyword search across prompt and assistantResponse text
      - limit: maximum number of matching conversation records to return
    """
    prompt_dir = get_account_data_dir(account_id) / "prompt_logs"
    if not prompt_dir.exists():
        print(f"No prompt_logs directory at {prompt_dir}", file=sys.stderr)
        print(f"Download first: python s3_sync.py --account <profile> --prompt-logs --date <date>", file=sys.stderr)
        return []

    # Filter files by date if specified (date is in filename: YYYYMMDD)
    files = sorted(prompt_dir.glob("*.json.gz"))
    if date:
        dt = datetime.strptime(date, "%Y-%m-%d")
        date_str = dt.strftime("%Y%m%d")
        files = [f for f in files if date_str in f.name]

    if not files:
        print(f"No prompt_log files found for date={date}", file=sys.stderr)
        return []

    # Resolve user filter
    user_ids = set()
    if user:
        user_ids = _resolve_user_filter_to_ids(account_id, user)

    results = []
    for f in files:
        try:
            with gzip.open(f, "rt", encoding="utf-8") as gz:
                data = json.load(gz)
        except Exception as e:
            print(f"Error reading {f.name}: {e}", file=sys.stderr)
            continue

        for rec in data.get("records", []):
            req = rec.get("generateAssistantResponseEventRequest", {})
            resp = rec.get("generateAssistantResponseEventResponse", {})

            rec_user_id = req.get("userId", "") or ""
            rec_model = req.get("modelId") or ""
            rec_prompt = req.get("prompt") or ""
            rec_response = resp.get("assistantResponse") or ""

            # Apply filters
            if user:
                matched = False
                if _user_matches(rec_user_id, user):
                    matched = True
                norm_uid = rec_user_id.split(".", 1)[1] if "." in rec_user_id else rec_user_id
                if user_ids and (any(uid.lower() in rec_user_id.lower() for uid in user_ids) or norm_uid in user_ids):
                    matched = True
                if not matched:
                    continue

            if model and model.lower() not in rec_model.lower():
                continue

            if search:
                combined = rec_prompt + rec_response
                if search.lower() not in combined.lower():
                    continue

            results.append({
                "file": f.name,
                "timestamp": req.get("timeStamp", ""),
                "userId": rec_user_id,
                "modelId": rec_model,
                "chatTriggerType": req.get("chatTriggerType", ""),
                "requestId": resp.get("requestId", ""),
                "prompt_length": len(rec_prompt),
                "response_length": len(rec_response),
                "prompt": rec_prompt,
                "response": rec_response,
            })

            if limit and len(results) >= limit:
                break

        if limit and len(results) >= limit:
            break

    return results


# -- User report reader --

def read_user_report(account_id: str, date: str | None = None, user: str | None = None,
                     output: str = "text") -> list[dict]:
    """Read, filter, and extract user_report CSV records from local disk.

    Parses daily per-client credit/subscription reports:
      - date: YYYY-MM-DD (filters files by date in filename)
      - user: email substring or userId fragment
    Returns list of dicts with credit usage, overage, subscription tier, and model counts.
    """
    report_dir = get_account_data_dir(account_id) / "user_report"
    if not report_dir.exists():
        print(f"No user_report directory at {report_dir}", file=sys.stderr)
        return []

    files = sorted(report_dir.glob("*.csv"))
    if date:
        dt = datetime.strptime(date, "%Y-%m-%d")
        date_str = dt.strftime("%Y%m%d")
        files = [f for f in files if date_str in f.name]

    results = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception as e:
            print(f"Error reading {f.name}: {e}", file=sys.stderr)
            continue

        if user:
            mask = (
                df.get("User_Email", pd.Series(dtype=str)).str.contains(user, case=False, na=False) |
                df.get("UserId", pd.Series(dtype=str)).str.contains(user, case=False, na=False)
            )
            df = df[mask]

        for _, row in df.iterrows():
            results.append(row.to_dict())

    return results


# -- By user analytic reader --

def read_by_user_analytic(account_id: str, date: str | None = None, user: str | None = None,
                          output: str = "text") -> list[dict]:
    """Read, filter, and extract by_user_analytic CSV records from local disk.

    Parses detailed developer feature telemetry (46 metrics):
      - date: YYYY-MM-DD
      - user: userId fragment or email (automatically resolved to userId)
    Returns list of dicts containing chat, code fix, docgen, testgen, and transformation counts.
    """
    analytic_dir = get_account_data_dir(account_id) / "by_user_analytic"
    if not analytic_dir.exists():
        print(f"No by_user_analytic directory at {analytic_dir}", file=sys.stderr)
        return []

    files = sorted(analytic_dir.glob("*.csv"))
    if date:
        dt = datetime.strptime(date, "%Y-%m-%d")
        date_str = dt.strftime("%Y%m%d")
        files = [f for f in files if date_str in f.name]

    # Resolve user → userId for matching
    user_ids = set()
    if user:
        user_ids = _resolve_user_filter_to_ids(account_id, user)

    results = []
    for f in files:
        try:
            df = pd.read_csv(f, dtype=str)
        except Exception as e:
            print(f"Error reading {f.name}: {e}", file=sys.stderr)
            continue

        if user:
            mask = df["UserId"].str.contains(user, case=False, na=False)
            if user_ids:
                for uid in user_ids:
                    mask = mask | df["UserId"].str.contains(uid, case=False, na=False)
            df = df[mask]

        for _, row in df.iterrows():
            results.append(row.to_dict())

    return results


# -- Summary generators --

def summarize_credits(account_id: str, date: str | None = None) -> dict:
    """Generate aggregate statistical overview of credit and subscription usage.

    Calculates:
      - Total credits consumed and overage credits across all users
      - Breakdown by client surface (IDE, CLI, PLUGIN) and subscription tier (PRO, PRO_PLUS, PRO_MAX)
      - Top 5 users by total credit consumption
      - Total messages sent across all 20 active AI models
    """
    results = read_user_report(account_id, date=date)
    if not results:
        return {"error": "No user_report data found"}

    df = pd.DataFrame(results)
    # Coerce numeric columns
    for col in ["Credits_Used", "Overage_Credits_Used", "Total_Messages", "Chat_Conversations"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    summary = {
        "date": date or "all available",
        "total_users": df["User_Email"].nunique() if "User_Email" in df.columns else df["UserId"].nunique(),
        "total_credits_used": round(df["Credits_Used"].sum(), 2),
        "total_overage_credits": round(df["Overage_Credits_Used"].sum(), 2),
        "total_messages": int(df["Total_Messages"].sum()),
        "total_conversations": int(df["Chat_Conversations"].sum()),
        "by_client_type": {},
        "by_tier": {},
        "top_users_by_credits": [],
        "model_usage": {},
    }

    # By client type
    for ct, grp in df.groupby("Client_Type"):
        summary["by_client_type"][ct] = {
            "users": int(grp["UserId"].nunique()),
            "credits": round(grp["Credits_Used"].sum(), 2),
            "messages": int(grp["Total_Messages"].sum()),
        }

    # By tier
    if "Subscription_Tier" in df.columns:
        for tier, grp in df.groupby("Subscription_Tier"):
            summary["by_tier"][tier] = {
                "users": int(grp["UserId"].nunique()),
                "credits": round(grp["Credits_Used"].sum(), 2),
            }

    # Top 5 users by credits
    if "User_Email" in df.columns:
        top = df.groupby("User_Email")["Credits_Used"].sum().nlargest(5)
        summary["top_users_by_credits"] = [{"user": email, "credits": round(c, 2)} for email, c in top.items()]

    # Model usage (sum of model-specific message columns)
    model_cols = [c for c in df.columns if c.endswith("_messages")]
    for col in model_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        total = int(df[col].sum())
        if total > 0:
            summary["model_usage"][col.replace("_messages", "")] = total

    return summary


def summarize_activity(account_id: str, date: str | None = None) -> dict:
    """Generate aggregate statistical overview of developer feature activity.

    Calculates:
      - Chat activity: messages sent, AI code lines generated, interactions
      - Inline completions: suggestions, acceptance count, and acceptance rate percentage
      - CodeFix: generation and acceptance counts, lines generated and accepted
      - CodeReview: succeeded/failed events, findings count
      - TestGeneration & DocGeneration: tests generated/accepted, files and lines updated
      - Transformation: code modernized/transformed
    """
    results = read_by_user_analytic(account_id, date=date)
    if not results:
        return {"error": "No by_user_analytic data found"}

    df = pd.DataFrame(results)
    # Coerce all numeric columns
    for col in df.columns:
        if col not in ("UserId", "Date"):
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    summary = {
        "date": date or "all available",
        "total_users": int(df["UserId"].nunique()),
        "chat": {
            "messages_sent": int(df["Chat_MessagesSent"].sum()),
            "ai_code_lines": int(df["Chat_AICodeLines"].sum()),
            "messages_interacted": int(df["Chat_MessagesInteracted"].sum()),
        },
        "inline_completions": {
            "suggestions": int(df["Inline_SuggestionsCount"].sum()),
            "accepted": int(df["Inline_AcceptanceCount"].sum()),
            "acceptance_rate": f"{df['Inline_AcceptanceCount'].sum() / max(df['Inline_SuggestionsCount'].sum(), 1) * 100:.1f}%",
            "ai_code_lines": int(df["Inline_AICodeLines"].sum()),
        },
        "code_fix": {
            "generated": int(df["CodeFix_GenerationEventCount"].sum()),
            "accepted": int(df["CodeFix_AcceptanceEventCount"].sum()),
            "generated_lines": int(df["CodeFix_GeneratedLines"].sum()),
            "accepted_lines": int(df["CodeFix_AcceptedLines"].sum()),
        },
        "code_review": {
            "succeeded": int(df["CodeReview_SucceededEventCount"].sum()),
            "failed": int(df["CodeReview_FailedEventCount"].sum()),
            "findings": int(df["CodeReview_FindingsCount"].sum()),
        },
        "test_generation": {
            "events": int(df["TestGeneration_EventCount"].sum()),
            "tests_generated": int(df["TestGeneration_GeneratedTests"].sum()),
            "tests_accepted": int(df["TestGeneration_AcceptedTests"].sum()),
        },
        "doc_generation": {
            "events": int(df["DocGeneration_EventCount"].sum()),
            "files_created": int(df["DocGeneration_AcceptedFilesCreations"].sum()),
            "lines_added": int(df["DocGeneration_AcceptedLineAdditions"].sum()),
        },
        "inline_chat": {
            "total_events": int(df["InlineChat_TotalEventCount"].sum()),
            "accepted": int(df["InlineChat_AcceptanceEventCount"].sum()),
            "rejected": int(df["InlineChat_RejectionEventCount"].sum()),
            "dismissed": int(df["InlineChat_DismissalEventCount"].sum()),
        },
        "transformation": {
            "events": int(df["Transformation_EventCount"].sum()),
            "lines_generated": int(df["Transformation_LinesGenerated"].sum()),
            "lines_ingested": int(df["Transformation_LinesIngested"].sum()),
        },
    }
    return summary


def summarize_prompts(account_id: str, date: str | None = None) -> dict:
    """Generate aggregate statistical overview of prompt conversation records.

    Calculates:
      - Total requests executed
      - Model distribution (invocations per model)
      - User distribution (requests per user UUID)
      - Character/token volumes: average prompt length, average response length
      - Percentage of responses containing code blocks (```)
    """
    results = read_prompt_logs(account_id, date=date, limit=None)
    if not results:
        return {"error": "No prompt_logs data found"}

    models = {}
    users = {}
    total_prompt_chars = 0
    total_response_chars = 0
    has_code_count = 0

    for r in results:
        # Model distribution
        model = r["modelId"] or "(none)"
        models[model] = models.get(model, 0) + 1

        # User distribution
        uid_short = r["userId"].split(".")[-1][:20]
        users[uid_short] = users.get(uid_short, 0) + 1

        total_prompt_chars += r["prompt_length"]
        total_response_chars += r["response_length"]
        if "```" in r["response"]:
            has_code_count += 1

    total = len(results)
    summary = {
        "date": date or "all available",
        "total_requests": total,
        "unique_users": len(users),
        "avg_prompt_length": round(total_prompt_chars / max(total, 1)),
        "avg_response_length": round(total_response_chars / max(total, 1)),
        "responses_with_code_pct": f"{has_code_count / max(total, 1) * 100:.1f}%",
        "by_model": dict(sorted(models.items(), key=lambda x: -x[1])),
        "top_users_by_requests": dict(sorted(users.items(), key=lambda x: -x[1])[:10]),
    }
    return summary


# -- Output formatters --

def print_prompt_results(results: list[dict], output: str, verbose: bool = False):
    """Print prompt log results."""
    if output == "json":
        print(json.dumps(results, indent=2, default=str))
        return

    for i, r in enumerate(results, 1):
        raw_ts = r.get("timestamp", "")
        clean_ts = raw_ts.split(".")[0].replace("T", " ") if "T" in raw_ts else raw_ts
        p_tok = r["prompt_length"] // 4
        r_tok = r["response_length"] // 4
        has_code = "yes" if "```" in r.get("response", "") else "no"
        model_name = r["modelId"] or "(none)"

        print(f"\n{'='*80}")
        print(f"[{i}] {clean_ts}  |  model: {model_name}  |  user: {r['userId'].split('.')[-1][:12]}...")
        print(f"    requestId: {r['requestId']}")
        print(f"    prompt: {r['prompt_length']} chars (~{p_tok} tokens)  |  response: {r['response_length']} chars (~{r_tok} tokens)  |  code: {has_code}")
        if verbose:
            print(f"\n--- PROMPT ---")
            prompt = r["prompt"]
            if "--- USER MESSAGE BEGIN ---" in prompt:
                user_msg = prompt.split("--- USER MESSAGE BEGIN ---")[1].split("--- USER MESSAGE END ---")[0].strip()
                print(user_msg[:2000])
            else:
                print(prompt[:2000])
            print(f"\n--- RESPONSE ---")
            print(r["response"][:3000])
        else:
            prompt = r["prompt"]
            if "--- USER MESSAGE BEGIN ---" in prompt:
                user_msg = prompt.split("--- USER MESSAGE BEGIN ---")[1].split("--- USER MESSAGE END ---")[0].strip()
                print(f"    prompt: {user_msg[:200]}{'...' if len(user_msg) > 200 else ''}")
            else:
                print(f"    prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}")

    print(f"\n{'='*80}")
    print(f"Total: {len(results)} records")


def print_csv_results(results: list[dict], output: str):
    """Print CSV-derived results."""
    if not results:
        print("No matching records found.")
        return

    if output == "json":
        print(json.dumps(results, indent=2, default=str))
        return

    df = pd.DataFrame(results)
    non_empty = df.columns[df.apply(lambda col: col.astype(str).str.strip().ne("").any() & col.astype(str).ne("0").any())]
    df_display = df[non_empty] if len(non_empty) > 0 else df
    print(df_display.to_string(index=False))
    print(f"\nTotal: {len(results)} records")


def print_summary(summary: dict, output: str):
    """Print a summary dict."""
    if output == "json":
        print(json.dumps(summary, indent=2, default=str))
        return

    if "error" in summary:
        print(summary["error"])
        return

    def _print_section(title, data, indent=2):
        prefix = " " * indent
        print(f"\n{prefix}{title}:")
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    print(f"{prefix}  {k}:")
                    for kk, vv in v.items():
                        print(f"{prefix}    {kk}: {vv}")
                else:
                    print(f"{prefix}  {k}: {v}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    parts = [f"{k}={v}" for k, v in item.items()]
                    print(f"{prefix}  {', '.join(parts)}")
                else:
                    print(f"{prefix}  {item}")

    print(f"\n{'='*60}")
    print(f"  SUMMARY — {summary.get('date', '?')}")
    print(f"{'='*60}")

    # Print top-level scalars
    for k, v in summary.items():
        if k == "date":
            continue
        if isinstance(v, (dict, list)):
            _print_section(k, v)
        else:
            print(f"  {k}: {v}")

    print(f"\n{'='*60}")


# -- Main --

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read and filter downloaded Kiro data locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View all prompts for a user on a date
  python read_logs.py prompts --account 222222222222 --date 2026-08-22 --user jdoe

  # Search prompts containing "kubectl"
  python read_logs.py prompts --account 222222222222 --date 2026-08-22 --search kubectl

  # Filter by model
  python read_logs.py prompts --account 222222222222 --date 2026-08-22 --model claude-opus

  # Full prompt+response text (verbose)
  python read_logs.py prompts --account 222222222222 --date 2026-08-22 --user jdoe -v

  # View user credits for a date
  python read_logs.py credits --account 222222222222 --date 2026-08-24 --user jdoe

  # View feature activity for a user
  python read_logs.py activity --account 222222222222 --date 2026-08-24 --user jdoe

  # Output as JSON (pipe to jq, etc.)
  python read_logs.py prompts --account 222222222222 --date 2026-08-22 --user jdoe --output json

  # List all users active on a date
  python read_logs.py credits --account 222222222222 --date 2026-08-24

  # Summary of all file types for a date (aggregated stats)
  python read_logs.py summary --account 222222222222 --date 2026-08-24

  # Summary of only credits for a date
  python read_logs.py summary --account 222222222222 --date 2026-08-24 --type credits

  # Summary of only feature activity
  python read_logs.py summary --account 222222222222 --date 2026-08-24 --type activity

  # Summary of only prompt logs
  python read_logs.py summary --account 222222222222 --date 2026-08-22 --type prompts

  # Summary as JSON
  python read_logs.py summary --account 222222222222 --date 2026-08-24 --output json
        """)

    parser.add_argument("command", choices=["prompts", "credits", "activity", "summary"],
                        help="What to read: prompts (prompt_logs), credits (user_report), activity (by_user_analytic), summary (aggregated overview)")
    parser.add_argument("--account", type=str, required=True,
                        help="Account ID (e.g., 222222222222) or full profile name")
    parser.add_argument("--date", type=str, default=None,
                        help="Filter by date (YYYY-MM-DD)")
    parser.add_argument("--user", type=str, default=None,
                        help="Filter by user (email substring, e.g. 'jdoe', or userId fragment)")
    parser.add_argument("--model", type=str, default=None,
                        help="(prompts only) Filter by model (substring, e.g. 'claude-opus', 'auto')")
    parser.add_argument("--search", type=str, default=None,
                        help="(prompts only) Search text in prompt or response content")
    parser.add_argument("--type", type=str, choices=["credits", "activity", "prompts", "all"], default="all",
                        help="(summary only) Which file type to summarize (default: all)")
    parser.add_argument("--output", type=str, choices=["text", "json"], default="text",
                        help="Output format (default: text)")
    parser.add_argument("--limit", type=int, default=50,
                        help="(prompts only) Max results to return (default: 50)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="(prompts only) Show full prompt and response text")

    args = parser.parse_args()

    # Resolve account(s) — accept 'all', account_id, or full profile name
    target_accounts = {}
    if args.account == "all":
        for prof, cfg in ACCOUNTS.items():
            target_accounts[cfg["account_id"]] = cfg.get("label", prof)
    else:
        acc = args.account
        if "_" in acc:
            for prof, cfg in ACCOUNTS.items():
                if prof == acc or cfg["account_id"] == acc:
                    acc = cfg["account_id"]
                    break
        target_accounts[acc] = acc

    if args.command == "prompts":
        all_results = []
        for acc_id, acc_lbl in target_accounts.items():
            if len(target_accounts) > 1 and args.output != "json":
                print(f"\n{'#'*80}\n# Account: {acc_lbl} ({acc_id})\n{'#'*80}")
            res = read_prompt_logs(
                acc_id, date=args.date, user=args.user,
                model=args.model, search=args.search,
                output=args.output, limit=args.limit
            )
            all_results.extend(res)
        print_prompt_results(all_results, args.output, verbose=args.verbose)

    elif args.command == "credits":
        all_results = []
        for acc_id, acc_lbl in target_accounts.items():
            if len(target_accounts) > 1 and args.output != "json":
                print(f"\n{'#'*80}\n# Account: {acc_lbl} ({acc_id})\n{'#'*80}")
            res = read_user_report(acc_id, date=args.date, user=args.user, output=args.output)
            all_results.extend(res)
        print_csv_results(all_results, args.output)

    elif args.command == "activity":
        all_results = []
        for acc_id, acc_lbl in target_accounts.items():
            if len(target_accounts) > 1 and args.output != "json":
                print(f"\n{'#'*80}\n# Account: {acc_lbl} ({acc_id})\n{'#'*80}")
            res = read_by_user_analytic(acc_id, date=args.date, user=args.user, output=args.output)
            all_results.extend(res)
        print_csv_results(all_results, args.output)

    elif args.command == "summary":
        summary_type = getattr(args, "type", "all")
        if args.output == "json":
            combined_all = {}
            for acc_id, acc_lbl in target_accounts.items():
                acc_summary = {}
                if summary_type in ("credits", "all"):
                    acc_summary["credits"] = summarize_credits(acc_id, date=args.date)
                if summary_type in ("activity", "all"):
                    acc_summary["activity"] = summarize_activity(acc_id, date=args.date)
                if summary_type in ("prompts", "all"):
                    acc_summary["prompts"] = summarize_prompts(acc_id, date=args.date)
                combined_all[acc_id] = acc_summary
            # If a single account was requested, unwrap root key for simpler parsing
            output_obj = combined_all if args.account == "all" else next(iter(combined_all.values()))
            print(json.dumps(output_obj, indent=2, default=str))
        else:
            for acc_id, acc_lbl in target_accounts.items():
                if len(target_accounts) > 1:
                    print(f"\n{'#'*80}\n# Account: {acc_lbl} ({acc_id})\n{'#'*80}")

                if summary_type in ("credits", "all"):
                    s = summarize_credits(acc_id, date=args.date)
                    if summary_type == "all":
                        print("\n" + "─" * 60)
                        print("  USER REPORT (credits/subscription)")
                        print("─" * 60)
                    print_summary(s, "text")

                if summary_type in ("activity", "all"):
                    s = summarize_activity(acc_id, date=args.date)
                    if summary_type == "all":
                        print("\n" + "─" * 60)
                        print("  BY USER ANALYTIC (feature usage)")
                        print("─" * 60)
                    print_summary(s, "text")

                if summary_type in ("prompts", "all"):
                    s = summarize_prompts(acc_id, date=args.date)
                    if summary_type == "all":
                        print("\n" + "─" * 60)
                        print("  PROMPT LOGS (conversations)")
                        print("─" * 60)
                    print_summary(s, "text")
