# OpenSearch Deployment & Operations Guide

OpenSearch provides distributed search and analytics, ideal for full-text indexing, keyword discovery, and exploring Kiro prompt and response conversations.

---

## 1. Local Quick Start (Docker Compose)

Launch single-node OpenSearch 2.19 + OpenSearch Dashboards with the security plugin disabled for easy local testing:

```bash
docker compose -f deploy/compose/docker-compose.opensearch.yml up -d
```

- **OpenSearch REST API**: `http://localhost:9200`
- **OpenSearch Dashboards UI**: `http://localhost:5601`
- **Security**: Disabled (no authentication needed for local dev)

To stop:
```bash
docker compose -f deploy/compose/docker-compose.opensearch.yml down
```

---

## 2. Local Native Start (macOS Homebrew)

```bash
brew install opensearch
brew services start opensearch

# Verify:
curl -s http://localhost:9200
```

---

## 3. Configuration (`conf/.env.kiro`)

```bash
STORAGE_BACKEND=opensearch

OPENSEARCH_HOST='http://localhost:9200'
OPENSEARCH_USER=''
OPENSEARCH_PASSWORD=''
OPENSEARCH_INDEX_PREFIX='kiro-'
OPENSEARCH_VERIFY_CERTS='false'
```

---

## 4. Ingestion Commands

```bash
pip install -r requirements-opensearch.txt

# Push all datasets for a specific date (full text automatically indexed)
python main.py --account <profile> --backend opensearch --date 2026-08-22

# Push ONLY prompt logs
python main.py --account <profile> --backend opensearch --dataset prompt_logs --date 2026-08-22

# Push existing local files without S3 download
python main.py --account <profile> --backend opensearch --dataset prompt_logs --load-only
```

---

## 5. Verification Commands (via `curl`)

### Check cluster health and version:
```bash
curl -s http://localhost:9200/_cluster/health?pretty
```

### List all Kiro indices with document counts and storage size:
```bash
curl -s "http://localhost:9200/_cat/indices/kiro-*?v&s=index"
```

### Check document count per index:
```bash
curl -s "http://localhost:9200/kiro-kiro_user_report/_count?pretty"
curl -s "http://localhost:9200/kiro-kiro_by_user_analytic/_count?pretty"
curl -s "http://localhost:9200/kiro-kiro_prompt_log/_count?pretty"
```

### Inspect index mappings (schema):
```bash
curl -s "http://localhost:9200/kiro-kiro_prompt_log/_mapping?pretty"
```

---

## 6. Search & Analytical Queries

### Full-text search inside prompts:
```bash
curl -s -X GET "http://localhost:9200/kiro-kiro_prompt_log/_search?pretty" \
  -H "Content-Type: application/json" -d '{
  "query": {
    "match": {
      "prompt_text": "docker kubernetes terraform"
    }
  },
  "_source": ["event_timestamp", "user_id_normalized", "model_id", "prompt_char_count"]
}'
```

### Aggregate prompt volume by AI model:
```bash
curl -s -X GET "http://localhost:9200/kiro-kiro_prompt_log/_search?size=0&pretty" \
  -H "Content-Type: application/json" -d '{
  "aggs": {
    "models": {
      "terms": { "field": "model_id", "size": 10 }
    }
  }
}'
```

### Find conversations where code was generated in the response:
```bash
curl -s -X GET "http://localhost:9200/kiro-kiro_prompt_log/_search?pretty" \
  -H "Content-Type: application/json" -d '{
  "query": {
    "term": { "has_code_in_response": true }
  },
  "sort": [{ "event_timestamp": { "order": "desc" } }],
  "size": 5
}'
```

---

## 7. Data Deletion Commands

### Delete documents for a specific date:
```bash
curl -s -X POST "http://localhost:9200/kiro-kiro_user_report/_delete_by_query?pretty" \
  -H "Content-Type: application/json" -d '{
  "query": { "term": { "report_date": "2026-08-22" } }
}'

curl -s -X POST "http://localhost:9200/kiro-kiro_prompt_log/_delete_by_query?pretty" \
  -H "Content-Type: application/json" -d '{
  "query": {
    "range": {
      "event_timestamp": {
        "gte": "2026-08-22T00:00:00Z",
        "lte": "2026-08-22T23:59:59Z"
      }
    }
  }
}'
```

### Delete documents for a specific AWS account:
```bash
curl -s -X POST "http://localhost:9200/kiro-*/_delete_by_query?pretty" \
  -H "Content-Type: application/json" -d '{
  "query": { "term": { "aws_account_id": "073885930324" } }
}'
```

### Purge / Delete all Kiro indices in a single pass:
```bash
curl -s -X DELETE "http://localhost:9200/kiro-*"
```

---

## 8. OpenSearch Dashboards (Web UI)

Open **http://localhost:5601** in your browser:
1. Navigate to **Stack Management** > **Index Patterns**.
2. Create index patterns for `kiro-*` (use `event_timestamp` for prompt logs or `report_date` for CSV reports).
3. Go to **Discover** to visually search prompts, analyze models, and build usage dashboards.

---

## 9. Advanced & Production Deployments

For advanced production deployments, refer to the code samples repository:
👉 [sagarnikam123-blog-youtube-code-samples/opensearch/install/](https://github.com/sagarnikam123/sagarnikam123-blog-youtube-code-samples/tree/main/opensearch/install)

- **APT/DEB (Debian/Ubuntu)**: `opensearch/install/deb/`
- **RPM (RHEL/Rocky/CentOS)**: `opensearch/install/rpm/`
- **Kubernetes (Helm)**: `opensearch/install/helm/` (Official OpenSearch Helm chart)
- **Kubernetes (Operator)**: `opensearch/install/operator/` (OpenSearch K8s Operator)
