#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse

from task1_service import ServiceConfig, Task1ClassifierService


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

REPORT_METRICS = {
    "gold30": [
        {"version": "v1 baseline", "accuracy": "13.3%", "invalid": "83.3%", "note": "仅薄 user prompt，输出协议失控"},
        {"version": "v2 structured", "accuracy": "100.0%", "invalid": "0.0%", "note": "结构化 prompt + 边界规则 + JSON 输出"},
        {"version": "v3 implicit", "accuracy": "100.0%", "invalid": "0.0%", "note": "在 v2 基础上补强隐式语义推理"},
    ],
    "implicit20": [
        {"version": "v2 structured（还原版）", "accuracy": "95.0%", "invalid": "0.0%", "note": "失败 1 条：隐式投诉被保守归为其他"},
        {"version": "v3 implicit reasoning", "accuracy": "100.0%", "invalid": "0.0%", "note": "加入 boundary_conditions 与潜在语义推理"},
    ],
    "stress120": {
        "accuracy": "100.0%",
        "invalid": "0.0%",
        "llm_hit": "100.0%",
        "fallback": "0.0%",
        "concurrency": "12",
        "elapsed": "46.7s",
        "throughput": "2.57 req/s",
        "latency_avg": "4420.74 ms",
        "latency_p95": "5831.10 ms",
        "latency_p99": "6680.80 ms",
        "tokens_total": "164091",
        "tokens_avg": "1367.42",
    },
}

REPORT_HIGHLIGHTS = [
    "v1 的主要问题不是单纯语义差，而是没有把分类规则真正落进运行逻辑，且输出协议不稳定。",
    "v2 首次把 system / user 分离、XML 分层、唯一标签约束、边界规则和 few-shot 统一收进指令。",
    "v3 重点补的是隐式语义：先还原业务情境，再做分类判断，因此在 20 条隐式边界集上从 95.0% 提升到 100.0%。",
    "规则版证明节点可落地，LLM-only 版证明模型在关闭规则后仍具备独立分类能力与高并发下的稳定性。",
]


