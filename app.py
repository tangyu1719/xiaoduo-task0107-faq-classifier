#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse

from task0107_review.task1_service import ServiceConfig, Task1ClassifierService


BASE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASE_DIR / "task1_rules.json"

app = FastAPI(title="Task1 FAQ Classifier")
service = Task1ClassifierService(
    ServiceConfig(
        rules_path=RULES_PATH,
        use_rules=True,
        use_llm_fallback=True,
        llm_only=False,
        max_retries=2,
        batch_max_workers=4,
    )
)

LLM_EDGE_SAMPLES = [
    "尾款会原路退回吗",
    "派件员联系不上我，能晚点再送吗",
    "怎么把现在这个号换成新的联系方式",
    "这件外套上身会不会扎，偏宽松还是修身",
    "售后半天不回我，这也太敷衍了吧",
    "这个型号还有没有更大一点的容量",
]


def render_page(result: Optional[dict] = None, selected_mode: str = "rule_first") -> str:
    result_html = ""
    if result:
        confidence_html = ""
        confidence = result.get('confidence')
        if confidence and confidence.get('is_ambiguous'):
            alt_html = ''.join([f"<li>{item['label']}：{round(item['confidence'] * 100, 1)}%</li>" for item in confidence.get('alternatives', [])])
            confidence_html = f"""
            <div style='margin-top:12px;padding:12px;background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;'>
              <strong>歧义置信度分析</strong>
              <div>第一判断：{confidence['top1']['label']}（{round(confidence['top1']['confidence'] * 100, 1)}%）</div>
              <div>备选项：</div>
              <ul>{alt_html}</ul>
            </div>
            """
        result_html = f"""
        <div class='panel'>
          <h3>分类结果</h3>
          <pre>{json.dumps(result, ensure_ascii=False, indent=2)}</pre>
          {confidence_html}
        </div>
        """
    return f"""
    <html>
    <head>
      <meta charset='utf-8' />
      <title>Task1 FAQ 分类节点</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; background: #f5f7fb; color: #1f2937; }}
        .wrap {{ max-width: 980px; margin: 0 auto; }}
        .panel {{ background: white; border: 1px solid #dbe3ee; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
        textarea {{ width: 100%; min-height: 120px; padding: 12px; }}
        button {{ background: #2563eb; color: white; border: none; padding: 10px 16px; border-radius: 6px; cursor: pointer; }}
        pre {{ white-space: pre-wrap; word-break: break-word; }}
      </style>
    </head>
    <body>
      <div class='wrap'>
        <div class='panel'>
          <h2>Task1 FAQ 分类节点</h2>
          <p>规则优先，LLM 兜底；支持回退、重试、并发批处理。</p>
          <form method='post' action='/classify'>
            <div style='margin-bottom:12px;'>
              <label><input type='radio' name='mode' value='rule_first' {('checked' if selected_mode == 'rule_first' else '')}/> 规则优先</label>
              <label style='margin-left:16px;'><input type='radio' name='mode' value='llm_only' {('checked' if selected_mode == 'llm_only' else '')}/> 仅 LLM</label>
            </div>
            <textarea name='question' placeholder='输入一条客服问题'></textarea>
            <div style='margin-top:12px;'><button type='submit'>分类</button></div>
          </form>
        </div>
        <div class='panel'>
          <h3>LLM 边界样例</h3>
          <p>先切到“仅 LLM”，再点下面任一样例自动填入。</p>
          <div style='display:grid; gap:8px;'>
            {''.join([f"<button type='button' onclick=\"fillSample('{sample}')\" style='text-align:left;background:#eef4ff;color:#1d4ed8;border:1px solid #bfdbfe;'> {sample} </button>" for sample in LLM_EDGE_SAMPLES])}
          </div>
        </div>
        {result_html}
      </div>
      <script>
        function fillSample(text) {{
          const area = document.querySelector('textarea[name="question"]');
          area.value = text;
          area.focus();
        }}
      </script>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return render_page()


@app.post("/classify", response_class=HTMLResponse)
async def classify_form(question: str = Form(...), mode: str = Form("rule_first")) -> str:
    result = service.classify_one(question, mode=mode)
    result["question"] = question
    return render_page(result, selected_mode=mode)


@app.post("/api/classify")
async def classify_api(payload: dict) -> JSONResponse:
    question = str(payload.get("question", ""))
    mode = str(payload.get("mode", "rule_first"))
    return JSONResponse(service.classify_one(question, mode=mode))
