from sqlmodel import Session, select

from app.agents.database.models import SalesProduct
from app.core.database import app_engine


DEFAULT_PRODUCT = {
    "sku": "ERHA-ACSBP-60G",
    "name": "ERHA Acneact Acne Cleanser Scrub Beta Plus (ACSBP)",
    "price_idr": 110900,
    "pack_size": "60 g",
    "expiry": "30 Januari 2028",
    "bpom": "NA18201202832",
    "halal_mui": "00150086800118",
    "stock_status": "ready",
    "benefits": (
        "Membantu menghambat bakteri penyebab jerawat (uji in-vitro), "
        "mengurangi minyak berlebih, membersihkan pori, dan mengangkat sel kulit mati."
    ),
    "usage_instructions": (
        "Basahi wajah, aplikasikan dan pijat lembut, bilas sampai bersih, "
        "gunakan 2-3 kali sehari."
    ),
    "complaint_policy": (
        "Komplain wajib video unboxing tanpa putus. "
        "Tanpa video unboxing, komplain tidak diproses."
    ),
    "testimony_1": (
        "Amanda: cocok, calming, bantu redakan jerawat meradang."
    ),
    "testimony_2": (
        "Silmi: repurchase sejak 2023, cocok untuk acne-prone."
    ),
}


def ensure_default_sales_product() -> None:
    with Session(app_engine) as session:
        existing = session.exec(
            select(SalesProduct).where(SalesProduct.sku == DEFAULT_PRODUCT["sku"])
        ).first()
        if existing:
            return
        session.add(SalesProduct(**DEFAULT_PRODUCT))
        session.commit()


def get_primary_product() -> SalesProduct | None:
    with Session(app_engine) as session:
        return session.exec(select(SalesProduct).order_by(SalesProduct.id.asc())).first()