def render_table(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{title}</th>" for _, title in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{row.get(key, '')}</td>" for key, _ in columns) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_report_section() -> str:
    stress = REPORT_METRICS["stress120"]
    kpi_cards = "".join(
        [
            f"<div class='metric'><div class='metric-label'>{label}</div><div class='metric-value'>{value}</div></div>"
            for label, value in [
                ("120 条压力集准确率", stress["accuracy"]),
                ("并发度", stress["concurrency"]),
                ("吞吐", stress["throughput"]),
                ("P95 时延", stress["latency_p95"]),
                ("总 Token", stress["tokens_total"]),
                ("平均单请求 Token", stress["tokens_avg"]),
            ]
        ]
    )
    highlights = "".join(f"<li>{item}</li>" for item in REPORT_HIGHLIGHTS)
    gold_chart = json.dumps(
        [
            {"label": "v1", "accuracy": 13.3, "invalid": 83.3, "color": "#ef4444"},
            {"label": "v2", "accuracy": 100.0, "invalid": 0.0, "color": "#2563eb"},
            {"label": "v3", "accuracy": 100.0, "invalid": 0.0, "color": "#14b8a6"},
        ],
        ensure_ascii=False,
    )
    implicit_chart = json.dumps(
        [
            {"label": "v2 还原版", "accuracy": 95.0, "invalid": 0.0, "color": "#f59e0b"},
            {"label": "v3", "accuracy": 100.0, "invalid": 0.0, "color": "#14b8a6"},
        ],
        ensure_ascii=False,
    )
    flow_steps = "".join(
        [
            "<div class='timeline-step'><span class='timeline-tag'>v1</span><strong>baseline</strong><p>只有薄 user prompt，标签约束弱，输出协议失控。</p></div>",
            "<div class='timeline-step'><span class='timeline-tag'>v2</span><strong>structured</strong><p>引入 XML 分层、system/user 分离、边界规则与 few-shot。</p></div>",
            "<div class='timeline-step'><span class='timeline-tag'>v3</span><strong>implicit reasoning</strong><p>增加 boundary_conditions，把隐式语义还原写成规范。</p></div>",
        ]
    )
    failure_cards = "".join(
        [
            "<div class='case-card'><span class='case-badge bad'>v1 典型问题</span><strong>输出协议污染</strong><p>返回重复标签、解释文本、尾部特殊 token，导致即使语义猜对也无法直接消费。</p></div>",
            "<div class='case-card'><span class='case-badge warn'>v2 边界缺口</span><strong>隐式投诉理解偏保守</strong><p>如“整个处理过程都让我有点崩溃”容易被兜底到“其他”，说明隐式情绪语义还未显式写入。</p></div>",
            "<div class='case-card'><span class='case-badge good'>v3 修复方式</span><strong>先还原场景，再落标签</strong><p>对“处理 / 售后 / 门牌 / 楼栋”等潜台词先复原业务上下文，再归类到退款、物流或投诉。</p></div>",
        ]
    )
    return f"""
    <section class='hero'>
      <div>
        <span class='eyebrow'>Task 0107 · 运行结果展示</span>
        <h1>客服 FAQ 分类节点评测结果</h1>
        <p>把 Prompt 演进、A/B 结果、边界增强效果与高并发压力测试放在同一页，方便截图提交。</p>
      </div>
      <div class='hero-card'>
        <div class='hero-kpi'>
          <strong>v3 最终状态</strong>
          <span>30 条金标：100.0%</span>
          <span>20 条隐式边界：100.0%</span>
          <span>120 条 llm-only 压测：100.0%</span>
        </div>
      </div>
    </section>

    <section class='panel compact-panel'>
      <div class='section-title'>Prompt 版本对比</div>
      <p class='section-desc'>用柱状图直接展示三版 Prompt 的准确率与无效输出率差异，再单独突出 v2 到 v3 的隐式边界能力提升。</p>
      <div class='chart-grid'>
        <div class='chart-card'>
          <div class='chart-title'>30 条金标集 A/B</div>
          <div class='chart-box'><canvas id='goldChart'></canvas></div>
        </div>
        <div class='chart-card'>
          <div class='chart-title'>20 条隐式边界集 A/B</div>
          <div class='chart-box'><canvas id='implicitChart'></canvas></div>
        </div>
      </div>
    </section>

    <section class='panel compact-panel'>
      <div class='section-title'>120 条压力测试结果</div>
      <p class='section-desc'>该轮测试在关闭规则的 llm-only 模式下完成，用于证明 Prompt 自身可用性与并发稳定性。</p>
      <div class='metric-grid'>{kpi_cards}</div>
      <div class='stress-grid'>
        <div class='stress-card'><span>无效输出率</span><strong>{stress['invalid']}</strong></div>
        <div class='stress-card'><span>LLM 命中率</span><strong>{stress['llm_hit']}</strong></div>
        <div class='stress-card'><span>降级回退率</span><strong>{stress['fallback']}</strong></div>
        <div class='stress-card'><span>平均时延</span><strong>{stress['latency_avg']}</strong></div>
        <div class='stress-card'><span>P99 时延</span><strong>{stress['latency_p99']}</strong></div>
        <div class='stress-card'><span>总耗时</span><strong>{stress['elapsed']}</strong></div>
      </div>
    </section>

    <section class='panel compact-panel'>
      <div class='section-title'>关键结论</div>
      <ul class='insight-list'>{highlights}</ul>
    </section>

    <details class='panel details-panel'>
      <summary>展开查看 Prompt 演进路径与关键失败样例</summary>
      <div class='details-body'>
        <div class='section-title'>Prompt 演进路径</div>
        <p class='section-desc'>不是简单改词，而是把分类规则、边界条件与潜在语义推理逐步沉淀为可维护规范。</p>
        <div class='timeline'>{flow_steps}</div>
        <div class='section-title' style='margin-top:18px;'>关键失败样例与修复思路</div>
        <p class='section-desc'>这一块适合说明为什么需要 v3，也能让评审快速理解 Prompt 不是机械堆 few-shot。</p>
        <div class='case-grid'>{failure_cards}</div>
      </div>
    </details>

    <script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
    <script>
      const goldData = {gold_chart};
      const implicitData = {implicit_chart};

      function buildCompareChart(canvasId, rows, title) {{
        const ctx = document.getElementById(canvasId);
        if (!ctx) return;
        new Chart(ctx, {{
          type: 'bar',
          data: {{
            labels: rows.map(item => item.label),
            datasets: [
              {{
                label: '准确率',
                data: rows.map(item => item.accuracy),
                backgroundColor: rows.map(item => item.color),
                borderRadius: 8,
              }},
              {{
                label: '无效输出率',
                data: rows.map(item => item.invalid),
                backgroundColor: 'rgba(148, 163, 184, 0.55)',
                borderRadius: 8,
              }}
            ]
          }},
          options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{
              legend: {{ position: 'top' }},
              title: {{ display: false, text: title }},
              tooltip: {{ callbacks: {{ label: (ctx) => `${{ctx.dataset.label}}: ${{ctx.raw}}%` }} }}
            }},
            scales: {{
              y: {{ beginAtZero: true, max: 100, ticks: {{ callback: (v) => `${{v}}%` }} }},
              x: {{ ticks: {{ color: '#29415f' }} }}
            }}
          }}
        }});
      }}

      window.addEventListener('DOMContentLoaded', () => {{
        buildCompareChart('goldChart', goldData, '30 条金标集');
        buildCompareChart('implicitChart', implicitData, '20 条隐式边界集');
      }});
    </script>
    """


