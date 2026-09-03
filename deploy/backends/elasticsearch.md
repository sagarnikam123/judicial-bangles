# Elasticsearch Deployment & Operations Guide

Elasticsearch provides robust distributed search and analytical log indexing for Kiro telemetry and conversation records.

---

## 1. Local Quick Start (Docker Compose)

Launch single-node Elasticsearch 8.17 with basic security disabled for local testing:

```bash
docker compose -f deploy/compose/docker-compose.elasticsearch.yml up -d
```

- **REST API**: `http://localhost:9200`
- **Security**: Disabled (no password required for local development)

To stop:
```bash
docker compose -f deploy/compose/docker-compose.elasticsearch.yml down
```

---

## 2. Local Native Start (macOS Homebrew)

```bash
brew tap elastic/tap
brew install elastic/tap/elasticsearch-full
brew services start elasticsearch-full

# Verify:
curl -s http://localhost:9200
```

---

## 3. Configuration (`conf/.env.kiro`)

```bash
STORAGE_BACKEND=elasticsearch

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
python main.py --account <profile> --backend elasticsearch --date 2026-08-22

# Push ONLY prompt logs
python main.py --account <profile> --backend elasticsearch --dataset prompt_logs --date 2026-08-22

# Push existing local files without S3 download
python main.py --account <profile> --backend elasticsearch --dataset prompt_logs --load-only
```

---

## 5. Verification Commands (via `curl`)

### Check cluster health:
```bash
curl -s http://localhost:9200/_cluster/health?pretty
```

### List all Kiro indices with document counts and storage size:
```bash
curl -s "http://localhost:9200/_cat/indices/kiro-*?v&s=index"
```

### Check document counts per index:
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
      "prompt_text": "python error exception"
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

## 8. Advanced & Production Deployments

For advanced production deployments, refer to the code samples repository:
👉 [sagarnikam123-blog-youtube-code-samples/elasticsearch/install/](https://github.com/sagarnikam123/sagarnikam123-blog-youtube-code-samples/tree/main/elasticsearch/install)

- **APT/DEB (Debian/Ubuntu)**: `elasticsearch/install/deb/`
- **RPM (RHEL/Rocky/CentOS)**: `elasticsearch/install/rpm/`
- **Kubernetes (Helm)**: `elasticsearch/install/helm/` (Elastic Helm chart)
- **Kubernetes (Operator)**: `elasticsearch/install/operator/` (Elastic Cloud on Kubernetes / ECK)
