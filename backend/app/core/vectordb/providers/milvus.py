from __future__ import annotations

from typing import Any

from app.core.vectordb.base import BaseVectorDB, VectorMatch, VectorRecord


class MilvusVectorDB(BaseVectorDB):
    def __init__(self, url: str, collection: str):
        try:
            from pymilvus import Collection, connections
        except ImportError as exc:
            raise ImportError(
                "pymilvus is required for MilvusVectorDB. Install with `pip install pymilvus`."
            ) from exc

        if not url:
            raise ValueError("VECTORDB_URL is required for Milvus provider.")
        if not collection:
            raise ValueError("VECTORDB_COLLECTION is required for Milvus provider.")

        self._Collection = Collection
        self._connections = connections
        self._connections.connect(alias="default", uri=url)

        self._collection_name = collection
        self._collection = Collection(collection)

    @staticmethod
    def _build_filter_expr(filter: dict[str, Any] | None) -> str | None:
        if not filter:
            return None
        parts: list[str] = []
        for key, value in filter.items():
            if isinstance(value, str):
                escaped = value.replace('"', '\\"')
                parts.append(f'{key} == "{escaped}"')
            elif isinstance(value, bool):
                parts.append(f"{key} == {'true' if value else 'false'}")
            else:
                parts.append(f"{key} == {value}")
        return " and ".join(parts) if parts else None

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        data = []
        for record in records:
            payload: dict[str, Any] = dict(record.metadata or {})
            if record.document is not None:
                payload["_document"] = record.document
            item = {"id": record.id, "vector": record.vector}
            item.update(payload)
            data.append(item)
        self._collection.upsert(data)
        self._collection.flush()

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        expr = self._build_filter_expr(filter)
        results = self._collection.search(
            data=[vector],
            anns_field="vector",
            param={"metric_type": "IP", "params": {"nprobe": 10}},
            limit=top_k,
            expr=expr,
            output_fields=["metadata", "document", "_document"],
        )

        matches: list[VectorMatch] = []
        hits = results[0] if results else []
        for hit in hits:
            metadata = None
            document = None
            entity = getattr(hit, "entity", None)
            if entity is not None:
                data = None
                if isinstance(entity, dict):
                    data = dict(entity)
                else:
                    try:
                        data = dict(entity)
                    except Exception:
                        try:
                            data = entity.to_dict()
                        except Exception:
                            data = None

                if data:
                    document = data.get("document") or data.get("_document")
                    metadata = data.get("metadata")
                    if metadata is None:
                        data.pop("vector", None)
                        data.pop("id", None)
                        data.pop("document", None)
                        data.pop("_document", None)
                        metadata = data or None

            matches.append(
                VectorMatch(
                    id=str(hit.id),
                    score=float(hit.score),
                    metadata=metadata,
                    document=document,
                )
            )
        return matches

    def delete(self, collection: str, ids: list[str]) -> None:
        if not ids:
            return
        quoted = ", ".join(f'"{item}"' for item in ids)
        expr = f"id in [{quoted}]"
        self._collection.delete(expr=expr)
