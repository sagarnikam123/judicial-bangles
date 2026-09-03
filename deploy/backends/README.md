# Backend Deployment Guides

Judicial Bangles supports five distinct storage backends. Choose the backend that fits your team's existing infrastructure, query patterns, and Grafana datasource setup.

---

## Supported Backends & Operational Guides

Each backend guide provides step-by-step instructions for:
- Local startup (`docker-compose` & Homebrew)
- CLI connection commands (`mysql`, `psql`, `clickhouse-client`, or `curl`)
- Data verification (table/index listings, schemas, row/doc counts)
- Analytics queries (top users, credit consumption, model breakdown, prompt joins)
- Data deletion (by date, by account, by user, or complete purge)

| Backend | `--backend` flag | Best for | Docker Compose | Operational Guide |
|---|---|---|---|---|
| **MySQL** | `mysql` | Relational analytics, SQL aggregations | [docker-compose.mysql.yml](../compose/docker-compose.mysql.yml) | [MySQL Operations Guide](mysql.md) |
| **PostgreSQL** | `postgres` | Relational metrics, JSONB fields, PostgreSQL ecosystems | [docker-compose.postgres.yml](../compose/docker-compose.postgres.yml) | [PostgreSQL Operations Guide](postgres.md) |
| **ClickHouse** | `clickhouse` | High-volume columnar storage, 300k+ prompt events | [docker-compose.clickhouse.yml](../compose/docker-compose.clickhouse.yml) | [ClickHouse Operations Guide](clickhouse.md) |
| **OpenSearch** | `opensearch` | Full-text conversation search, Dashboards | [docker-compose.opensearch.yml](../compose/docker-compose.opensearch.yml) | [OpenSearch Operations Guide](opensearch.md) |
| **Elasticsearch** | `elasticsearch` | Full-text conversation search, Elastic stack | [docker-compose.elasticsearch.yml](../compose/docker-compose.elasticsearch.yml) | [Elasticsearch Operations Guide](elasticsearch.md) |

---

## 1-Command Local Spin-up

You can spin up any backend locally using the ready-to-run recipes in `deploy/compose/`:

```bash
# Pick ONE backend to launch:
docker compose -f deploy/compose/docker-compose.mysql.yml up -d
docker compose -f deploy/compose/docker-compose.postgres.yml up -d
docker compose -f deploy/compose/docker-compose.clickhouse.yml up -d
docker compose -f deploy/compose/docker-compose.opensearch.yml up -d
docker compose -f deploy/compose/docker-compose.elasticsearch.yml up -d
```

---

## Detailed Enterprise & Bare-Metal Installations

For enterprise, clustered, or Kubernetes deployment patterns, full production recipes are maintained in the companion repository:
👉 [sagarnikam123-blog-youtube-code-samples](https://github.com/sagarnikam123/sagarnikam123-blog-youtube-code-samples)

Available installation modes include:
- **Bare-metal & Package Managers**: APT/DEB (Ubuntu/Debian), RPM (RHEL/Rocky), Homebrew (macOS), Native Binaries
- **Kubernetes & Production**: Helm Charts, CloudNativePG, Oracle MySQL Operator, Altinity ClickHouse Operator, ECK (Elastic Cloud on Kubernetes), OpenSearch Kubernetes Operator
