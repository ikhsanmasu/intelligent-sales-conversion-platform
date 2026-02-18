from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VectorRecord:
    id: str
    vector: list[float]
    metadata: dict[str, Any] | None = None
    document: str | None = None


@dataclass(frozen=True)
class VectorMatch:
    id: str
    score: float
    metadata: dict[str, Any] | None = None
    document: str | None = None


class BaseVectorDB:
    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        raise NotImplementedError

    def query(
        self,
        collection: str,
        vector: list[float],
        top_k: int = 5,
        filter: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        raise NotImplementedError

    def delete(self, collection: str, ids: list[str]) -> None:
        raise NotImplementedError
