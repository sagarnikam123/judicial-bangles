"""OpenSearch / Elasticsearch writer — one index per dataset.

opensearch-py works against Elasticsearch too, so one writer covers both
`--backend opensearch` and `--backend elasticsearch`.

Index mapping is generated from the Dataset field lists (numeric/date/keyword/
text) so aggregations and full-text search behave correctly. Idempotency: each
doc's _id is the join of the dataset's unique_key values, so re-ingesting a
record overwrites rather than duplicates (same guarantee as a SQL upsert).

Index name: OPENSEARCH_INDEX_PREFIX + dataset name (e.g. "kiro-kiro_prompt_log").
"""

import logging

from conf.config import (
    OPENSEARCH_HOST,
    OPENSEARCH_INDEX_PREFIX,
    OPENSEARCH_PASSWORD,
    OPENSEARCH_USER,
    OPENSEARCH_VERIFY_CERTS,
)
from writers.base import Dataset, Writer

logger = logging.getLogger(__name__)


def _field_type(ds: Dataset, col: str) -> dict:
    if col in ds.text_cols:
        return {"type": "text"}
    if col in ds.bool_cols:
        return {"type": "boolean"}
    if col in ds.int_cols:
        return {"type": "integer"}
    if col in ds.float_cols:
        return {"type": "double"}
    if col in ds.datetime_cols:
        return {"type": "date",
                "format": "yyyy-MM-dd HH:mm:ss.SSS||strict_date_optional_time"}
    if col == ds.date_col:
        return {"type": "date", "format": "yyyy-MM-dd"}
    return {"type": "keyword"}


class SearchWriter(Writer):
    def __init__(self, flavor: str = "opensearch"):
        self.flavor = flavor
        self.client = None
        self._schema_ready = set()

    def _index(self, ds: Dataset) -> str:
        return f"{OPENSEARCH_INDEX_PREFIX}{ds.name}"

    def _connect(self):
        if self.client is None:
            from opensearchpy import OpenSearch  # lazy import
            self.client = OpenSearch(
                hosts=[OPENSEARCH_HOST],
                http_auth=(OPENSEARCH_USER, OPENSEARCH_PASSWORD),
                verify_certs=OPENSEARCH_VERIFY_CERTS,
                ssl_show_warn=False,
            )
        return self.client

    def init_schema(self, ds: Dataset) -> None:
        client = self._connect()
        index = self._index(ds)
        if not client.indices.exists(index=index):
            mapping = {"mappings": {"properties": {c: _field_type(ds, c) for c in ds.columns}}}
            client.indices.create(index=index, body=mapping)
            logger.info(f"[{self.flavor}] created index {index}")
        self._schema_ready.add(ds.name)

    def _doc_id(self, ds: Dataset, doc: dict) -> str:
        return ":".join(str(doc[k]) for k in ds.unique_key)

    def write(self, ds: Dataset, rows: list[tuple]) -> int:
        if not rows:
            return 0
        if ds.name not in self._schema_ready:
            self.init_schema(ds)
        from opensearchpy.helpers import bulk  # lazy import

        client = self._connect()
        index = self._index(ds)
        actions = []
        for row in rows:
            doc = dict(zip(ds.columns, row))
            for b in ds.bool_cols:
                doc[b] = bool(doc.get(b))
            actions.append({"_op_type": "index", "_index": index,
                            "_id": self._doc_id(ds, doc), "_source": doc})
        success, _ = bulk(client, actions, refresh=False)
        logger.info(f"[{self.flavor}] indexed {success} docs into {index}")
        return success

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
