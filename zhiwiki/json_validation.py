"""共享 JSON 解析规则，确保接入与质量检查一致。"""

import json


def _reject_nonstandard_constant(value):
    """拒绝 Python 默认接受、但不属于 JSON 的特殊数值。"""
    raise ValueError("JSON 包含非标准数值")


def parse_json(text, object_pairs_hook=None):
    """严格解析 JSON；可选回调允许质检检查重复键。"""
    return json.loads(text, parse_constant=_reject_nonstandard_constant,
                      object_pairs_hook=object_pairs_hook)
