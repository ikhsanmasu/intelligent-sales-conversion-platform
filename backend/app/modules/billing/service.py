import time
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.config import settings
from app.core.database import app_engine
from app.modules.billing.models import LLMUsageEvent

# USD pricing per 1M tokens. Values are estimated and can be overridden in future.
_MODEL_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "openai:gpt-5.2": (1.25, 10.0),
    "openai:gpt-5.2-pro": (15.0, 120.0),
    "openai:gpt-5.2-codex": (1.5, 12.0),
    "openai:gpt-5": (1.25, 10.0),
    "openai:gpt-5-pro": (15.0, 120.0),
    "openai:gpt-5-mini": (0.25, 2.0),
    "openai:gpt-5-nano": (0.05, 0.4),
    "openai:gpt-4.1": (2.0, 8.0),
    "openai:gpt-4.1-mini": (0.4, 1.6),
    "openai:gpt-4.1-nano": (0.1, 0.4),
    "openai:gpt-4o": (5.0, 15.0),
    "openai:gpt-4o-mini": (0.15, 0.6),
    "openai:o3": (10.0, 40.0),
    "openai:o3-mini": (1.1, 4.4),
    "openai:o4-mini": (1.0, 4.0),
    "anthropic:claude-opus-4-1-20250805": (15.0, 75.0),
    "anthropic:claude-opus-4-20250514": (15.0, 75.0),
    "anthropic:claude-sonnet-4-20250514": (3.0, 15.0),
    "anthropic:claude-3-7-sonnet-20250219": (3.0, 15.0),
    "anthropic:claude-3-5-sonnet-20241022": (3.0, 15.0),
    "anthropic:claude-3-5-haiku-20241022": (0.8, 4.0),
    "google:gemini-2.5-pro": (1.25, 5.0),
    "google:gemini-2.5-flash": (0.3, 1.2),
    "google:gemini-2.0-flash": (0.2, 0.8),
    "xai:grok-4": (5.0, 20.0),
    "xai:grok-4-fast-reasoning": (3.0, 12.0),
    "xai:grok-3": (3.0, 12.0),
}

_MODEL_PREFIX_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "openai:gpt-5": (1.25, 10.0),
    "openai:gpt-4.1": (2.0, 8.0),
    "openai:gpt-4o": (5.0, 15.0),
    "openai:o3": (10.0, 40.0),
    "openai:o4-mini": (1.0, 4.0),
    "anthropic:claude-opus": (15.0, 75.0),
    "anthropic:claude-sonnet": (3.0, 15.0),
    "anthropic:claude-haiku": (0.8, 4.0),
    "google:gemini-2.5-pro": (1.25, 5.0),
    "google:gemini-2.5-flash": (0.3, 1.2),
    "google:gemini-2.0-flash": (0.2, 0.8),
    "google:gemini": (0.5, 2.0),
    "xai:grok-4": (5.0, 20.0),
    "xai:grok-3": (3.0, 12.0),
}

_PROVIDER_DEFAULT_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    "openai": (5.0, 15.0),
    "anthropic": (3.0, 15.0),
    "google": (0.5, 2.0),
    "xai": (3.0, 12.0),
}


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_identity(provider: str | None, model: str | None) -> tuple[str, str]:
    p = (provider or settings.CHATBOT_DEFAULT_LLM or "openai").strip().lower()
    m = (model or settings.CHATBOT_DEFAULT_MODEL or "unknown").strip().lower()
    return p, m


def _resolve_pricing(provider: str, model: str) -> tuple[float, float, str]:
    key = f"{provider}:{model}"
    if key in _MODEL_PRICING_PER_1M:
        input_rate, output_rate = _MODEL_PRICING_PER_1M[key]
        return input_rate, output_rate, "exact"

    for prefix in sorted(_MODEL_PREFIX_PRICING_PER_1M, key=len, reverse=True):
        if key.startswith(prefix):
            input_rate, output_rate = _MODEL_PREFIX_PRICING_PER_1M[prefix]
            return input_rate, output_rate, "prefix"

    input_rate, output_rate = _PROVIDER_DEFAULT_PRICING_PER_1M.get(provider, (2.0, 8.0))
    return input_rate, output_rate, "provider_default"


