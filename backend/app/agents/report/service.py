import base64
import json
import re
from collections.abc import Generator

from app.agents.report import create_report_agent
from app.agents.report.api_schemas import ReportPdfRequest, ReportRequest, ReportResponse
from app.agents.report.pdf import build_report_pdf


def _parse_report_output(raw: str) -> tuple[dict | None, str | None]:
    raw = (raw or "").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, "Invalid report payload."
    if isinstance(payload, dict) and payload.get("report"):
        return payload.get("report"), None
    if isinstance(payload, dict) and payload.get("error"):
        return None, str(payload.get("error"))
    return None, "Report payload missing."


def _attach_query(report: dict, query: str) -> dict:
    report.setdefault("query", query)
    return report


def _derive_pdf_filename(filename: str | None) -> str:
    name = filename or "report.pdf"
    if name.lower().endswith(".pdf"):
        return name
    stem = re.sub(r"\.[^.]+$", "", name)
    if not stem:
        stem = "report"
    return f"{stem}.pdf"


def _attach_pdf(report: dict) -> tuple[dict, str | None]:
    try:
        pdf_bytes = build_report_pdf(report)
    except Exception as exc:  # pragma: no cover - defensive
        return report, f"PDF generation failed: {exc}"
    payload = dict(report)
    payload["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
    payload["filename"] = _derive_pdf_filename(report.get("filename"))
    payload["format"] = "pdf"
    return payload, None


def generate_report(request: ReportRequest) -> ReportResponse:
    agent = create_report_agent()
    result = agent.execute(request.query)
    report, error = _parse_report_output(result.output)
    if report:
        report = _attach_query(report, request.query)
        if request.format == "pdf":
            report, pdf_error = _attach_pdf(report)
            if pdf_error:
                error = pdf_error
    status = "success" if report and not error else "error"
    return ReportResponse(status=status, report=report, error=error)


def generate_report_pdf(request: ReportPdfRequest) -> ReportResponse:
    report = request.report or {}
    if not isinstance(report, dict):
        return ReportResponse(status="error", error="Invalid report payload.")
    if not report.get("content"):
        return ReportResponse(status="error", error="Report content is missing.")
    report, error = _attach_pdf(report)
    status = "success" if report and not error else "error"
    return ReportResponse(status=status, report=report, error=error)


def generate_report_stream(request: ReportRequest) -> Generator[str, None, None]:
    agent = create_report_agent()
    report_result = None
    for event in agent.execute_stream(request.query):
        if event.get("type") == "_result":
            report_result = event["data"]
        else:
            yield f"data: {json.dumps(event)}\n\n"

    if report_result is None:
        yield f"data: {json.dumps({'type': 'content', 'content': 'Error: Report agent returned no result.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    yield f"data: {json.dumps({'type': 'content', 'content': report_result.output})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
