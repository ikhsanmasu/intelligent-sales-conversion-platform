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
        "Amanda (amandabilla98): Oke banget sih buat perawatan jerawat. "
        "Dia tuh lembut, calming, dan ngebantu banget redain jerawat yang lagi meradang. "
        "Pokoknya worth it buat yang lagi nyari facial wash buat acne care!"
    ),
    "testimony_2": (
        "Silmi (silmisyauz): Udah pakai ini dari tahun 2023. "
        "Aku repurchase terus karena emang cocok banget buat kulit acne-prone ku. "
        "Busanya lembut, scrubnya juga halus, jadi nggak bikin iritasi. "
        "Jerawat ku jauh lebih terkontrol sejak pakai ini."
    ),
}


def ensure_default_sales_product() -> None:
    with Session(app_engine) as session:
        existing = session.exec(
            select(SalesProduct).where(SalesProduct.sku == DEFAULT_PRODUCT["sku"])
        ).first()
        if existing:
            # Update existing record with latest data (e.g. full testimonials)
            for key, value in DEFAULT_PRODUCT.items():
                if key != "sku":
                    setattr(existing, key, value)
            session.add(existing)
            session.commit()
            return
        session.add(SalesProduct(**DEFAULT_PRODUCT))
        session.commit()


def get_primary_product() -> SalesProduct | None:
    with Session(app_engine) as session:
        return session.exec(select(SalesProduct).order_by(SalesProduct.id.asc())).first()