def _usage_event_to_dict(event: LLMUsageEvent) -> dict:
    return {
        "id": int(event.id) if event.id is not None else 0,
        "user_id": event.user_id,
        "conversation_id": event.conversation_id,
        "provider": event.provider,
        "model": event.model,
        "input_tokens": int(event.input_tokens),
        "output_tokens": int(event.output_tokens),
        "total_tokens": int(event.total_tokens),
        "input_cost_usd": float(event.input_cost_usd),
        "output_cost_usd": float(event.output_cost_usd),
        "total_cost_usd": float(event.total_cost_usd),
        "pricing_source": event.pricing_source,
        "created_at": float(event.created_at),
    }


def _extract_usage_payload(
    assistant_metadata: dict | None,
) -> tuple[str, str, int, int, int] | None:
    if not isinstance(assistant_metadata, dict):
        return None

    usage = assistant_metadata.get("usage") or {}
    model_meta = assistant_metadata.get("model") or {}

    provider = model_meta.get("provider") or settings.CHATBOT_DEFAULT_LLM
    model = model_meta.get("name") or settings.CHATBOT_DEFAULT_MODEL
    provider, model = _normalize_identity(provider, model)

    input_tokens = _to_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    output_tokens = _to_int(usage.get("output_tokens") or usage.get("completion_tokens"))
    total_tokens = _to_int(usage.get("total_tokens"))
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
        return None
    if input_tokens <= 0 and total_tokens > 0:
        input_tokens = max(0, total_tokens - max(0, output_tokens))
    if output_tokens <= 0 and total_tokens > 0:
        output_tokens = max(0, total_tokens - max(0, input_tokens))

    return provider, model, input_tokens, output_tokens, total_tokens


def record_usage_event(
    user_id: str,
    conversation_id: str,
    assistant_metadata: dict | None,
    created_at: float | None = None,
) -> bool:
    payload = _extract_usage_payload(assistant_metadata)
    if payload is None:
        return False

    provider, model, input_tokens, output_tokens, total_tokens = payload
    input_rate, output_rate, pricing_source = _resolve_pricing(provider, model)
    input_cost = (input_tokens / 1_000_000.0) * input_rate
    output_cost = (output_tokens / 1_000_000.0) * output_rate
    total_cost = input_cost + output_cost

    with Session(app_engine) as session:
        session.add(
            LLMUsageEvent(
                user_id=user_id,
                conversation_id=conversation_id,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                input_cost_usd=input_cost,
                output_cost_usd=output_cost,
                total_cost_usd=total_cost,
                pricing_source=pricing_source,
                created_at=created_at or time.time(),
            )
        )
        session.commit()
    return True


def list_usage_events(
    user_id: str,
    days: int = 30,
    limit: int = 500,
) -> list[dict]:
    safe_days = max(1, min(int(days), 365))
    safe_limit = max(1, min(int(limit), 2000))
    start_at = time.time() - (safe_days * 86400)

    with Session(app_engine) as session:
        events = session.exec(
            select(LLMUsageEvent)
            .where(LLMUsageEvent.user_id == user_id)
            .where(LLMUsageEvent.created_at >= start_at)
            .order_by(LLMUsageEvent.created_at.desc(), LLMUsageEvent.id.desc())
            .limit(safe_limit)
        ).all()
    return [_usage_event_to_dict(event) for event in events]


