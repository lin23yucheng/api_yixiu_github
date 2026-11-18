"""
语义审计记录辅助模块。

业务预期的失败必须在调用端显式标记。本模块不从测试名称或步骤名称推断意图。
"""
import re


_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})|\\U([0-9a-fA-F]{8})")


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def decode_unicode_escapes(value):
    """解码字面量 ``\\uXXXX`` 转义片段，不改动普通文本。"""
    if isinstance(value, dict):
        return {k: decode_unicode_escapes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decode_unicode_escapes(v) for v in value]
    if not isinstance(value, str) or "\\u" not in value and "\\U" not in value:
        return value

    def _replace(match):
        hex_value = match.group(1) or match.group(2)
        try:
            return chr(int(hex_value, 16))
        except Exception:
            return match.group(0)

    return _UNICODE_ESCAPE_RE.sub(_replace, value)


def annotate_semantic_record(record):
    """返回一份规范化副本，附带显式的预期失败标记字段。"""
    annotated = decode_unicode_escapes(dict(record))
    expected = (
        _to_bool(annotated.get("semantic_expected"))
        or _to_bool(annotated.get("expected_failure"))
        or str(annotated.get("semantic_category", "")).strip() == "expected_failure"
    )
    annotated["semantic_expected"] = expected
    annotated["expected_reason"] = (
        annotated.get("expected_reason")
        or annotated.get("semantic_expected_reason")
        or ""
    )
    if expected:
        annotated["semantic_category"] = "expected_failure"
    return annotated


def is_expected_semantic_anomaly(record):
    return bool(annotate_semantic_record(record).get("semantic_expected"))
