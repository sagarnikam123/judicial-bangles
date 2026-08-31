"""ClickHouse writer — generates ReplacingMergeTree DDL from Dataset metadata.

ClickHouse has no row-level UPSERT. ReplacingMergeTree ordered by the dataset's
unique_key collapses duplicate keys at merge time (last insert wins via the
created_at version column). Queries needing the deduped view use SELECT ... FINAL.

ponytail: dedup is eventual (on background merge), not on insert — the known
ClickHouse tradeoff. Upgrade path: FINAL in Grafana queries, already keyed for it.
"""

import logging
from datetime import date, datetime

from conf.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)
from writers.base import Dataset, Writer
from writers.sqlgen import clickhouse_column_type

logger = logging.getLogger(__name__)


class ClickHouseWriter(Writer):
    def __init__(self):
        self.client = None
        self._schema_ready = set()

    def _connect(self):
        if self.client is None:
            import clickhouse_connect  # lazy import
            # Create the target DB first via a connection NOT bound to it — you
            # can't connect to a database to create that same database.
            bootstrap = clickhouse_connect.get_client(
                host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT,
                username=CLICKHOUSE_USER, password=CLICKHOUSE_PASSWORD,
            )
            bootstrap.command(f"CREATE DATABASE IF NOT EXISTS {CLICKHOUSE_DB}")
            bootstrap.close()
            self.client = clickhouse_connect.get_client(
                host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT,
                username=CLICKHOUSE_USER, password=CLICKHOUSE_PASSWORD,
                database=CLICKHOUSE_DB,
            )
        return self.client

    def _ddl(self, ds: Dataset) -> str:
        cols = [f"    {c} {clickhouse_column_type(ds, c)}" for c in ds.columns]
        cols.append("    created_at DateTime DEFAULT now()")
        order_by = ", ".join(ds.unique_key)
        body = ",\n".join(cols)
        return (
            f"CREATE TABLE IF NOT EXISTS {ds.name} (\n{body}\n) "
            f"ENGINE = ReplacingMergeTree(created_at) "
            f"ORDER BY ({order_by}) "
            f"PARTITION BY toYYYYMM({ds.date_col})"
        )

    def init_schema(self, ds: Dataset) -> None:
        client = self._connect()   # ensures the database exists
        client.command(self._ddl(ds))
        self._schema_ready.add(ds.name)

    def _coerce(self, ds: Dataset, row: tuple) -> list:
        """Coerce parser values to what the ClickHouse driver expects.

        Parsers emit dates/datetimes as strings (fine for MySQL/Postgres), but
        the ClickHouse client needs real date/datetime objects for Date/DateTime
        columns. String columns also reject NULL, so nullable text/varchar -> ''.
        """
        out = []
        for col, val in zip(ds.columns, row):
            if col == ds.date_col:
                val = self._to_date(val)
            elif col in ds.datetime_cols:
                val = self._to_datetime(val)
            elif val is None:
                if col in ds.text_cols or clickhouse_column_type(ds, col).startswith("String"):
                    val = ""
                elif col in ds.int_cols or col in ds.bool_cols:
                    val = 0
                elif col in ds.float_cols:
                    val = 0.0
            elif col in ds.bool_cols:
                val = int(bool(val))
            out.append(val)
        return out

    @staticmethod
    def _to_date(val):
        if val is None or val == "":
            return date(1970, 1, 1)   # ClickHouse Date is non-nullable; epoch = "unknown"
        if isinstance(val, date) and not isinstance(val, datetime):
            return val
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()

    @staticmethod
    def _to_datetime(val):
        if val is None or val == "":
            return datetime(1970, 1, 1)
        if isinstance(val, datetime):
            return val
        s = str(val)
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return datetime(1970, 1, 1)

    def write(self, ds: Dataset, rows: list[tuple]) -> int:
        if not rows:
            return 0
        if ds.name not in self._schema_ready:
            self.init_schema(ds)
        client = self._connect()
        data = [self._coerce(ds, r) for r in rows]
        client.insert(ds.name, data, column_names=ds.columns)
        logger.info(f"[clickhouse] inserted {len(data)} rows into {ds.name}")
        return len(data)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