def get_billing_summary(
    user_id: str,
    days: int = 30,
    recent_limit: int = 50,
) -> dict:
    safe_days = max(1, min(int(days), 365))
    safe_recent_limit = max(1, min(int(recent_limit), 200))
    start_at = time.time() - (safe_days * 86400)

    with Session(app_engine) as session:
        events = session.exec(
            select(LLMUsageEvent)
            .where(LLMUsageEvent.user_id == user_id)
            .where(LLMUsageEvent.created_at >= start_at)
            .order_by(LLMUsageEvent.created_at.asc(), LLMUsageEvent.id.asc())
        ).all()

    totals = {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "input_cost_usd": 0.0,
        "output_cost_usd": 0.0,
        "total_cost_usd": 0.0,
    }

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=safe_days - 1)
    daily_map: dict[str, dict] = {}
    cursor_date = start_date
    while cursor_date <= end_date:
        key = cursor_date.isoformat()
        daily_map[key] = {
            "date": key,
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
        }
        cursor_date += timedelta(days=1)

    by_model: dict[str, dict] = {}
    recent_items: list[dict] = []

    for event in events:
        item = _usage_event_to_dict(event)
        totals["requests"] += 1
        totals["input_tokens"] += item["input_tokens"]
        totals["output_tokens"] += item["output_tokens"]
        totals["total_tokens"] += item["total_tokens"]
        totals["input_cost_usd"] += item["input_cost_usd"]
        totals["output_cost_usd"] += item["output_cost_usd"]
        totals["total_cost_usd"] += item["total_cost_usd"]

        day_key = datetime.fromtimestamp(item["created_at"], tz=timezone.utc).date().isoformat()
        if day_key in daily_map:
            point = daily_map[day_key]
            point["requests"] += 1
            point["input_tokens"] += item["input_tokens"]
            point["output_tokens"] += item["output_tokens"]
            point["total_tokens"] += item["total_tokens"]
            point["total_cost_usd"] += item["total_cost_usd"]

        model_key = f"{item['provider']}::{item['model']}"
        if model_key not in by_model:
            by_model[model_key] = {
                "provider": item["provider"],
                "model": item["model"],
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_cost_usd": 0.0,
                "output_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "pricing_source": item["pricing_source"],
            }
        row = by_model[model_key]
        row["requests"] += 1
        row["input_tokens"] += item["input_tokens"]
        row["output_tokens"] += item["output_tokens"]
        row["total_tokens"] += item["total_tokens"]
        row["input_cost_usd"] += item["input_cost_usd"]
        row["output_cost_usd"] += item["output_cost_usd"]
        row["total_cost_usd"] += item["total_cost_usd"]

        recent_items.append(item)

    by_model_list = sorted(
        by_model.values(),
        key=lambda entry: (entry["total_cost_usd"], entry["total_tokens"]),
        reverse=True,
    )

    daily_list = [daily_map[key] for key in sorted(daily_map.keys())]
    recent_items = list(reversed(recent_items))[:safe_recent_limit]

    return {
        "currency": "USD",
        "range_days": safe_days,
        "generated_at": time.time(),
        "totals": {
            "requests": int(totals["requests"]),
            "input_tokens": int(totals["input_tokens"]),
            "output_tokens": int(totals["output_tokens"]),
            "total_tokens": int(totals["total_tokens"]),
            "input_cost_usd": _to_float(round(totals["input_cost_usd"], 6)),
            "output_cost_usd": _to_float(round(totals["output_cost_usd"], 6)),
            "total_cost_usd": _to_float(round(totals["total_cost_usd"], 6)),
        },
        "by_model": [
            {
                **row,
                "input_cost_usd": _to_float(round(row["input_cost_usd"], 6)),
                "output_cost_usd": _to_float(round(row["output_cost_usd"], 6)),
                "total_cost_usd": _to_float(round(row["total_cost_usd"], 6)),
            }
            for row in by_model_list
        ],
        "daily": [
            {
                **point,
                "total_cost_usd": _to_float(round(point["total_cost_usd"], 6)),
            }
            for point in daily_list
        ],
        "recent": recent_items,
    }

