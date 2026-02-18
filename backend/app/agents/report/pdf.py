from __future__ import annotations

import logging
import os
import re

from fpdf import FPDF

logger = logging.getLogger(__name__)

_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?[-]+:?\s*(\|\s*:?[-]+:?\s*)+\|?$")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)")

# ---------------------------------------------------------------------------
# Font resolution — try to find a Unicode-capable TTF on the system.
# ---------------------------------------------------------------------------

_FONT_SEARCH_PATHS = [
    # Windows
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    # Linux / Docker common paths
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]

_FONT_BOLD_MAP = {
    "C:/Windows/Fonts/arial.ttf": "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf": "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/tahoma.ttf": "C:/Windows/Fonts/tahomabd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf": "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
}


def _find_unicode_font() -> tuple[str | None, str | None]:
    """Return (regular_path, bold_path) or (None, None) if no Unicode font found."""
    for path in _FONT_SEARCH_PATHS:
        if os.path.isfile(path):
            bold = _FONT_BOLD_MAP.get(path)
            bold_path = bold if bold and os.path.isfile(bold) else None
            logger.info("Found Unicode font: %s (bold: %s)", path, bold_path or "none")
            return path, bold_path
    logger.warning("No Unicode font found in search paths")
    return None, None


# ---------------------------------------------------------------------------
# Unicode → ASCII fallback map for when Unicode fonts are unavailable.
# Covers common characters LLMs produce that aren't in ISO-8859-1 (latin-1).
# ---------------------------------------------------------------------------

_UNICODE_REPLACEMENTS = {
    "\u2013": "-",       # en-dash  –
    "\u2014": "--",      # em-dash  —
    "\u2018": "'",       # left single quote '
    "\u2019": "'",       # right single quote '
    "\u201c": '"',       # left double quote "
    "\u201d": '"',       # right double quote "
    "\u2026": "...",     # ellipsis …
    "\u2192": "->",      # right arrow →
    "\u2190": "<-",      # left arrow ←
    "\u2265": ">=",      # greater-than-or-equal ≥
    "\u2264": "<=",      # less-than-or-equal ≤
    "\u2260": "!=",      # not equal ≠
    "\u00d7": "x",       # multiplication sign ×
    "\u2022": "-",       # bullet •
    "\u2212": "-",       # minus sign −
    "\u200b": "",        # zero-width space
    "\u00a0": " ",       # non-breaking space
    "\ufeff": "",        # BOM
}


def _sanitize_unicode(text: str) -> str:
    """Replace common Unicode characters with ASCII equivalents."""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        if char in text:
            text = text.replace(char, replacement)
    return text


# ---------------------------------------------------------------------------
# Markdown → structured blocks for PDF rendering
# ---------------------------------------------------------------------------

def _strip_inline_markdown(line: str) -> str:
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
    line = re.sub(r"\*(.*?)\*", r"\1", line)
    line = re.sub(r"_(.*?)_", r"\1", line)
    line = re.sub(r"`(.*?)`", r"\1", line)
    line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
    return line


def _parse_markdown_blocks(markdown: str) -> list[dict]:
    """Parse markdown into structured blocks for rendering.

    Block types: heading, text, table, blank
    """
    blocks: list[dict] = []
    lines = markdown.splitlines()
    i = 0

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        # Code fence — skip
        if stripped.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                blocks.append({"type": "text", "content": lines[i]})
                i += 1
            if i < len(lines):
                i += 1  # skip closing fence
            continue

        # Blank line
        if not stripped:
            blocks.append({"type": "blank"})
            i += 1
            continue

        # Heading
        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            text = _strip_inline_markdown(m.group(2))
            blocks.append({"type": "heading", "level": level, "content": text})
            i += 1
            continue

        # Table block — collect consecutive table lines
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines: list[list[str]] = []
            while i < len(lines):
                s = lines[i].strip()
                if not s.startswith("|") or "|" not in s[1:]:
                    break
                if not _TABLE_SEPARATOR_RE.match(s):
                    cells = [c.strip() for c in s.strip("|").split("|")]
                    table_lines.append(cells)
                i += 1
            if table_lines:
                header = table_lines[0]
                rows = table_lines[1:]
                blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        # Regular text (may contain bold markers)
        text = _strip_inline_markdown(stripped)
        blocks.append({"type": "text", "content": text})
        i += 1

    return blocks


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

