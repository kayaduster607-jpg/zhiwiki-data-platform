"""Explicit, deterministic text cleanup; source versions remain in the store."""

import re


def clean_text(text):
    """Normalize line endings and whitespace without rewriting document facts."""
    if not isinstance(text, str):
        raise ValueError("正文必须是字符串")
    # Apply each rule independently so the preview can explain every change.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    trimmed_lines = [line.rstrip(" \t") for line in lines]
    trimmed = "\n".join(trimmed_lines)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", trimmed)
    return {
        "text": cleaned,
        "changed": cleaned != text,
        "changes": {
            "line_endings_changed": normalized != text,
            "trailing_whitespace_lines": sum(a != b for a, b in zip(lines, trimmed_lines)),
            "blank_line_runs_reduced": len(re.findall(r"\n{4,}", trimmed)),
        },
    }
