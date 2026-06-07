import requests
import json
from config import API, URL

API_KEY = API
url = URL

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

PROMPT_ADVICE = """你是一个财务审计助手。根据发票的字段信息和校验结果，生成简洁的审计建议。

###校验结果等级
ERROR：严重问题，发票可能无效，需要立即处理
WARNING：潜在风险，建议人工复核
PASS：该项检查通过，无需关注

###发票字段
{fields_text}

###校验结果
{results_text}

###要求
如果存在ERROR或WARNING，请用3句话以内指出问题、说明风险、给出操作建议。
如果全部通过，只输出"该发票校验通过，未发现明显异常。"

"""

def _format_results(results: list) -> str:
    lines = []
    for r in results:
        if r.passed:
            icon = "✅"
        elif r.severity.name == "WARNING":
            icon = "⚠️"
        else:
            icon = "❌"
        line = f"{icon} {r.rule_name}:{r.message}"
        lines.append(line)
    return "\n".join(lines)

def generate_audit_opinion(fields: dict, results: list) -> str:
    has_issue = False
    for r in results:
        if not r.passed:
            has_issue = True
            break
    if not has_issue:
        return "该发票校验通过，未发现明显异常。"

    fields_text = json.dumps(fields, ensure_ascii=False, indent=2)
    results_text = _format_results(results)
    prompt = PROMPT_ADVICE.format(fields_text=fields_text, results_text=results_text)

    body = {
        "model": "agnes-2.0-flash",
        "messages": [{
            "role": "user",
            "content": prompt,
        }],
    }
    try:
        response = requests.post(url, headers=headers, json=body)
    except requests.exceptions.Timeout:
        issues = [str(r.message) for r in results if not r.passed]
        return f"审计建议生成失败（API超时）。异常摘要：{'；'.join(issues)}"
    except requests.exceptions.ConnectionError:
        issues = [str(r.message) for r in results if not r.passed]
        return f"审计建议生成失败（网络连接异常）。异常摘要：{'；'.join(issues)}"
    except requests.exceptions.RequestException as e:
        issues = [str(r.message) for r in results if not r.passed]
        return f"审计建议生成失败（请求异常：{str(e)}）。异常摘要：{'；'.join(issues)}"
    if response.status_code != 200:
        issues = [str(r.message) for r in results if not r.passed]
        return f"审计建议生成失败（API状态码{response.status_code}）。异常摘要：{'；'.join(issues)}"

    data = response.json()
    
    if 'choices' in data:
        return data['choices'][0]['message']['content']

    issues = [str(r.message) for r in results if not r.passed]
    return f"审计建议生成失败（API异常）。异常摘要：{'；'.join(issues)}"