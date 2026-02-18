from __future__ import annotations

from typing import Any

from app.core.vectordb.base import BaseVectorDB, VectorMatch, VectorRecord


class QdrantVectorDB(BaseVectorDB):
    def __init__(self, url: str, api_key: str | None = None, collection: str | None = None):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models
        except ImportError as exc:
            raise ImportError(
                "qdrant-client is required for QdrantVectorDB. Install with `pip install qdrant-client`."
            ) from exc

        self._models = models
        self._client = QdrantClient(url=url, api_key=api_key or None)
        self._default_collection = collection

    def _get_collection(self, collection: str | None) -> str:
        if collection:
            return collection
        if self._default_collection:
            return self._default_collection
        raise ValueError("Collection name is required for QdrantVectorDB.")

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        collection_name = self._get_collection(collection)
        points = []
        for record in records:
            payload: dict[str, Any] = dict(record.metadata or {})
            if record.document is not None:
                payload["_document"] = record.document
            points.append(
                self._models.PointStruct(
                    id=record.id,
                    vector=record.vector,
                    payload=payload or None,
                )
            )
        if points:
            self._client.upsert(collection_name=collection_name, points=points)

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        collection_name = self._get_collection(collection)
        qdrant_filter = None
        if filter:
            conditions = [
                self._models.FieldCondition(
                    key=key,
                    match=self._models.MatchValue(value=value),
                )
                for key, value in filter.items()
            ]
            qdrant_filter = self._models.Filter(must=conditions)

        results = self._client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        matches: list[VectorMatch] = []
        for item in results:
            payload = item.payload or {}
            document = payload.pop("_document", None) if isinstance(payload, dict) else None
            matches.append(
                VectorMatch(
                    id=str(item.id),
                    score=float(item.score),
                    metadata=payload if isinstance(payload, dict) else None,
                    document=document,
                )
            )
        return matches

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        collection_name = self._get_collection(collection)
        selector = self._models.PointIdsList(points=ids)
        self._client.delete(collection_name=collection_name, points_selector=selector)
