from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.vectordb.base import BaseVectorDB, VectorMatch, VectorRecord


class ChromaVectorDB(BaseVectorDB):
    def __init__(self, url: str | None = None, collection: str | None = None):
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for ChromaVectorDB. Install with `pip install chromadb`."
            ) from exc

        self._client = None
        if url:
            parsed = urlparse(url)
            if parsed.scheme in {"http", "https"}:
                host = parsed.hostname or "localhost"
                port = parsed.port or 8000
                self._client = chromadb.HttpClient(host=host, port=port)
            else:
                self._client = chromadb.PersistentClient(path=url)
        else:
            self._client = chromadb.Client()

        self._default_collection = collection or "default"

    def _get_collection(self, collection: str | None):
        name = collection or self._default_collection
        return self._client.get_or_create_collection(name=name)

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        col = self._get_collection(collection)
        ids = [record.id for record in records]
        embeddings = [record.vector for record in records]
        metadatas = [record.metadata for record in records]
        documents = [record.document for record in records]
        col.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        col = self._get_collection(collection)
        result = col.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=filter or None,
            include=["metadatas", "documents", "distances"],
        )

        matches: list[VectorMatch] = []
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]

        for idx, item_id in enumerate(ids):
            distance = distances[idx] if idx < len(distances) else None
            score = 1.0 - float(distance) if distance is not None else 0.0
            matches.append(
                VectorMatch(
                    id=str(item_id),
                    score=score,
                    metadata=metadatas[idx] if idx < len(metadatas) else None,
                    document=documents[idx] if idx < len(documents) else None,
                )
            )
        return matches

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        col = self._get_collection(collection)
        col.delete(ids=ids)
