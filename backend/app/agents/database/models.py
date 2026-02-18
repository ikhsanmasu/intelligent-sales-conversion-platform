from typing import Optional

from sqlmodel import Field, SQLModel


class SalesProduct(SQLModel, table=True):
    __tablename__ = "sales_products"

    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(index=True, sa_column_kwargs={"unique": True})
    name: str = Field(index=True)
    price_idr: int = 0
    pack_size: str = ""
    expiry: str = ""
    bpom: str = ""
    halal_mui: str = ""
    stock_status: str = "ready"
    benefits: str = ""
    usage_instructions: str = ""
    complaint_policy: str = ""
    testimony_1: str = ""
    testimony_2: str = ""
