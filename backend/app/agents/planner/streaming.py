from collections.abc import Generator

THINK_OPEN_TAG = "<think>"
THINK_CLOSE_TAG = "</think>"


def parse_think_tags(chunks: Generator[str, None, None]) -> Generator[dict, None, None]:
    """Split streamed LLM output into thinking/content events via <think> tags."""
    buffer = ""
    inside_think = False

    open_guard_len = len(THINK_OPEN_TAG) - 1
    close_guard_len = len(THINK_CLOSE_TAG) - 1

    for chunk in chunks:
        buffer += chunk

        while True:
            if not inside_think:
                open_index = buffer.find(THINK_OPEN_TAG)
                if open_index == -1:
                    safe = buffer[:-open_guard_len] if len(buffer) > open_guard_len else ""
                    if safe:
                        yield {"type": "content", "content": safe}
                        buffer = buffer[len(safe):]
                    break

                if open_index > 0:
                    yield {"type": "content", "content": buffer[:open_index]}
                buffer = buffer[open_index + len(THINK_OPEN_TAG):]
                inside_think = True
                continue

            close_index = buffer.find(THINK_CLOSE_TAG)
            if close_index == -1:
                safe = buffer[:-close_guard_len] if len(buffer) > close_guard_len else ""
                if safe:
                    yield {"type": "thinking", "content": safe}
                    buffer = buffer[len(safe):]
                break

            if close_index > 0:
                yield {"type": "thinking", "content": buffer[:close_index]}
            buffer = buffer[close_index + len(THINK_CLOSE_TAG):]
            inside_think = False

    if buffer:
        event_type = "thinking" if inside_think else "content"
        yield {"type": event_type, "content": buffer}
