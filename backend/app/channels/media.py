import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelImage:
    title: str
    image_url: str
    source_url: str


# ---------------------------------------------------------------------------
# Relative path served by FastAPI StaticFiles at /v1/static/resource/
# WhatsApp/Telegram need absolute public URLs — see get_testimony_images().
# ---------------------------------------------------------------------------
_STATIC_PATH_AMANDA = "/v1/static/resource/testimoni_erha_acsbp_amanda.jpeg"
_STATIC_PATH_SILMI = "/v1/static/resource/testimoni_erha_acsbp_silmi.jpg"

TESTIMONY_AMANDA = ChannelImage(
    title="Testimoni @amandabilla98 (Amanda)",
    image_url=_STATIC_PATH_AMANDA,
    source_url="",
)
TESTIMONY_SILMI = ChannelImage(
    title="Testimoni @silmisyauz (Silmi)",
    image_url=_STATIC_PATH_SILMI,
    source_url="",
)

TESTIMONY_IMAGES: list[ChannelImage] = [TESTIMONY_AMANDA, TESTIMONY_SILMI]


_TESTIMONY_SIGNAL_TOKENS = {
    "@amandabilla",
    "@silmisyauz",
    "amandabilla98",
    "silmisyauz",
}


def _absolute_url(relative_path: str, base_url: str) -> str:
    """Turn a relative static path into an absolute URL."""
    base = base_url.rstrip("/")
    return f"{base}{relative_path}"


def get_testimony_images(base_url: str = "") -> list[ChannelImage]:
    """Return all testimony images. If *base_url* is provided the image_url
    is made absolute (needed for WhatsApp / Telegram APIs)."""
    if not base_url:
        return list(TESTIMONY_IMAGES)
    return [
        ChannelImage(
            title=img.title,
            image_url=_absolute_url(img.image_url, base_url),
            source_url=img.source_url,
        )
        for img in TESTIMONY_IMAGES
    ]


def looks_like_testimony_reply(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    return any(token in lowered for token in _TESTIMONY_SIGNAL_TOKENS)


def format_whatsapp_reply_text(base_text: str) -> str:
    """Convert markdown-ish LLM text into WhatsApp-friendly plain formatting."""
    text = str(base_text or "").strip()
    if not text:
        return ""

    # Strip markdown images because channel media is sent via dedicated API calls.
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)\n*", "", text)

    # Convert markdown links to "label (url)".
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        lambda match: f"{match.group(1).strip()} ({match.group(2).strip()})",
        text,
    )

    # Remove heading markers and normalize bullet markers.
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-+*]\s+", "- ", text)

    # Remove markdown table separator rows like: | --- | --- |
    text = re.sub(r"(?m)^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$", "", text)

    # Code fences -> inline quoted lines.
    def _code_fence_to_lines(match: re.Match) -> str:
        block = str(match.group(1) or "").strip("\n")
        if not block:
            return ""
        return "\n".join(f"`{line}`" if line.strip() else "" for line in block.splitlines())

    text = re.sub(r"```[A-Za-z0-9_-]*\n([\s\S]*?)```", _code_fence_to_lines, text)

    # Emphasis normalization for WhatsApp:
    # **bold** -> *bold*, __italic__ -> _italic_, ~~strike~~ -> ~strike~
    text = re.sub(r"\*\*([^\n*][^*]*?)\*\*", r"*\1*", text)
    text = re.sub(r"__([^\n_][^_]*?)__", r"_\1_", text)
    text = re.sub(r"~~([^\n~][^~]*?)~~", r"~\1~", text)

    # Unescape markdown escaped formatting characters.
    text = re.sub(r"\\([*_~`])", r"\1", text)

    # Collapse excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_testimony_reply_text(base_text: str) -> str:
    """Wrap text for WhatsApp/Telegram. Also strips markdown image syntax
    since those channels send images separately via API."""
    clean = str(base_text or "").strip()
    if not clean:
        return ""
    # Strip markdown images: ![alt](url)
    clean = re.sub(r"!\[[^\]]*\]\([^)]+\)\n*", "", clean).strip()
    if clean.lower().startswith("testimoni real pengguna"):
        return clean
    return (
        "Testimoni real pengguna ✨\n\n"
        f"{clean}\n\n"
        "Kalau mau, aku bantu lanjut ke cara pakai paling aman buat kondisi kulit kamu."
    )


def build_testimony_markdown_images() -> str:
    """Return markdown image block for dashboard rendering."""
    lines = []
    for img in TESTIMONY_IMAGES:
        lines.append(f"![{img.title}]({img.image_url})")
    return "\n\n".join(lines)
