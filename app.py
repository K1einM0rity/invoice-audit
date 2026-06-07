import streamlit as st
from io import BytesIO
import pandas as pd
from history import load_history, save_history
from pipeline import process_invoice
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
st.title("智能财务审计助手")
st.write("欢迎使用，上传发票图片即可开始审计。")

if 'all_results' not in st.session_state:
    st.session_state.is_processing = False
    st.session_state.all_results = []
    st.session_state.seen_numbers = set()
    st.session_state.upload_key = 0
    st.session_state.history_numbers = load_history()
uploaded_files = st.file_uploader(
    "选择发票图片",
    type=["jpg", "png"],
    accept_multiple_files=True,
    key=f"uploaded_{st.session_state.upload_key}"
)

if uploaded_files:
    for file in uploaded_files:
        st.image(file, caption=file.name, width=300)

    if st.button("🔍 开始审计", disabled=st.session_state.is_processing):
        st.session_state.all_results = []
        st.session_state.seen_numbers = set()
        st.session_state.is_processing = True
        st.rerun()

if st.session_state.is_processing:

    seen_set = st.session_state.seen_numbers
    history_set = st.session_state.history_numbers

    # ⬇ 在主线程预读所有文件，避免子线程碰 Streamlit 对象
    file_cache = {}
    for f in uploaded_files:
        file_cache[f.name] = f.read()

    def process_one(name, data):
        temp_path = f"temp_{name}"
        with open(temp_path, "wb") as f:
            f.write(data)
        report = process_invoice(temp_path, seen_set, history_set)
        report['filename'] = name
        return report

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_one, n, d): n for n, d in file_cache.items()}
        for future in as_completed(futures):
            report = future.result()
            st.session_state.all_results.append(report)

    st.success(f"全部处理完成，总共 {len(uploaded_files)} 张")
    save_history(st.session_state.history_numbers | seen_set)
    st.session_state.history_numbers = st.session_state.history_numbers | seen_set
    st.session_state.is_processing = False
    st.rerun()

if st.session_state.all_results:
    for report in st.session_state.all_results:
        with st.expander(f"{'🔴' if report['has_error'] else '🟡' if report['has_warning'] else '🟢'} {report['filename']}"):
            col_img, col_data = st.columns([1, 1])
            with col_img:
                st.image(f"temp_{report['filename']}", caption=report['filename'])
            with col_data:
                st.subheader("提取字段")
                for k, v in report['fields'].items():
                    st.write(f"**{k}**：{v}")
                st.subheader("校验结果")
                for r in report['results']:
                    if r.passed:
                        st.success(f"✅ {r.rule_name}：{r.message}")
                    elif r.severity.name == "WARNING":
                        st.warning(f"🟡 {r.rule_name}：{r.message}")
                    else:
                        st.error(f"🔴 {r.rule_name}：{r.message}")
                st.subheader("审计建议")
                st.info(report['opinion'])
            

    st.header("📊 统计看板")
    total = len(st.session_state.all_results)
    errors = sum(1 for r in st.session_state.all_results if r['has_error'])
    warnings = sum(1 for r in st.session_state.all_results if r['has_warning'] and not r['has_error'])
    passed = total - errors - warnings
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总处理数", total)
    m2.metric("合规", passed)
    m3.metric("异常", errors)
    m4.metric("警告", warnings)
    total_amount = sum(
        float(str(r['fields'].get('价税合计', 0) or 0))
        for r in st.session_state.all_results
    )
    st.metric("💰 价税合计总额", f"¥{total_amount:,.2f}")

    # Sheet1 数据
    rows = []
    for rep in st.session_state.all_results:
        fld = rep['fields']
        errors = [r.message for r in rep['results'] if not r.passed]
        rows.append({
            "文件名": rep['filename'],
            "发票类型": fld.get('发票类型', ''),
            "发票代码": fld.get('发票代码', ''),
            "发票号码": fld.get('发票号码', ''),
            "开票日期": fld.get('开票日期', ''),
            "购买方": fld.get('购买方名称', ''),
            "购买方税号": fld.get('购买方税号', ''),
            "销售方": fld.get('销售方名称', ''),
            "销售方税号": fld.get('销售方税号', ''),
            "金额": fld.get('金额', ''),
            "税额": fld.get('税额', ''),
            "价税合计": fld.get('价税合计', ''),
            "审计建议": rep['opinion'],
            "校验结论": "异常" if rep['has_error'] else ("警告" if rep['has_warning'] else "合规"),
        })
    
    df = pd.DataFrame(rows)

    # Sheet2 异常明细
    error_rows = []
    for rep in st.session_state.all_results:
        for r in rep['results']:
            if not r.passed:
                error_rows.append({
                    "文件名": rep['filename'],
                    "规则": r.rule_name,
                    "严重程度": "ERROR" if r.severity.name == "ERROR" else "WARNING",
                    "问题描述": r.message,
                })
    df_errors = pd.DataFrame(error_rows)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="审计结果", index=False)
        if not df_errors.empty:
            df_errors.to_excel(writer, sheet_name="异常明细", index=False)

        ws = writer.sheets["审计结果"]
        text_cols = {"购买方", "销售方", "审计建议"}
        for col in ws.columns:
            col_letter = col[0].column_letter
            header = col[0].value
            max_len = max(len(str(cell.value or "")) for cell in col)
            if header in text_cols:
                max_len = max(max_len, 18)
            ws.column_dimensions[col_letter].width = min(max_len + 4, 50)
    st.download_button(
        label="📥 导出 Excel",
        data=output.getvalue(),
        file_name="审计报告.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    if st.button("🔄 重置"):
        st.session_state.all_results = []
        st.session_state.seen_numbers = set()
        st.session_state.upload_key += 1
        for f in os.listdir():
            if f.startswith("temp_") and os.path.isfile(f):
                os.remove(f)