import json
import logging
import re
from collections.abc import Generator
from typing import Any

import httpx

from app.agents.base import AgentResult, BaseAgent
from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.core.websearch import create_websearch
from app.core.websearch.base import SearchResult
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)


class BrowserAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)
        self._search = create_websearch()

    @staticmethod
    def _strip_json_fence(raw_text: str) -> str:
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return raw

    @staticmethod
    def _extract_text(html: str) -> str:
        text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _fetch_url(self, url: str) -> str:
        headers = {"User-Agent": settings.WEB_BROWSE_USER_AGENT}
        timeout = settings.WEB_BROWSE_TIMEOUT
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "text" not in content_type and "html" not in content_type:
                return ""
            return response.text

    def _build_sources(self, query: str, max_results: int, max_pages: int) -> list[dict[str, Any]]:
        results = self._search.search(query=query, num_results=max_results)
        sources: list[dict[str, Any]] = []

        for idx, item in enumerate(results):
            if idx >= max_pages:
                break
            content = ""
            try:
                html = self._fetch_url(item.url)
                content = self._extract_text(html) if html else ""
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", item.url, exc)

            sources.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "snippet": item.snippet or "",
                    "content": content[: settings.WEB_BROWSE_MAX_CHARS],
                }
            )

        return sources

    @staticmethod
    def _format_sources_block(sources: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for idx, source in enumerate(sources, start=1):
            blocks.append(
                "\n".join(
                    [
                        f"[{idx}] Title: {source.get('title')}",
                        f"URL: {source.get('url')}",
                        f"Snippet: {source.get('snippet')}",
                        f"Content: {source.get('content')}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    def _summarize(self, question: str, sources: list[dict[str, Any]]) -> str:
        if not sources:
            return "Error: No sources found."

        prompt_sources = self._format_sources_block(sources)
        messages = [
            {"role": "system", "content": resolve_prompt("browser_summarize_system")},
            {
                "role": "user",
                "content": resolve_prompt("browser_summarize_user").format(
                    question=question,
                    sources=prompt_sources,
                ),
            },
        ]
        response = self.llm.generate(messages=messages, config=GenerateConfig(temperature=0.2))
        return response.text

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        question = input_text.strip()
        if not question:
            return AgentResult(output="Error: Empty query.", metadata={"error": "empty query"})

        max_results = settings.WEB_BROWSE_MAX_RESULTS
        max_pages = settings.WEB_BROWSE_MAX_PAGES
        if context:
            max_results = context.get("max_results", max_results)
            max_pages = context.get("max_pages", max_pages)

        try:
            sources = self._build_sources(question, max_results, max_pages)
        except Exception as exc:
            logger.exception("Web search failed")
            return AgentResult(output=f"Error: {exc}", metadata={"error": str(exc)})

        summary = self._summarize(question, sources)
        return AgentResult(
            output=summary,
            metadata={
                "sources": sources,
                "count": len(sources),
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        question = input_text.strip()
        if not question:
            yield {"type": "content", "content": "Error: Empty query."}
            return

        max_results = settings.WEB_BROWSE_MAX_RESULTS
        max_pages = settings.WEB_BROWSE_MAX_PAGES
        if context:
            max_results = context.get("max_results", max_results)
            max_pages = context.get("max_pages", max_pages)

        yield {"type": "thinking", "content": "Mencari di internet...\n"}
        try:
            sources = self._build_sources(question, max_results, max_pages)
        except Exception as exc:
            logger.exception("Web search failed")
            yield {"type": "content", "content": f"Error: {exc}"}
            return

        yield {"type": "thinking", "content": f"Sumber ditemukan: {len(sources)}\n"}
        yield {"type": "thinking", "content": "Menyusun ringkasan...\n"}
        summary = self._summarize(question, sources)
        result = AgentResult(
            output=summary,
            metadata={
                "sources": sources,
                "count": len(sources),
            },
        )
        yield {"type": "_result", "data": result}