_HEADING_SIZES = {1: 16, 2: 13, 3: 11, 4: 10}
_BODY_SIZE = 9.5
_TABLE_FONT_SIZE = 7
_CELL_HEIGHT = 5.5
_TABLE_CELL_HEIGHT = 4.5
_HEADING_MARGIN_TOP = {1: 6, 2: 5, 3: 3, 4: 2}
_HEADING_MARGIN_BOTTOM = {1: 3, 2: 2, 3: 1.5, 4: 1}


def build_report_pdf(report: dict) -> bytes:
    title = str(report.get("title") or "Report")
    period = str(report.get("period") or "")
    content = str(report.get("content") or "")

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    # Try to register a Unicode font
    font_path, bold_path = _find_unicode_font()
    use_unicode = False
    font_family = "Helvetica"

    if font_path:
        try:
            pdf.add_font("UniFont", "", font_path)
            if bold_path:
                pdf.add_font("UniFont", "B", bold_path)
            font_family = "UniFont"
            use_unicode = True
            logger.info("Unicode font loaded successfully: %s", font_path)
        except Exception as exc:
            logger.warning("Failed to load Unicode font %s: %s (type: %s)", font_path, exc, type(exc).__name__)

    def safe(text: str) -> str:
        if use_unicode:
            return text
        # Replace common Unicode chars with ASCII equivalents first,
        # then encode to latin-1 as last resort
        text = _sanitize_unicode(text)
        return text.encode("latin-1", "replace").decode("latin-1")

    pdf.add_page()
    max_width = pdf.w - pdf.l_margin - pdf.r_margin

    # Title
    pdf.set_font(font_family, "B", 16)
    pdf.cell(0, 9, safe(title), ln=True)

    # Period
    if period:
        pdf.set_font(font_family, "", 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, safe(f"Periode: {period}"), ln=True)
        pdf.set_text_color(0, 0, 0)

    # Divider line
    pdf.ln(2)
    y = pdf.get_y()
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(3)

    # Parse and render blocks
    blocks = _parse_markdown_blocks(content)

    for block in blocks:
        btype = block["type"]

        if btype == "blank":
            pdf.ln(2)
            continue

        if btype == "heading":
            level = block["level"]
            size = _HEADING_SIZES.get(level, 10)
            pdf.ln(_HEADING_MARGIN_TOP.get(level, 2))
            pdf.set_font(font_family, "B", size)
            pdf.cell(0, size * 0.5, safe(block["content"]), ln=True)
            pdf.ln(_HEADING_MARGIN_BOTTOM.get(level, 1))
            continue

        if btype == "text":
            pdf.set_font(font_family, "", _BODY_SIZE)
            text = safe(block["content"])
            if not text.strip():
                pdf.ln(2)
                continue
            # Use _write_wrapped for safe text output
            _write_wrapped(pdf, text, max_width, _CELL_HEIGHT)
            continue

        if btype == "table":
            header = block["header"]
            rows = block["rows"]
            if not header:
                continue
            _render_table_safe(pdf, font_family, safe, header, rows, max_width)
            continue

    return bytes(pdf.output())


def _write_wrapped(pdf: FPDF, text: str, max_width: float, line_h: float) -> None:
    """Write text with manual word wrapping — never fails regardless of content."""
    words = text.split(" ")
    current_line = ""

    for word in words:
        if not word:
            continue
        candidate = word if not current_line else f"{current_line} {word}"
        if pdf.get_string_width(candidate) <= max_width:
            current_line = candidate
        else:
            if current_line:
                pdf.cell(0, line_h, current_line, ln=True)
            # If single word is wider than max_width, truncate it
            if pdf.get_string_width(word) > max_width:
                while pdf.get_string_width(word) > max_width and len(word) > 3:
                    word = word[:-1]
                word += "~"
            current_line = word

    if current_line:
        pdf.cell(0, line_h, current_line, ln=True)


# ---------------------------------------------------------------------------
# Table rendering — always safe, never crashes
# ---------------------------------------------------------------------------

