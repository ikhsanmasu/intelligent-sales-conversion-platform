from pydantic import BaseModel


class BillingTotals(BaseModel):
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float


class BillingDailyPoint(BaseModel):
    date: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost_usd: float


class BillingModelBreakdown(BaseModel):
    provider: str
    model: str
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_source: str


class BillingUsageEventItem(BaseModel):
    id: int
    user_id: str
    conversation_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_source: str
    created_at: float


class BillingSummary(BaseModel):
    currency: str
    range_days: int
    generated_at: float
    totals: BillingTotals
    by_model: list[BillingModelBreakdown]
    daily: list[BillingDailyPoint]
    recent: list[BillingUsageEventItem]

