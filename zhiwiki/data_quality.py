"""确定性文档质量提示；只读正文，不代替人工内容审核。"""

from collections import Counter
import csv

from .csv_validation import CsvFieldTooLarge, csv_rows
from .json_validation import parse_json


def _issue(code, severity, message):
    """统一质量提示格式，方便界面与后续规则扩展。"""
    return {"code": code, "severity": severity, "message": message}


def _structured_issues(source_key, text):
    """Describe structural faults without assuming business-specific rules."""
    name = source_key.lower()
    if name.endswith(".json"):
        duplicate_count = 0

        def count_duplicate_keys(pairs):
            """Count repeats inside each object without exposing its keys or values."""
            nonlocal duplicate_count
            counts = Counter(key for key, _ in pairs)
            duplicate_count += sum(count - 1 for count in counts.values() if count > 1)
            return dict(pairs)

        try:
            parse_json(text, object_pairs_hook=count_duplicate_keys)
        except (ValueError, RecursionError):
            return [_issue("invalid_json", "warning", "JSON 结构无效，请检查数据来源。")]
        if duplicate_count:
            return [_issue("duplicate_key", "warning", f"JSON 存在 {duplicate_count} 次重复键，请人工核对。")]
        return []
    if not name.endswith(".csv"):
        return []
    try:
        rows = csv_rows(text)
        header = next(rows, [])
        irregular = sum(1 for row in rows if len(row) != len(header))
    except CsvFieldTooLarge as error:
        return [_issue("csv_field_too_large", "warning", str(error))]
    except csv.Error:
        return [_issue("invalid_csv", "warning", "CSV 解析失败，请检查格式及字段长度限制。")]
    issues = []
    if not header or any(not item.strip() for item in header):
        issues.append(_issue("empty_header", "warning", "CSV 存在空表头，请人工核对。"))
    normalized = [item.strip() for item in header if item.strip()]
    if len(set(normalized)) != len(normalized):
        issues.append(_issue("duplicate_header", "warning", "CSV 存在重复表头，请人工核对。"))
    if irregular:
        issues.append(_issue("inconsistent_columns", "warning", f"有 {irregular} 行字段数与表头不一致。"))
    return issues


def inspect_document(document):
    """针对指定文档版本检查可解释的文本异常。"""
    text = document["text"]
    lines = text.splitlines()
    nonempty = [line.strip() for line in lines if line.strip()]
    issues = []

    if len(text.strip()) < 30:
        issues.append(_issue("short_text", "warning", "正文少于 30 字符，请人工核对资料是否完整。"))
    replacement_count = text.count("\ufffd")
    if replacement_count:
        issues.append(_issue("replacement_character", "warning", f"发现 {replacement_count} 个替换字符，可能存在编码或解析问题。"))
    control_count = sum(ord(char) < 32 and char not in "\n\r\t" for char in text)
    if control_count:
        issues.append(_issue("control_character", "warning", f"发现 {control_count} 个异常控制字符，请核对原文。"))
    repeated = sum(count - 1 for line, count in Counter(nonempty).items() if len(line) >= 10 and count >= 3)
    if repeated:
        issues.append(_issue("repeated_lines", "info", f"存在 {repeated} 行重复内容，请检查是否为重复采集或正常格式。"))

    issues.extend(_structured_issues(document.get("source_key", ""), text))

    return {"document_id": document["id"], "title": document["title"], "issues": issues,
            "stats": {"characters": len(text), "lines": len(lines)}}


def inspect_documents(store, document_ids):
    """按所选 ID 读取版本并生成报告，不写入或修改资料。"""
    documents = [inspect_document(store.get_document(document_id)) for document_id in document_ids]
    return {"documents": documents, "summary": {"total": len(documents),
            "issue_count": sum(len(item["issues"]) for item in documents)}}
