import math
import re
from collections import Counter
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.agents.database.store import get_primary_product
from app.agents.vector.store import VectorDocument


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _tf(tokens: list[str]) -> Counter:
    return Counter(tokens)


def _cosine_similarity(left: Counter, right: Counter) -> float:
    if not left or not right:
        return 0.0

    dot = 0.0
    for term, value in left.items():
        dot += float(value) * float(right.get(term, 0))

    left_norm = math.sqrt(sum(float(v * v) for v in left.values()))
    right_norm = math.sqrt(sum(float(v * v) for v in right.values()))
    denom = left_norm * right_norm
    if denom <= 0:
        return 0.0
    return dot / denom


def _build_documents() -> list[VectorDocument]:
    product = get_primary_product()
    if product is None:
        return []

    documents = [
        VectorDocument(
            doc_id="product.overview",
            text=(
                f"Produk: {product.name}. Harga: Rp{product.price_idr:,}. "
                f"Kemasan: {product.pack_size}. "
                f"BPOM: {product.bpom}. Halal: {product.halal_mui}."
            ).replace(",", "."),
            metadata={"type": "overview"},
        ),
        VectorDocument(
            doc_id="product.benefits",
            text=product.benefits,
            metadata={"type": "benefits"},
        ),
        VectorDocument(
            doc_id="product.usage",
            text=product.usage_instructions,
            metadata={"type": "usage"},
        ),
        VectorDocument(
            doc_id="product.policy",
            text=product.complaint_policy,
            metadata={"type": "policy"},
        ),
        VectorDocument(
            doc_id="product.testimony.1",
            text=product.testimony_1,
            metadata={"type": "testimony"},
        ),
        VectorDocument(
            doc_id="product.testimony.2",
            text=product.testimony_2,
            metadata={"type": "testimony"},
        ),
    ]

    return [doc for doc in documents if doc.text and doc.text.strip()]


def _format_matches(matches: list[dict]) -> str:
    if not matches:
        return "(no matches)"

    lines = ["Dokumen relevan:"]
    for item in matches:
        lines.append(
            f"- [{item['doc_id']}] (score={item['score']:.3f}) {item['text']}"
        )
    return "\n".join(lines)


class VectorAgent(BaseAgent):
    def __init__(self):
        super().__init__(llm=None)

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        context = context or {}
        top_k = int(context.get("top_k") or 3)
        top_k = max(1, min(top_k, 8))

        docs = _build_documents()
        if not docs:
            return AgentResult(
                output="Error: knowledge vector belum tersedia.",
                metadata={"error": "empty_knowledge"},
            )

        query_tf = _tf(_tokenize(input_text))
        ranked: list[dict] = []

        for doc in docs:
            score = _cosine_similarity(query_tf, _tf(_tokenize(doc.text)))
            ranked.append(
                {
                    "doc_id": doc.doc_id,
                    "score": float(score),
                    "text": doc.text,
                    "metadata": doc.metadata,
                }
            )

        ranked.sort(key=lambda item: item["score"], reverse=True)
        selected = [item for item in ranked[:top_k] if item["score"] > 0]
        if not selected:
            selected = ranked[:top_k]

        return AgentResult(
            output=_format_matches(selected),
            metadata={
                "count": len(selected),
                "top_k": top_k,
                "matches": selected,
                "source": "sales_knowledge",
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        yield {"type": "thinking", "content": "Mencari dokumen paling relevan di knowledge vector...\n"}
        result = self.execute(input_text=input_text, context=context)
        yield {"type": "_result", "data": result}
