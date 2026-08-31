"""MySQL writer — generates DDL + upsert SQL from Dataset metadata.

One code path for all three datasets. Column types are derived from the
Dataset field lists so the schema can never drift from the row tuple.
"""

import logging

from conf.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from writers.base import Dataset, Writer
from writers.sqlgen import mysql_column_type, upsert_sql_mysql

logger = logging.getLogger(__name__)


class MySQLWriter(Writer):
    def __init__(self):
        self.conn = None
        self._schema_ready = set()

    def _connect(self):
        if self.conn is None:
            import pymysql  # lazy import
            self.conn = pymysql.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, database=DB_NAME,
                charset="utf8mb4", autocommit=True,
            )
        return self.conn

    def _ddl(self, ds: Dataset) -> str:
        cols = ["    id BIGINT AUTO_INCREMENT PRIMARY KEY"]
        for c in ds.columns:
            cols.append(f"    {c} {mysql_column_type(ds, c)}")
        cols.append("    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        uq = ", ".join(ds.unique_key)
        cols.append(f"    UNIQUE KEY uq_{ds.name} ({uq})")
        cols.append(f"    INDEX idx_{ds.name}_date ({ds.date_col})")
        body = ",\n".join(cols)
        return f"CREATE TABLE IF NOT EXISTS {ds.name} (\n{body}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"

    def init_schema(self, ds: Dataset) -> None:
        conn = self._connect()
        with conn.cursor() as cur:
            cur.execute(self._ddl(ds))
        self._schema_ready.add(ds.name)

    def write(self, ds: Dataset, rows: list[tuple]) -> int:
        if not rows:
            return 0
        if ds.name not in self._schema_ready:
            self.init_schema(ds)
        conn = self._connect()
        with conn.cursor() as cur:
            cur.executemany(upsert_sql_mysql(ds), rows)
        logger.info(f"[mysql] upserted {len(rows)} rows into {ds.name}")
        return len(rows)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None
