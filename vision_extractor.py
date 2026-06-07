import requests
import json
import re
import base64
from config import API, URL
from PIL import Image, UnidentifiedImageError

API_KEY = API
VISION_URL = URL  # 同一个端点，换成多模态模式

PROMPT_VISION = """你是一个财务发票数据提取器。从发票图片中直接提取关键字段。

##输出规则(必须严格遵守)
1.只输出一个纯JSON对象,不要任何解释、问候语、Markdown代码块标记
2.无法确定的字段值填null,严禁编造。
3.金额字段只保留数字和小数点,去除"￥""元""$"等符号。
4.日期统一转换为YYYY-MM-DD格式,无法转换的填null。
5.发票类型只能从以下枚举中选择：增值税专用发票、增值税普通发票、增值税电子普通发票、增值税电子专用发票、数电发票（增值税专用发票）、数电发票（普通发票）、其他发票

##输出格式
每个字段输出为 {"value": 字段值, "confidence": 1~5}，confidence 根据以下标准打分：
5=字体清晰、无遮挡、可直接辨认；4=略有模糊但基本确定；3=有干扰但大概率正确；
2=模糊或部分遮挡、不确定；1=完全看不清或缺失（此时value填null）。
无法确定的字段 value 填 null，严禁编造。
{
"发票类型": {"value": "增值税专用发票", "confidence": 5},
"发票代码": {"value": "123456789012", "confidence": 5},
"发票号码": {"value": "01100190021112345678", "confidence": 5},
"开票日期": {"value": "2024-01-15", "confidence": 4},
"购买方名称": {"value": "XX公司", "confidence": 4},
"购买方税号": {"value": "91110000XXXXXXXXXX", "confidence": 3},
"销售方名称": {"value": "YY公司", "confidence": 5},
"销售方税号": {"value": "91110000YYYYYYYYYY", "confidence": 5},
"金额": {"value": 1000.00, "confidence": 5},
"税额": {"value": 130.00, "confidence": 5},
"价税合计": {"value": 1130.00, "confidence": 5}
}

##你的输出(仅JSON)："""

def _is_likely_invoice(fields: dict) -> bool:
    """
    快速判断提取结果是否像一张发票。
    如果发票号码、发票类型、金额三者全部为 null，大概率不是发票。
    """
    key_fields = [
        fields.get("发票号码"),
        fields.get("发票类型"),
        fields.get("金额"),
        fields.get("价税合计"),
        fields.get("购买方名称"),
        fields.get("销售方名称"),
    ]
    # 至少有两个关键字段有值，才认为可能是发票
    filled = sum(1 for v in key_fields if v is not None)
    return filled >= 4

def _parse_json_safe(content: str) -> dict:
    """带兜底策略的 JSON 解析器"""
    # 策略1：直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 策略2：提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 策略3：提取 `...` 内联代码
    match = re.search(r'`(?:json)?\s*([\s\S]*?)\s*`', content)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 策略4：正则提取第一个 {} 块
    match = re.search(r'\{[\s\S]*\}', content)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None  # 全部失败

def extract_from_image(image_path: str) -> dict:
    """
    从发票图片中提取字段。
    返回的 dict 中 _parse_error=True 表示解析失败，
    _not_invoice=True 表示图片不像发票。
    """

    # ===== 阶段1：打开并验证图片 =====
    try:
        img = Image.open(image_path)
        if img.width > 2000:
            ratio = 2000 / img.width
            new_h = int(img.height * ratio)
            img = img.resize((2000, new_h), Image.LANCZOS)
            img.save(image_path)
    except (UnidentifiedImageError,OSError,IOError)as e:
        return {
            "_parse_error": True,
            "_error_type": "invalid_image",
            "_raw": f"图片文件无法打开或已损坏：{str(e)}",
        }
    except Exception as e:
        return{
            "_parse_error": True,
            "_error_type": "image_processing",
            "_raw": f"图片处理失败：{str(e)}",
        }
    
    # ===== 阶段2：读取并编码 =====
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {
            "_parse_error": True,
            "_error_type": "file_read",
            "_raw": f"读取图片文件失败：{str(e)}",
        }

    # ===== 阶段3：调用 API =====
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "agnes-2.0-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT_VISION},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{image_data}"
                }}
            ]
        }]
    }

    try:
        response = requests.post(VISION_URL, headers=headers, json=body, timeout=60)
    except requests.exceptions.Timeout:
        return {
            "_parse_error": True,
            "_error_type": "api_timeout",
            "_raw": "API 请求超时（60秒），请稍后重试",
        }
    except requests.exceptions.ConnectionError:
        return {
            "_parse_error": True,
            "_error_type": "api_connection",
            "_raw": "无法连接到 API 服务，请检查网络或 API 地址配置",
        }
    except requests.exceptions.RequestException as e:
        return {
            "_parse_error": True,
            "_error_type": "api_request",
            "_raw": f"API 请求异常：{str(e)}",
        }

    if response.status_code != 200:
        return {
            "_parse_error": True,
            "_error_type": "api_status",
            "_raw": f"API 返回异常状态码 {response.status_code}：{response.text[:200]}",
        }

    try:
        data = response.json()
    except json.JSONDecodeError:
        return {
            "_parse_error": True,
            "_error_type": "api_response",
            "_raw": f"API 返回了非 JSON 格式的数据：{response.text[:200]}",
        }

    if 'choices' not in data:
        return {
            "_parse_error": True,
            "_error_type": "api_response",
            "_raw": f"API 响应缺少 choices 字段：{str(data)[:200]}",
        }

    content = data['choices'][0]['message']['content']

    # ===== 阶段4：解析 JSON =====
    fields = _parse_json_safe(content)

    if fields is None:
        return {
            "_parse_error": True,
            "_error_type": "json_parse",
            "_raw": content,
        }
    flattened = {}
    confidences = {}
    for k,v in fields.items():
        if isinstance(v,dict) and "value" in v:
            flattened[k] = v["value"]
            if "confidence" in v:
                confidences[k] = v["confidence"]
        else:
            flattened[k] = v
    flattened["_confidence"] = confidences
    fields = flattened
    # ===== 阶段5：判断是否像发票 =====
    if not _is_likely_invoice(fields):
        fields["_not_invoice"] = True

    return fields