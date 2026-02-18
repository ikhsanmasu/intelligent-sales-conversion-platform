from typing import Literal

from pydantic import BaseModel


class ReportRequest(BaseModel):
    query: str
    format: Literal["markdown", "pdf"] | None = None


class ReportPdfRequest(BaseModel):
    report: dict


class ReportResponse(BaseModel):
    status: str
    report: dict | None = None
    error: str | None = None
