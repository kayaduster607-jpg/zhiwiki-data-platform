"""Version-bound quality hints for team imports and subsequent corrections."""

from ..data_quality import inspect_document


def assess_page(filename, text, pdf=False, corrected=False):
    """Recompute hints from the current page text without changing its content."""
    result = {}
    if pdf:
        if not text.strip():
            result["empty"] = True
        elif len(text.strip()) < 40:
            result["low_text"] = True
        if "\ufffd" in text:
            result["missing_glyphs"] = text.count("\ufffd")
    report = inspect_document({"id": "", "title": filename, "source_key": filename, "text": text})
    # An absent field means no warning; it does not certify the document's truth.
    if report["issues"]:
        result["rule_issues"] = report["issues"]
    if corrected:
        result["manually_corrected"] = True
    return result


def summarize_quality(qualities):
    """Count actual warnings; correction history alone is not a quality issue."""
    return {
        "pages": len(qualities),
        "flagged_pages": sum(any(key != "manually_corrected" and bool(value) for key, value in quality.items()) for quality in qualities),
        "empty_pages": sum(bool(q.get("empty")) for q in qualities),
        "missing_glyph_pages": sum(bool(q.get("missing_glyphs")) for q in qualities),
    }
