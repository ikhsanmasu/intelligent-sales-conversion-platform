from __future__ import annotations

import math
from typing import Any

from app.core.vectordb.base import BaseVectorDB, VectorMatch, VectorRecord


class MemoryVectorDB(BaseVectorDB):
    def __init__(self, collection: str | None = None):
        self._default_collection = collection or "default"
        self._store: dict[str, dict[str, VectorRecord]] = {}

    def _get_collection(self, collection: str | None) -> str:
        return collection or self._default_collection

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _match_filter(metadata: dict[str, Any] | None, filter: dict[str, Any] | None) -> bool:
        if not filter:
            return True
        if not metadata:
            return False
        for key, value in filter.items():
            if metadata.get(key) != value:
                return False
        return True

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        bucket = self._store.setdefault(self._get_collection(collection), {})
        for record in records:
            bucket[record.id] = record

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        bucket = self._store.get(self._get_collection(collection), {})
        scored: list[VectorMatch] = []
        for record in bucket.values():
            if not self._match_filter(record.metadata, filter):
                continue
            score = self._cosine_similarity(vector, record.vector)
            scored.append(
                VectorMatch(
                    id=record.id,
                    score=score,
                    metadata=record.metadata,
                    document=record.document,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(top_k, 0)]

    def delete(self, collection: str, ids: list[str]) -> None:
        bucket = self._store.get(self._get_collection(collection), {})
        for item_id in ids:
            bucket.pop(item_id, None)
