"""
QR 码解码器 — 从发票图片中提取 QR 码结构化数据，用于与 AI 提取结果交叉验证。
"""
import cv2
import re
from urllib.parse import parse_qs, urlparse

def decode_qr_from_image(image_path: str) -> dict | None:
    """
    从发票图片中检测并解码 QR 码。
    返回解析后的字段 dict，或 None（无 QR 码或解码失败）。
    """
    img = cv2.imread(image_path)
    if img is None:
        return None

    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    if not data or not data.strip():
        return None

    return _parse_qr_data(data.strip())

def _parse_qr_data(raw: str) -> dict | None:
    """
    解析 QR 码原始数据，支持多种常见格式：
    1. 逗号分隔：01,发票代码,发票号码,金额,日期,校验码
    2. URL 查询参数：https://...?fpdm=...&fphm=...
    3. JSON（较新的数电发票可能用）
    """
    import json

    # 格式1：JSON
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # 格式2：URL 查询参数（税务查验平台格式）
    if raw.startswith("http"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        mapped = {}
        # 常见参数名映射
        key_map = {
            "fpdm": "发票代码",
            "fphm": "发票号码",
            "kprq": "开票日期",
            "je": "金额",
            "jym": "校验码",
        }
        for eng, cn in key_map.items():
            if eng in params:
                mapped[cn] = params[eng][0]
        if mapped:
            return mapped

    # 格式3：逗号分隔（传统格式）
    # 常见: 01,发票代码,发票号码,价税合计,开票日期,校验码
    parts = raw.split(",")
    if len(parts) >= 5:
        return {
            "发票代码": parts[1] if len(parts) > 1 else None,
            "发票号码": parts[2] if len(parts) > 2 else None,
            "价税合计": parts[3] if len(parts) > 3 else None,
            "开票日期": parts[4] if len(parts) > 4 else None,
            "_raw_qr": raw,
        }

    return {"_raw_qr": raw}

def cross_validate_qr(ai_fields: dict, qr_fields: dict) -> list[tuple[str, str, str]]:
    """
    比对 AI 提取字段与 QR 码解码字段。
    返回不一致列表：[(字段名, AI值, QR值), ...]
    """
    compare_keys = ["发票代码", "发票号码", "开票日期", "价税合计"]
    mismatches = []

    for key in compare_keys:
        ai_val = _normalize(ai_fields.get(key))
        qr_val = _normalize(qr_fields.get(key))
        if ai_val is None or qr_val is None:
            continue
        if ai_val != qr_val:
            mismatches.append((key, str(ai_val), str(qr_val)))

    return mismatches

def _normalize(val) -> str | None:
    """标准化字段值用于比对"""
    if val is None:
        return None
    return str(val).strip().replace(" ", "").replace("-", "").replace("/", "")