def _render_table_safe(
    pdf: FPDF,
    font_family: str,
    safe,
    header: list[str],
    rows: list[list[str]],
    max_width: float,
) -> None:
    """Render a table. Falls back to key-value format if grid doesn't fit."""
    col_count = len(header)

    # Quick check: can we fit as a grid at all?
    # Min usable width per column with 7pt font is about 12mm
    min_needed = col_count * 12
    if min_needed > max_width:
        # Too many columns — render as key-value pairs
        _render_table_as_kv(pdf, font_family, safe, header, rows, max_width)
        return

    # Try grid rendering inside try/except
    try:
        _render_table_grid(pdf, font_family, safe, header, rows, max_width)
    except Exception as exc:
        logger.warning("Grid table render failed (%s), falling back to KV", exc)
        _render_table_as_kv(pdf, font_family, safe, header, rows, max_width)


def _render_table_grid(
    pdf: FPDF,
    font_family: str,
    safe,
    header: list[str],
    rows: list[list[str]],
    max_width: float,
) -> None:
    """Render table as grid with borders. May raise if columns too narrow."""
    col_count = len(header)
    font_size = _TABLE_FONT_SIZE
    cell_h = _TABLE_CELL_HEIGHT

    # Calculate column widths at current font size
    pdf.set_font(font_family, "B", font_size)
    widths = [pdf.get_string_width(h) + 3 for h in header]

    pdf.set_font(font_family, "", font_size)
    for row in rows[:20]:
        for j in range(min(len(row), col_count)):
            cell_w = pdf.get_string_width(row[j]) + 3
            if cell_w > widths[j]:
                widths[j] = cell_w

    # Cap individual columns to 35% of page width
    max_col = max_width * 0.35
    widths = [min(w, max_col) for w in widths]

    # Scale to fit page width
    total = sum(widths)
    if total > max_width:
        scale = max_width / total
        widths = [w * scale for w in widths]
    elif total < max_width * 0.5:
        scale = (max_width * 0.6) / total
        widths = [w * scale for w in widths]

    # Safety: ensure minimum column width
    min_w = min(widths) if widths else 0
    if min_w < 8:
        raise ValueError(f"Column too narrow ({min_w:.1f}mm) for grid render")

    pdf.ln(1)

    # Header row
    pdf.set_font(font_family, "B", font_size)
    pdf.set_fill_color(240, 240, 240)
    for j, cell_text in enumerate(header):
        w = widths[j] if j < len(widths) else widths[-1]
        txt = safe(cell_text)
        # Truncate header if needed
        while pdf.get_string_width(txt) > w - 1.5 and len(txt) > 2:
            txt = txt[:-2] + "~"
        pdf.cell(w, cell_h + 0.5, txt, border=1, fill=True)
    pdf.ln()

    # Data rows
    pdf.set_font(font_family, "", font_size)
    for row_idx, row in enumerate(rows):
        if row_idx % 2 == 1:
            pdf.set_fill_color(248, 248, 248)
            fill = True
        else:
            fill = False

        for j in range(col_count):
            w = widths[j] if j < len(widths) else widths[-1]
            cell_val = safe(row[j]) if j < len(row) else ""
            # Truncate if needed
            while pdf.get_string_width(cell_val) > w - 1.5 and len(cell_val) > 2:
                cell_val = cell_val[:-2] + "~"
            pdf.cell(w, cell_h, cell_val, border=1, fill=fill)
        pdf.ln()

    pdf.ln(2)


def _render_table_as_kv(
    pdf: FPDF,
    font_family: str,
    safe,
    header: list[str],
    rows: list[list[str]],
    max_width: float,
) -> None:
    """Fallback: render wide table as key-value pairs per record.

    This approach uses full-width cells and can never fail.
    """
    pdf.ln(1)

    for row_idx, row in enumerate(rows):
        if row_idx > 0:
            # Light separator
            pdf.set_draw_color(220, 220, 220)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.l_margin + max_width * 0.4, y)
            pdf.ln(1.5)

        # Record header
        pdf.set_font(font_family, "B", 7.5)
        pdf.cell(0, 4.5, safe(f"Record {row_idx + 1}"), ln=True)

        # Key-value pairs
        pdf.set_font(font_family, "", 7)
        for j, col_name in enumerate(header):
            val = row[j] if j < len(row) else "-"
            line_text = safe(f"  {col_name}: {val}")
            # Truncate if absurdly long
            if len(line_text) > 120:
                line_text = line_text[:117] + "..."
            pdf.cell(0, 4, line_text, ln=True)

    pdf.ln(2)
