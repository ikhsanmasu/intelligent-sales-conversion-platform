from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.agents.database.models import SalesProduct
from app.agents.database.store import get_primary_product


def _as_currency(value: int) -> str:
    return f"Rp{value:,}".replace(",", ".")


def _rows_for_product(product: SalesProduct) -> list[dict]:
    return [
        {"field": "product", "value": product.name},
        {"field": "price", "value": _as_currency(product.price_idr)},
        {"field": "pack_size", "value": product.pack_size},
        {"field": "expiry", "value": product.expiry},
        {"field": "bpom", "value": product.bpom},
        {"field": "halal_mui", "value": product.halal_mui},
        {"field": "benefits", "value": product.benefits},
        {"field": "usage", "value": product.usage_instructions},
        {"field": "complaint_policy", "value": product.complaint_policy},
        {"field": "testimony_1", "value": product.testimony_1},
        {"field": "testimony_2", "value": product.testimony_2},
    ]


def _render_response(rows: list[dict]) -> str:
    if not rows:
        return "Error: data produk tidak tersedia."

    lines = ["Ringkasan data produk terverifikasi:"]
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

        rows = _rows_for_product(product)
        return AgentResult(
            output=_render_response(rows),
            metadata={
                "intent": "full_context",
                "row_count": len(rows),
                "rows": rows,
                "source": "sales_products",
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        yield {"type": "thinking", "content": "Mengambil data produk dari database...\n"}
        result = self.execute(input_text=input_text, context=context)
        yield {"type": "_result", "data": result}
