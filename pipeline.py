from vision_extractor import extract_from_image
from validator import validate_all, RuleResult, Severity
from auditor import generate_audit_opinion  

def _build_error_report(
    rule_name: str,
    message: str,
    severity: Severity = Severity.ERROR,
    is_system_error: bool = False,
) -> dict:
    """
    构造一个"处理失败"的统一返回结构。
    """
    result = RuleResult(
        rule_name=rule_name,
        passed=False,
        severity=severity,
        message=message,
    )
    if is_system_error:
        opinion = f"处理失败：{message}。请稍后重试。"
    else:
        opinion = f"处理失败：{message}。请确认上传的是清晰的发票图片。"
    return {
        'fields': {},
        'results': [result],
        'opinion': opinion,
        'has_error': severity == Severity.ERROR,
        'has_warning': severity == Severity.WARNING,
    }

def process_invoice(image_path: str, seen_set: set, history_set: set) -> dict:
    """
    处理单张发票图片的完整流水线：
    1. 视觉提取 → 2. 规则校验 → 3. 审计建议

    每一步都有异常兜底，确保不会因单张图片的问题导致整体崩溃。
    """

    # ===== 第一步：视觉提取（带异常兜底） =====
    try:
        fields = extract_from_image(image_path)
    except Exception as e:
        return _build_error_report(
            "文件读取",
            f"读取图片时发生未知错误：{str(e)}",
        )

    # 检查 _parse_error 标志
    if fields.get("_parse_error"):
        error_type = fields.get("_error_type", "unknown")
        raw_msg = fields.get("_raw", "未知错误")
        
        # 根据错误类型给出更友好的提示
        error_messages = {
            "invalid_image": f"无法识别为有效的图片文件，请确认上传的是 JPG/PNG 格式的发票图片。原始错误：{raw_msg}",
            "image_processing": f"图片处理失败：{raw_msg}",
            "file_read": f"文件读取失败：{raw_msg}",
            "api_timeout": "发票识别服务响应超时，请稍后重试。",
            "api_connection": "无法连接到发票识别服务，请检查网络连接。",
            "api_status": f"发票识别服务异常：{raw_msg}",
            "api_response": f"发票识别服务返回了异常数据：{raw_msg}",
            "json_parse": "发票识别结果无法解析，可能是图片不清晰或不是标准发票格式。",
        }
        friendly_msg = error_messages.get(error_type, raw_msg)
        is_system = error_type in ("api_timeout", "api_connection", "api_status", "api_response")
        return _build_error_report(
            "发票识别",
            friendly_msg,
            is_system_error = is_system,
        )

    # 检查是否不像发票
    if fields.get("_not_invoice"):
        return _build_error_report(
            "发票识别",
            "上传的图片不像是一张发票（关键字段缺失过多），请确认上传的是发票图片。",
            severity=Severity.WARNING,
        )
    # ===== 1.5步：QR码解码与注入 =====
    try:
        from qr_decoder import decode_qr_from_image
        qr_fields = decode_qr_from_image(image_path)
        if qr_fields:
            fields["_qr_fields"] = qr_fields
    except Exception:
        pass  # QR解码失败不影响主流程
        # ===== 第二步：规则校验 =====
        try:
            results = validate_all(fields, seen_set, history_set)
        except Exception as e:
            return _build_error_report(
                "规则校验",
                f"规则校验阶段出错：{str(e)}",
            )

    # ===== 第三步：审计建议 =====
    try:
        opinion = generate_audit_opinion(fields, results)
    except Exception as e:
        # 审计建议失败不影响整体，用规则结果拼一个摘要
        issues = [r.message for r in results if not r.passed]
        if issues:
            opinion = f"审计建议生成失败，以下为规则异常摘要：{'；'.join(issues)}"
        else:
            opinion = "审计建议生成失败，但所有规则均通过。"
    clean_fields = {k: v for k, v in fields.items() if not k.startswith("_") or k == "_confidence"}
    return {
        'fields': clean_fields,
        'results': results,
        'opinion': opinion,
        'has_error': any(not r.passed and r.severity.name == 'ERROR' for r in results),
        'has_warning': any(not r.passed and r.severity.name == 'WARNING' for r in results),
    }