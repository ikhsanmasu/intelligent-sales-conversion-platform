from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.report.api_schemas import ReportPdfRequest, ReportRequest, ReportResponse
from app.agents.report.service import (
    generate_report,
    generate_report_pdf,
    generate_report_stream,
)

router = APIRouter(tags=["Report"], prefix="/v1/report")


@router.post("/generate", response_model=ReportResponse)
async def generate_report_endpoint(request: ReportRequest):
    return generate_report(request=request)


@router.post("/pdf", response_model=ReportResponse)
async def generate_report_pdf_endpoint(request: ReportPdfRequest):
    return generate_report_pdf(request=request)


@router.post("/generate/stream")
async def generate_report_stream_endpoint(request: ReportRequest):
    return StreamingResponse(
        generate_report_stream(request),
        media_type="text/event-stream",
    )
