"""
规则引擎
"""

from enum import Enum
from dataclasses import dataclass
import re
from datetime import datetime,timedelta
from decimal import Decimal, InvalidOperation

DEADLINE_DAY = 180
# 统一社会信用代码校验码权重（ISO 7064 MOD 31-3 / GB/T 32100-2015）
TAX_ID_WEIGHTS = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
TAX_ID_CHARS = '0123456789ABCDEFGHJKLMNPQRTUWXY'

def _calc_tax_id_check_digit(first_17: str) -> str:
    """计算统一社会信用代码第18位校验码"""
    char_to_num = {c: i for i, c in enumerate(TAX_ID_CHARS)}
    total = sum(char_to_num[c] * w for c, w in zip(first_17, TAX_ID_WEIGHTS))
    return TAX_ID_CHARS[(31 - (total % 31)) % 31]

class Severity(Enum):
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class RuleResult:
    rule_name:str
    passed:bool
    severity:Severity
    message:str

#FR-D01
def check_invoice_number(fields:dict) ->RuleResult:
    number = fields.get("发票号码")
    if not number:
        return RuleResult(
            rule_name="发票号码格式",
            passed=False,
            severity=Severity.ERROR,
            message="发票号码缺失，无法校验"
        )
    number = str(number)
    if not re.match(r'^\d{8}$|^\d{20}$',number):
        return RuleResult(
            rule_name="发票号码格式",
            passed=False,
            severity=Severity.ERROR,
            message=f"发票号码'{number}'格式不正确，要求8位（传统发票）或20位（数电发票）数字"
        )
    return RuleResult(
        rule_name="发票号码格式",
        passed=True,
        severity=Severity.PASS,
        message="发票号码格式正确"
    )

#FR-D02
def check_tax_id(fields:dict)->RuleResult:
    tax_id = fields.get("购买方税号")
    if not tax_id:
        return RuleResult(
            rule_name="统一社会信用代码",
            passed=False,
            severity=Severity.WARNING,
            message="购买方税号缺失，可能为非企业发票（如个人抬头发票）"
        )
    tax_id = str(tax_id).strip().upper()
    if not re.match(r'^[0-9A-HJ-NPQRTUWXY]{18}$',tax_id):
        return RuleResult(
            rule_name="统一社会信用代码",
            passed=False,
            severity=Severity.ERROR,
            message=f"购买方税号'{tax_id}'格式不正确，应为18位数字和大写字母（不含I/O/Z/S/V）"
        )
    # 第二层：校验码验证（WARNING）
    expected = _calc_tax_id_check_digit(tax_id[:17])
    if tax_id[17] != expected:
        return RuleResult(
            rule_name="统一社会信用代码",
            passed=False,
            severity=Severity.WARNING,
            message=f"购买方税号校验码不匹配：期望{expected}，实际{tax_id[17]}，可能为识别错误"
        )
    return RuleResult(
        rule_name="统一社会信用代码",
        passed=True,
        severity=Severity.PASS,
        message="购买方税号格式正确"
    )


#FR-D03
def check_date_logic(fields: dict) -> RuleResult:
    date_str = fields.get("开票日期")
    if not date_str:
        return RuleResult(
            rule_name="开票日期逻辑",
            passed=False,
            severity=Severity.WARNING,
            message="开票日期缺失，无法校验日期有效性"
        )
    date_str = str(date_str).strip()
    try:
        invoice_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return RuleResult(
            rule_name="开票日期逻辑",
            passed=False,
            severity=Severity.ERROR,
            message=f"开票日期'{date_str}'无法解析，要求YYYY-MM-DD格式"
        )
    now = datetime.now()
    deadline = now - timedelta(days=DEADLINE_DAY)
    if invoice_date > now:
        return RuleResult(
            rule_name="开票日期逻辑",
            passed=False,
            severity=Severity.ERROR,
            message=f"开票日期'{date_str}'晚于当前日期，可能为错误数据"
        )
    if invoice_date < deadline:
        return RuleResult(
            rule_name="开票日期逻辑",
            passed=False,
            severity=Severity.WARNING,
            message=f"开票日期'{date_str}'超过{DEADLINE_DAY}天，可能超出企业报销期限"
        )
    return RuleResult(
        rule_name="开票日期逻辑",
        passed=True,
        severity=Severity.PASS,
        message="开票日期在合理范围内"
    )