def render_page(result: Optional[dict] = None, selected_mode: str = "rule_first") -> str:
    result_html = ""
    llm_enabled = bool(os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")) and bool(os.getenv("CLASSIFIER_MODEL"))
    if selected_mode == "llm_only" and not llm_enabled:
        llm_notice = "<div class='notice notice-warn'><strong>当前未配置 LLM 环境变量。</strong> 仅 LLM 模式无法真实调用模型，请先设置 `ARK_API_KEY / CLASSIFIER_MODEL`，或先使用规则优先模式演示。</div>"
    elif not llm_enabled:
        llm_notice = "<div class='notice'><strong>当前演示环境未配置 LLM。</strong> 当前页可展示规则命中效果；未命中规则时的 fallback 不代表测试用例标签错误。</div>"
    else:
        llm_notice = "<div class='notice notice-ok'><strong>LLM 已启用。</strong> 可切换到“仅 LLM”模式验证 Prompt 本身的分类能力。</div>"
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
        * {{ box-sizing: border-box; }}
        body {{ font-family: Arial, sans-serif; margin: 0; background: #f3f7fb; color: #172033; }}
        .wrap {{ max-width: 1280px; margin: 0 auto; padding: 22px 18px 24px; }}
        .hero {{ display:grid; grid-template-columns: 1.5fr 0.9fr; gap: 16px; align-items: stretch; margin-bottom: 14px; }}
        .hero h1 {{ margin: 8px 0 12px; font-size: 34px; line-height: 1.15; }}
        .eyebrow {{ display:inline-block; font-size: 12px; font-weight: 700; color:#2457d6; background:#eaf1ff; border:1px solid #cfe0ff; padding:6px 10px; border-radius:999px; }}
        .hero-card, .panel {{ background: white; border: 1px solid #dce6f4; border-radius: 16px; padding: 18px; box-shadow: 0 10px 30px rgba(38, 63, 109, 0.06); }}
        .hero-kpi {{ display:grid; gap: 12px; min-height: 100%; align-content: center; }}
        .hero-kpi strong {{ font-size: 18px; }}
        .hero-kpi span {{ display:block; padding:10px 12px; background:#f7faff; border:1px solid #e1ebfb; border-radius:10px; font-weight:600; }}
        .panel {{ margin-bottom: 14px; }}
        .compact-panel {{ padding: 16px; }}
        .section-title {{ font-size: 22px; font-weight: 700; margin-bottom: 8px; }}
        .section-desc {{ margin: 0 0 12px; color:#52607a; }}
        textarea {{ width: 100%; min-height: 120px; padding: 12px; border:1px solid #cfd9ea; border-radius: 10px; }}
        button {{ background: #2563eb; color: white; border: none; padding: 10px 16px; border-radius: 10px; cursor: pointer; font-weight: 700; }}
        button:hover {{ background:#1d4ed8; }}
        pre {{ white-space: pre-wrap; word-break: break-word; margin:0; font-size: 13px; line-height:1.5; }}
        table {{ width:100%; border-collapse: collapse; font-size:14px; }}
        th, td {{ padding: 12px 10px; border-bottom: 1px solid #e7edf7; text-align:left; vertical-align: top; }}
        th {{ background:#f8fbff; color:#35507c; font-size:13px; }}
        .table-wrap {{ overflow:auto; border:1px solid #e2eaf6; border-radius: 12px; }}
        .chart-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:14px; }}
        .chart-card {{ border:1px solid #e3ebf7; border-radius: 14px; padding:14px; background:#fbfdff; min-height:280px; display:grid; grid-template-rows:auto 1fr; }}
        .chart-title {{ font-size:16px; font-weight:700; margin-bottom:10px; color:#223d68; }}
        .chart-box {{ position:relative; height:220px; min-height:220px; max-height:220px; }}
        .metric-grid {{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; margin-bottom: 12px; }}
        .metric {{ padding: 16px; background:#f8fbff; border:1px solid #dce8fb; border-radius: 12px; }}
        .metric-label {{ font-size:13px; color:#587095; margin-bottom:6px; }}
        .metric-value {{ font-size:22px; font-weight:700; color:#17315f; }}
        .stress-grid {{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; }}
        .stress-card {{ padding: 14px; background:#fff; border:1px solid #e4ebf6; border-radius: 12px; display:grid; gap:8px; }}
        .stress-card span {{ color:#60708b; font-size:13px; }}
        .stress-card strong {{ font-size:20px; }}
        .insight-list {{ margin:0; padding-left: 20px; display:grid; gap: 10px; line-height:1.6; }}
        .notice {{ margin: 0 0 14px; padding: 12px 14px; border-radius: 12px; background:#f8fbff; border:1px solid #dce6f6; color:#41546f; line-height:1.6; }}
        .notice-warn {{ background:#fff7ed; border-color:#fed7aa; color:#9a3412; }}
        .notice-ok {{ background:#ecfdf5; border-color:#bbf7d0; color:#166534; }}
        .timeline {{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:14px; }}
        .timeline-step {{ padding:16px; border-radius:14px; background:#f8fbff; border:1px solid #dde8f8; display:grid; gap:8px; }}
        .timeline-step p {{ margin:0; color:#556882; line-height:1.6; }}
        .timeline-tag {{ display:inline-block; width:fit-content; padding:5px 10px; border-radius:999px; background:#e7f0ff; border:1px solid #cdddff; font-size:12px; font-weight:700; color:#2854b8; }}
        .case-grid {{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:14px; }}
        .case-card {{ padding:16px; border-radius:14px; border:1px solid #e4ebf7; background:#fff; display:grid; gap:10px; }}
        .case-card p {{ margin:0; color:#596b86; line-height:1.6; }}
        .case-badge {{ display:inline-block; width:fit-content; padding:5px 10px; border-radius:999px; font-size:12px; font-weight:700; }}
        .case-badge.bad {{ background:#fee2e2; color:#b91c1c; }}
        .case-badge.warn {{ background:#fef3c7; color:#b45309; }}
        .case-badge.good {{ background:#dcfce7; color:#15803d; }}
        .demo-grid {{ display:grid; grid-template-columns: 1.05fr 0.95fr; gap:14px; }}
        .details-panel summary {{ cursor:pointer; font-weight:700; color:#1f3f77; list-style:none; }}
        .details-panel summary::-webkit-details-marker {{ display:none; }}
        .details-body {{ margin-top:16px; }}
        @media (max-width: 900px) {{
          .hero, .demo-grid, .metric-grid, .stress-grid, .chart-grid, .timeline, .case-grid {{ grid-template-columns: 1fr; }}
          .wrap {{ padding: 18px 14px 30px; }}
          .hero h1 {{ font-size: 28px; }}
        }}
      </style>
    </head>
    <body>
      <div class='wrap'>
        {render_report_section()}
        <div class='demo-grid'>
          <div class='panel'>
            <div class='section-title'>在线分类演示</div>
            <p class='section-desc'>规则优先 / 仅 LLM 两种模式可切换，适合现场演示节点工作方式。</p>
            {llm_notice}
            <form method='post' action='/classify'>
              <div style='margin-bottom:12px;'>
                <label><input type='radio' name='mode' value='rule_first' {('checked' if selected_mode == 'rule_first' else '')}/> 规则优先</label>
                <label style='margin-left:16px;'><input type='radio' name='mode' value='llm_only' {('checked' if selected_mode == 'llm_only' else '')}/> 仅 LLM</label>
              </div>
              <textarea name='question' placeholder='输入一条客服问题'></textarea>
              <div style='margin-top:12px;'><button type='submit'>开始分类</button></div>
            </form>
          </div>
          <div class='panel'>
            <div class='section-title'>LLM 边界样例</div>
            <p class='section-desc'>先切到“仅 LLM”，再点击样例自动填入，便于现场演示隐式语义能力。</p>
            <div style='display:grid; gap:8px;'>
              {''.join([f"<button type='button' onclick=\"fillSample('{sample}')\" style='text-align:left;background:#eef4ff;color:#1d4ed8;border:1px solid #bfdbfe;'> {sample} </button>" for sample in LLM_EDGE_SAMPLES])}
            </div>
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
