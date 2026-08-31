"""OpenSearch / Elasticsearch prompt-log writer.

Both engines speak the same wire API for our needs, and opensearch-py works
against Elasticsearch too, so one writer covers `--backend opensearch` and
`--backend elasticsearch`.

Idempotency: each doc's _id = "<aws_account_id>:<request_id>", so re-ingesting
the same record overwrites rather than duplicates (same guarantee as SQL upsert).

Text fields are ALWAYS indexed here — full-text search on prompt/response is the
whole reason to pick this backend, so --store-text is implied.
"""

import logging

from conf.config import (
    OPENSEARCH_HOST,
    OPENSEARCH_INDEX,
    OPENSEARCH_PASSWORD,
    OPENSEARCH_USER,
    OPENSEARCH_VERIFY_CERTS,
)
from writers.base import PROMPT_LOG_COLUMNS, PromptLogWriter

logger = logging.getLogger(__name__)

# Explicit mapping so numeric/date/keyword/text fields aggregate and search correctly.
INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "aws_account_id": {"type": "keyword"},
            "account_label": {"type": "keyword"},
            "request_id": {"type": "keyword"},
            "user_id": {"type": "keyword"},
            "user_id_normalized": {"type": "keyword"},
            "event_time": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss.SSS||strict_date_optional_time"},
            "event_date": {"type": "date", "format": "yyyy-MM-dd"},
            "model_id": {"type": "keyword"},
            "chat_trigger_type": {"type": "keyword"},
            "prompt_length": {"type": "integer"},
            "user_message_length": {"type": "integer"},
            "response_length": {"type": "integer"},
            "has_code_in_response": {"type": "boolean"},
            "code_reference_count": {"type": "integer"},
            "prompt_text": {"type": "text"},
            "response_text": {"type": "text"},
            "source_file": {"type": "keyword"},
        }
    }
}


class SearchPromptWriter(PromptLogWriter):
    def __init__(self, flavor: str = "opensearch"):
        self.flavor = flavor
        self.client = None
        self.index = OPENSEARCH_INDEX

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

    def init_schema(self) -> None:
        client = self._connect()
        if not client.indices.exists(index=self.index):
            client.indices.create(index=self.index, body=INDEX_MAPPING)
            logger.info(f"[{self.flavor}] created index {self.index}")

    def _to_doc(self, row: tuple) -> dict:
        doc = dict(zip(PROMPT_LOG_COLUMNS, row))
        # Store bool as bool for the boolean mapping; keep everything else as-is.
        doc["has_code_in_response"] = bool(doc.get("has_code_in_response"))
        return doc

    def write(self, rows: list[tuple]) -> int:
        if not rows:
            return 0
        from opensearchpy.helpers import bulk  # lazy import

        client = self._connect()
        actions = []
        for row in rows:
            doc = self._to_doc(row)
            _id = f"{doc['aws_account_id']}:{doc['request_id']}"
            actions.append({"_op_type": "index", "_index": self.index, "_id": _id, "_source": doc})
        success, _ = bulk(client, actions, refresh=False)
        logger.info(f"[{self.flavor}] indexed {success} prompt-log docs into {self.index}")
        return success

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
