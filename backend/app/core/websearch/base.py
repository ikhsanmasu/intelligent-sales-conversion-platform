from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str | None = None


class BaseWebSearch:
    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError
