from __future__ import annotations

import httpx

from app.core.websearch.base import BaseWebSearch, SearchResult


class SerperSearch(BaseWebSearch):
    def __init__(self, api_key: str, api_url: str | None = None):
        if not api_key:
            raise ValueError("WEB_SEARCH_API_KEY is required for Serper provider.")
        self._api_key = api_key
        self._api_url = api_url or "https://google.serper.dev/search"

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        payload = {"q": query, "num": max(num_results, 1)}
        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(self._api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        results: list[SearchResult] = []
        for item in data.get("organic", []) or []:
            title = str(item.get("title") or "")
            url = str(item.get("link") or "")
            snippet = item.get("snippet")
            if url:
                results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= num_results:
                break
        return results
