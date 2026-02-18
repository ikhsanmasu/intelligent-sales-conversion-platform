import json
import logging
import re
from collections.abc import Generator
from typing import Any

from app.agents.base import AgentResult, BaseAgent
from app.core.llm.base import BaseLLM
from app.core.vectordb import create_vectordb

logger = logging.getLogger(__name__)


class VectorAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)
        self._vectordb = create_vectordb()

    @staticmethod
    def _strip_json_fence(raw_text: str) -> str:
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return raw

    def _parse_instruction(self, raw_text: str) -> dict[str, Any]:
        raw = self._strip_json_fence(raw_text)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON instruction: {exc}") from exc

        if not isinstance(payload, dict):
            raise ValueError("Instruction must be a JSON object.")

        vector = payload.get("vector")
        if not isinstance(vector, list) or not all(isinstance(v, (int, float)) for v in vector):
            raise ValueError("Instruction must include a numeric 'vector' array.")

        top_k = payload.get("top_k", 5)
        if not isinstance(top_k, int) or top_k <= 0:
            top_k = 5

        collection = payload.get("collection") or ""
        if collection is not None and not isinstance(collection, str):
            raise ValueError("'collection' must be a string when provided.")

        filter_payload = payload.get("filter")
        if filter_payload is not None and not isinstance(filter_payload, dict):
            raise ValueError("'filter' must be an object when provided.")

        return {
            "collection": collection,
            "vector": vector,
            "top_k": top_k,
            "filter": filter_payload,
        }

    @staticmethod
    def _format_matches(matches: list[dict[str, Any]]) -> str:
        if not matches:
            return "(no matches)"

        lines = ["id | score | document | metadata", "---|---|---|---"]
        for match in matches:
            doc = match.get("document")
            if isinstance(doc, str) and len(doc) > 160:
                doc = doc[:160].rstrip() + "..."
            metadata = match.get("metadata")
            if metadata is not None:
                try:
                    metadata = json.dumps(metadata, ensure_ascii=True)
                except TypeError:
                    metadata = str(metadata)
            lines.append(
                f"{match.get('id')} | {match.get('score')} | {doc or '-'} | {metadata or '-'}"
            )
        return "\n".join(lines)

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        try:
            instruction = self._parse_instruction(input_text)
        except ValueError as exc:
            return AgentResult(output=f"Error: {exc}", metadata={"error": str(exc)})

        try:
            results = self._vectordb.query(
                collection=instruction["collection"],
                vector=instruction["vector"],
                top_k=instruction["top_k"],
                filter=instruction["filter"],
            )
        except Exception as exc:
            logger.exception("Vector DB query failed")
            return AgentResult(output=f"Error: {exc}", metadata={"error": str(exc)})

        matches = [
            {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata,
                "document": match.document,
            }
            for match in results
        ]
        output = self._format_matches(matches)
        return AgentResult(
            output=output,
            metadata={
                "count": len(matches),
                "collection": instruction["collection"],
                "top_k": instruction["top_k"],
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        yield {"type": "thinking", "content": "Memproses instruksi vector...\n"}
        try:
            instruction = self._parse_instruction(input_text)
        except ValueError as exc:
            yield {"type": "content", "content": f"Error: {exc}"}
            return

        yield {
            "type": "thinking",
            "content": (
                "Menjalankan query vector\n"
                f"Collection: {instruction['collection'] or '-'}\n"
                f"Top K: {instruction['top_k']}\n\n"
            ),
        }

        try:
            results = self._vectordb.query(
                collection=instruction["collection"],
                vector=instruction["vector"],
                top_k=instruction["top_k"],
                filter=instruction["filter"],
            )
        except Exception as exc:
            logger.exception("Vector DB query failed")
            yield {"type": "content", "content": f"Error: {exc}"}
            return

        matches = [
            {
                "id": match.id,
                "score": match.score,
                "metadata": match.metadata,
                "document": match.document,
            }
            for match in results
        ]
        output = self._format_matches(matches)
        result = AgentResult(
            output=output,
            metadata={
                "count": len(matches),
                "collection": instruction["collection"],
                "top_k": instruction["top_k"],
            },
        )
        yield {"type": "_result", "data": result}
