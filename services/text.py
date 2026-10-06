"""Pure text utilities: newline-aware chunking for the Telegram message limit."""


def split_message(text: str, limit: int) -> list[str]:
    """Split `text` into chunks on newline boundaries, never splitting a line.

    Every chunk is at most `limit` characters, except a single line longer than
    `limit` which stays intact as its own chunk (so the guarantee is conditional).
    `"\\n".join(chunks) == text` always holds; empty input returns `[""]`.
    """
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        added = len(line) if not current else current_len + 1 + len(line)
        if current and added > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len = added
    if current:
        chunks.append("\n".join(current))
    return chunks
