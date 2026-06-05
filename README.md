```markdown
# 智能财务审计助手

基于多模态视觉 API + 自研规则引擎的发票自动审计系统。上传发票图片，自动识别11个字段，8条规则校验，生成审计建议，导出Excel。

全程零训练，Python + Streamlit，CPU 即可运行。

## 功能

- 批量上传 — 一次最多20张 JPG/PNG
- 视觉识别 — 多模态模型直接看图提取字段
- 8条规则校验 — 号码格式、税号两层防御、金额验算、日期逻辑、必填项、重复检测、发票代码、交叉验证
- 审计建议 — 自动生成审计意见
- 统计看板 — 合规率、异常数、金额合计
- Excel导出 — 双Sheet（审计结果 + 异常明细），三色条件格式
- 跨批次查重 — 发票号码持久化存储，自动检测历史重复

## 技术架构

```
用户上传发票图片
        ↓
  vision_extractor.py    ← 多模态视觉API，直接看图提取字段
        ↓
  validator.py           ← 自研规则引擎，8条规则链
        ↓
  auditor.py             ← 审计建议生成
        ↓
  app.py (Streamlit)     ← Web界面 + 统计看板 + Excel导出
```

## 快速开始

### 1. 创建环境

```
mamba create -n invoice python=3.11 -y
mamba activate invoice
```

### 2. 安装依赖

```
pip install streamlit pandas openpyxl pillow requests
```

### 3. 配置 API Key

在项目根目录创建 `config.py`：

```python
API = "sk-你的Key"
URL = "你的URL"
```

### 4. 启动

```
streamlit run app.py
```

浏览器访问，上传发票即可。

## 项目结构

```
├── app.py                  # Streamlit主界面
├── pipeline.py             # 流水线入口
├── vision_extractor.py     # 多模态视觉提取
├── validator.py            # 规则引擎（8条规则）
├── auditor.py              # 审计建议生成
├── history.py              # 跨批次查重持久化
├── config.py               # API配置（需自行创建）
└── invoice_history.json    # 历史发票号码记录
```

## 校验规则

| 规则 | 级别 | 说明 |
|------|------|------|
| FR-D01 发票号码格式 | ERROR | 8位（传统）/20位（电子） |
| FR-D02 统一社会信用代码 | ERROR/WARNING | 18位格式 + ISO 7064校验码，两层防御 |
| FR-D03 开票日期逻辑 | ERROR/WARNING | 不超过今天 / 报销期限可配置（默认180天） |
| FR-D04 金额验算 | ERROR | 金额+税额≈价税合计（Decimal精确计算，容差0.01） |
| FR-D05 必填项缺失 | WARNING | 号码/日期/购买方/金额 |
| FR-D06 重复报销 | ERROR | 同批次 + 跨批次历史检测 |
| FR-D07 发票代码格式 | ERROR | 10位/12位纯数字 |
| FR-D08 类型交叉验证 | WARNING | 号码位数 vs 提取类型，代码号码互换检测 |

## 技术栈

Agnes-2.0-Flash / Streamlit / Python 3.11 / requests / pandas / openpyxl / Pillow / Decimal

## 合规声明

- 本项目仅做发票表面信息校验（格式、逻辑）
- 不做真伪查验（需对接税务局接口）
- 校验规则依据 GB/T 32100-2015（现行有效）及国家税务总局公告（截止2026年6月）
- 企业内部报销期限（180天）为可配置默认值，非税法强制
- 测试必须使用模拟发票或网络公开样本
```