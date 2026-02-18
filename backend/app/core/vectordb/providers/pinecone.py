from __future__ import annotations

from typing import Any

from app.core.vectordb.base import BaseVectorDB, VectorMatch, VectorRecord


class PineconeVectorDB(BaseVectorDB):
    def __init__(
        self,
        api_key: str,
        index: str,
        namespace: str | None = None,
    ):
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise ImportError(
                "pinecone is required for PineconeVectorDB. Install with `pip install pinecone`."
            ) from exc

        if not index:
            raise ValueError("Index name is required for PineconeVectorDB.")

        self._client = Pinecone(api_key=api_key)
        self._index = self._client.Index(index)
        self._namespace = namespace

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        vectors = []
        for record in records:
            payload: dict[str, Any] = dict(record.metadata or {})
            if record.document is not None:
                payload["_document"] = record.document
            vectors.append((record.id, record.vector, payload or None))

        self._index.upsert(vectors=vectors, namespace=self._namespace)

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        result = self._index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
            namespace=self._namespace,
            filter=filter or None,
        )
        matches: list[VectorMatch] = []
        for item in result.matches or []:
            payload = item.metadata or {}
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
        self._index.delete(ids=ids, namespace=self._namespace)
