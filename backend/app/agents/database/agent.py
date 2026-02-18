import re
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.agents.database.models import SalesProduct
from app.agents.database.store import get_primary_product

_PRICE_KEYWORDS = {
    "harga",
    "price",
    "berapa",
    "biaya",
    "mahal",
    "murah",
}
_STOCK_KEYWORDS = {
    "stok",
    "stock",
    "ready",
    "tersedia",
    "available",
}
_COMPLIANCE_KEYWORDS = {
    "bpom",
    "halal",
    "exp",
    "expired",
    "kadaluarsa",
    "legal",
}
_USAGE_KEYWORDS = {
    "cara pakai",
    "pemakaian",
    "pakai",
    "gunakan",
    "usage",
}
_BENEFIT_KEYWORDS = {
    "manfaat",
    "fungsi",
    "kegunaan",
    "benefit",
}
_TESTIMONY_KEYWORDS = {
    "testimoni",
    "review",
    "ulasan",
    "bukti",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _as_currency(value: int) -> str:
    return f"Rp{value:,}".replace(",", ".")


def _detect_intent(question: str) -> str:
    normalized = _normalize(question)

    def has_any(words: set[str]) -> bool:
        return any(word in normalized for word in words)

    if has_any(_PRICE_KEYWORDS):
        return "price"
    if has_any(_STOCK_KEYWORDS):
        return "stock"
    if has_any(_COMPLIANCE_KEYWORDS):
        return "compliance"
    if has_any(_USAGE_KEYWORDS):
        return "usage"
    if has_any(_BENEFIT_KEYWORDS):
        return "benefits"
    if has_any(_TESTIMONY_KEYWORDS):
        return "testimony"
    return "overview"


def _rows_for_intent(product: SalesProduct, intent: str) -> list[dict]:
    if intent == "price":
        return [
            {"field": "product", "value": product.name},
            {"field": "price", "value": _as_currency(product.price_idr)},
            {"field": "pack_size", "value": product.pack_size},
        ]

    if intent == "stock":
        return [
            {"field": "product", "value": product.name},
            {"field": "stock_status", "value": product.stock_status},
        ]

    if intent == "compliance":
        return [
            {"field": "bpom", "value": product.bpom},
            {"field": "halal_mui", "value": product.halal_mui},
            {"field": "expiry", "value": product.expiry},
        ]

    if intent == "usage":
        return [
            {"field": "usage", "value": product.usage_instructions},
            {"field": "complaint_policy", "value": product.complaint_policy},
        ]

    if intent == "benefits":
        return [
            {"field": "benefits", "value": product.benefits},
            {"field": "ingredients", "value": "BHA, Sulphur, Biodegradable Sphere Scrub"},
        ]

    if intent == "testimony":
        return [
            {"field": "testimony_1", "value": product.testimony_1},
            {"field": "testimony_2", "value": product.testimony_2},
        ]

    return [
        {"field": "product", "value": product.name},
        {"field": "price", "value": _as_currency(product.price_idr)},
        {"field": "pack_size", "value": product.pack_size},
        {"field": "benefits", "value": product.benefits},
        {"field": "usage", "value": product.usage_instructions},
        {"field": "bpom", "value": product.bpom},
        {"field": "halal_mui", "value": product.halal_mui},
        {"field": "expiry", "value": product.expiry},
    ]


def _render_response(rows: list[dict], intent: str) -> str:
    header = {
        "price": "Info harga terbaru:",
        "stock": "Info stok saat ini:",
        "compliance": "Info legalitas produk:",
        "usage": "Panduan penggunaan:",
        "benefits": "Manfaat utama produk:",
        "testimony": "Ringkasan testimoni:",
        "overview": "Ringkasan data produk:",
    }.get(intent, "Ringkasan data produk:")

    lines = [header]
    for row in rows:
        lines.append(f"- {row['field']}: {row['value']}")
    return "\n".join(lines)


class DatabaseAgent(BaseAgent):
    def __init__(self):
        super().__init__(llm=None)

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        product = get_primary_product()
        if product is None:
            return AgentResult(
                output="Error: data produk belum tersedia di database.",
                metadata={"error": "empty_product_table"},
            )

        intent = _detect_intent(input_text)
        rows = _rows_for_intent(product, intent)
        return AgentResult(
            output=_render_response(rows, intent=intent),
            metadata={
                "intent": intent,
                "row_count": len(rows),
                "rows": rows,
                "source": "sales_products",
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        yield {"type": "thinking", "content": "Mengambil data produk dari database...\n"}
        result = self.execute(input_text=input_text, context=context)
        yield {"type": "_result", "data": result}
