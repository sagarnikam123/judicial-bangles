"""SQL generation from Dataset metadata — the single place SQL dialects differ.

Column types and upsert dialect are derived from the Dataset field lists
(int_cols / float_cols / bool_cols / text_cols / datetime_cols), so schema and
insert SQL can never drift from the row tuple. Adding a column = update the
Dataset, and every SQL backend follows automatically.
"""

from writers.base import Dataset

# Columns that should be VARCHAR-typed with a specific width (all else defaults).
_VARCHAR_WIDTHS = {
    "aws_account_id": 16,
    "account_label": 32,
    "request_id": 64,
    "user_id": 128,
    "user_id_normalized": 128,
    "client_type": 32,
    "model_id": 64,
    "chat_trigger_type": 32,
    "subscription_tier": 32,
    "user_email": 255,
    "profile_id": 255,
    "source_file": 255,
}


def _kind(ds: Dataset, col: str) -> str:
    if col in ds.int_cols:
        return "int"
    if col in ds.float_cols:
        return "float"
    if col in ds.bool_cols:
        return "bool"
    if col in ds.text_cols:
        return "text"
    if col in ds.datetime_cols:
        return "datetime"
    if col == ds.date_col:
        return "date"
    return "varchar"


def mysql_column_type(ds: Dataset, col: str) -> str:
    k = _kind(ds, col)
    return {
        "int": "INT DEFAULT 0",
        "float": "DOUBLE DEFAULT 0",
        "bool": "TINYINT(1) DEFAULT 0",
        "text": "MEDIUMTEXT NULL",
        "datetime": "DATETIME(3) NOT NULL",
        "date": "DATE NOT NULL",
        "varchar": f"VARCHAR({_VARCHAR_WIDTHS.get(col, 255)})",
    }[k]


def postgres_column_type(ds: Dataset, col: str) -> str:
    k = _kind(ds, col)
    return {
        "int": "INTEGER DEFAULT 0",
        "float": "DOUBLE PRECISION DEFAULT 0",
        "bool": "SMALLINT DEFAULT 0",
        "text": "TEXT",
        "datetime": "TIMESTAMP(3) NOT NULL",
        "date": "DATE NOT NULL",
        "varchar": f"VARCHAR({_VARCHAR_WIDTHS.get(col, 255)})",
    }[k]


def clickhouse_column_type(ds: Dataset, col: str) -> str:
    k = _kind(ds, col)
    return {
        "int": "Int64 DEFAULT 0",
        "float": "Float64 DEFAULT 0",
        "bool": "UInt8 DEFAULT 0",
        "text": "String DEFAULT ''",
        "datetime": "DateTime64(3)",
        "date": "Date",
        "varchar": "String DEFAULT ''",
    }[k]


def upsert_sql_mysql(ds: Dataset) -> str:
    cols = ", ".join(ds.columns)
    ph = ", ".join(["%s"] * len(ds.columns))
    updates = ", ".join(
        f"{c} = VALUES({c})" for c in ds.columns if c not in ds.unique_key
    )
    return (
        f"INSERT INTO {ds.name} ({cols}) VALUES ({ph}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )


def upsert_sql_postgres(ds: Dataset) -> str:
    cols = ", ".join(ds.columns)
    ph = ", ".join(["%s"] * len(ds.columns))
    conflict = ", ".join(ds.unique_key)
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in ds.columns if c not in ds.unique_key
    )
    return (
        f"INSERT INTO {ds.name} ({cols}) VALUES ({ph}) "
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    )