#FR-D04
def check_amount_math(fields: dict) -> RuleResult:
    amount = fields.get("金额")
    tax = fields.get("税额")
    total = fields.get("价税合计")
    if amount is None or tax is None or total is None:
        return RuleResult(
            rule_name="金额验算",
            passed=False,
            severity=Severity.WARNING,
            message="金额、税额或价税合计缺失，跳过金额验算"
        )
    

    try:
        amount = Decimal(str(amount))
        tax = Decimal(str(tax))
        total = Decimal(str(total))
    except InvalidOperation:
        return RuleResult(
            rule_name="金额验算",
            passed=False,
            severity=Severity.ERROR,
            message="金额字段包含非数字字符，无法验算"
        )


    diff = abs(amount + tax - total)
    if diff > Decimal("0.01"):
        return RuleResult(
            rule_name="金额验算",
            passed=False,
            severity=Severity.ERROR,
            message=f"金额验算失败：{amount} + {tax} = {amount + tax}，与价税合计 {total} 相差 {diff:.2f} 元"
        )
    return RuleResult(
        rule_name="金额验算",
        passed=True,
        severity=Severity.PASS,
        message="金额验算通过"
    )

#FR-D05

def check_required_fields(fields:dict) ->RuleResult:
    required = ["发票号码","开票日期","购买方名称","金额"]
    missing = []
    for field in required:
        if fields.get(field) is None:
            missing.append(field)
    if missing:
        return RuleResult(
            rule_name="必填项缺失",
            passed=False,
            severity=Severity.WARNING,
            message=f"缺失必填字段：{'、'.join(missing)}"
            )
    return RuleResult(
        rule_name="必填项缺失",
        passed=True,
        severity=Severity.PASS,
         message="必填字段完整"
        )


#FR-D06
def get_dedup_key(fields:dict) ->str:
    code = fields.get("发票代码")
    number = fields.get("发票号码")
    if not number:
        return None
    if code and code != "null":
        return f"{code}--{number}"
    return str(number)

def check_duplicate(fields:dict,seen_set:set,history_set:set)->RuleResult:
    key = get_dedup_key(fields)
    if not key:
        return RuleResult(
            rule_name="重复报销检测",
            passed=False,
            severity=Severity.WARNING,
            message="发票号码或代码缺失，无法进行重复检测"
        )
    if key in history_set:
        return RuleResult(
            rule_name="重复报销检测",
            passed=False,
            severity=Severity.ERROR,
            message=f"发票'{key}'在历史记录中已存在，疑似重复报销"
        )
    if key in seen_set:
        return RuleResult(
            rule_name="重复报销检测",
            passed=False,
            severity=Severity.ERROR,
            message=f"发票'{key}'在本次批量中重复出现"
        )
    seen_set.add(key)
    return RuleResult(
        rule_name="重复报销检测",
        passed=True,
        severity=Severity.PASS,
        message="未检测到重复"
    )

#FR-D07
def check_invoice_code(fields:dict)->RuleResult:
    code = fields.get("发票代码")
    if not code:
        return RuleResult(
            rule_name="发票代码格式",
            passed=True,
            severity=Severity.PASS,
            message="发票代码为空（数电发票无代码），跳过校验"
        )
    code = str(code).strip()
    if not re.match(r'^\d{10}$|^0\d{11}$',code):
        return RuleResult(
            rule_name="发票代码格式",
            passed=False,
            severity=Severity.ERROR,
            message=f"发票代码'{code}'格式不正确，应为12位数字且首位为0,老发票应为10位数字"
        )
    return RuleResult(
        rule_name="发票代码格式",
        passed=True,
        severity=Severity.PASS,
        message="发票代码格式正确"
    )

#FR-D08
def cross_validate_invoice_type(fields: dict) -> RuleResult:
    number = fields.get("发票号码")
    llm_type = fields.get("发票类型")
    
    if not llm_type:
        return RuleResult(
            rule_name="发票类型交叉验证",
            passed=False,
            severity=Severity.WARNING,
            message="发票类型缺失，未能识别发票类型，建议人工补充"
        )
    
    if not number:
        return RuleResult(
            rule_name="发票类型交叉验证",
            passed=True,
            severity=Severity.PASS,
            message="发票号码缺失，跳过类型交叉验证"
        )
    
    # 代码和号码互换检测
    code = fields.get("发票代码")
    if code:
        num_str = str(number)
        code_str = str(code)
        if len(num_str) >= 10 and len(code_str) <= 8:
            return RuleResult(
                rule_name="发票类型交叉验证",
                passed=False,
                severity=Severity.WARNING,
                message=f"发票代码'{code}'和发票号码'{number}'可能互换，建议人工核对"
            )
    
    # 20位号码 → 电子发票，不做类型纠错
    return RuleResult(
        rule_name="发票类型交叉验证",
        passed=True,
        severity=Severity.PASS,
        message="发票类型与号码长度一致"
    )

#规则链汇总函数

def validate_all(fields:dict,seen_set:set,history_set:set)->list:
    results = []
    results.append(check_invoice_number(fields))
    results.append(check_tax_id(fields))
    results.append(check_date_logic(fields))
    results.append(check_amount_math(fields))
    results.append(check_required_fields(fields))
    results.append(check_duplicate(fields, seen_set, history_set))
    results.append(check_invoice_code(fields))
    results.append(cross_validate_invoice_type(fields))
    return results
