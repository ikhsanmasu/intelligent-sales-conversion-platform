from __future__ import annotations

import httpx

from app.core.websearch.base import BaseWebSearch, SearchResult


class TavilySearch(BaseWebSearch):
    def __init__(self, api_key: str, api_url: str | None = None):
        if not api_key:
            raise ValueError("WEB_SEARCH_API_KEY is required for Tavily provider.")
        self._api_key = api_key
        self._api_url = api_url or "https://api.tavily.com/search"

    def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max(num_results, 1),
            "include_answer": False,
            "include_raw_content": False,
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(self._api_url, json=payload)
            response.raise_for_status()
            data = response.json()

        results: list[SearchResult] = []
        for item in data.get("results", []) or []:
            title = str(item.get("title") or "")
            url = str(item.get("url") or "")
            snippet = item.get("content") or item.get("snippet")
            if url:
                results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= num_results:
                break
        return results
