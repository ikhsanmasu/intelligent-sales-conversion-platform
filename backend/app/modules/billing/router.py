from fastapi import APIRouter

from app.modules.billing.schemas import BillingSummary, BillingUsageEventItem
from app.modules.billing.service import get_billing_summary, list_usage_events

router = APIRouter(tags=["Billing"], prefix="/v1/billing")


@router.get("/summary/{user_id}", response_model=BillingSummary)
async def get_summary_endpoint(
    user_id: str,
    days: int = 30,
    recent_limit: int = 50,
):
    return get_billing_summary(user_id=user_id, days=days, recent_limit=recent_limit)


@router.get("/events/{user_id}", response_model=list[BillingUsageEventItem])
async def list_events_endpoint(
    user_id: str,
    days: int = 30,
    limit: int = 200,
):
    return list_usage_events(user_id=user_id, days=days, limit=limit)

