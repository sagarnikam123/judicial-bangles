"""PostgreSQL writer — generates DDL + ON CONFLICT upsert from Dataset metadata."""

import logging

from conf.config import PG_DB, PG_HOST, PG_PASSWORD, PG_PORT, PG_USER
from writers.base import Dataset, Writer
from writers.sqlgen import postgres_column_type, upsert_sql_postgres

logger = logging.getLogger(__name__)


class PostgresWriter(Writer):
    def __init__(self):
        self.conn = None
        self._schema_ready = set()

    def _connect(self):
        if self.conn is None:
            import psycopg2  # lazy import
            self.conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, dbname=PG_DB,
                user=PG_USER, password=PG_PASSWORD,
            )
            self.conn.autocommit = True
        return self.conn

    def _ddl(self, ds: Dataset) -> str:
        cols = ["    id BIGSERIAL PRIMARY KEY"]
        for c in ds.columns:
            cols.append(f"    {c} {postgres_column_type(ds, c)}")
        cols.append("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        uq = ", ".join(ds.unique_key)
        cols.append(f"    CONSTRAINT uq_{ds.name} UNIQUE ({uq})")
        body = ",\n".join(cols)
        create = f"CREATE TABLE IF NOT EXISTS {ds.name} (\n{body}\n);"
        idx = (f"CREATE INDEX IF NOT EXISTS idx_{ds.name}_date "
               f"ON {ds.name} ({ds.date_col});")
        return create + "\n" + idx

    def init_schema(self, ds: Dataset) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(self._ddl(ds))
            # Auto-migrate any newly introduced columns to existing tables
            for c in ds.columns:
                cur.execute(f"ALTER TABLE {ds.name} ADD COLUMN IF NOT EXISTS {c} {postgres_column_type(ds, c)};")
        self._schema_ready.add(ds.name)

    def write(self, ds: Dataset, rows: list[tuple]) -> int:
        if not rows:
            return 0
        if ds.name not in self._schema_ready:
            self.init_schema(ds)
        conn = self._connect()
        with conn.cursor() as cur:
            cur.executemany(upsert_sql_postgres(ds), rows)
        logger.info(f"[postgres] upserted {len(rows)} rows into {ds.name}")
        return len(rows)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
