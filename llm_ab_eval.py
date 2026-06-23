#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = BASE_DIR / "prompts"
ALLOWED = ["退款退货", "物流查询", "账号问题", "商品咨询", "投诉建议", "其他"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt(version: str) -> str:
    mapping = {
        "v1": PROMPT_DIR / "classification_prompt_v1_baseline.xml",
        "v2": PROMPT_DIR / "classification_prompt_v2_structured.xml",
        "v3": PROMPT_DIR / "classification_prompt_v3_implicit.xml",
    }
    path = mapping[version]
    return path.read_text(encoding="utf-8")


def render_messages(version: str, question: str) -> List[Dict[str, str]]:
    prompt = load_prompt(version)
    if version == "v1":
        user_text = prompt.split("<user_message>", 1)[1].split("</user_message>", 1)[0].strip().replace("{question}", question)
        return [{"role": "user", "content": user_text}]
    system_text = prompt.split("<user_message>", 1)[0].strip()
    user_text = prompt.split("<user_message>", 1)[1].split("</user_message>", 1)[0].strip().replace("{question}", question)
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_text},
    ]


def normalize_output(text: str) -> str:
    cleaned = (text or "").strip().replace("分类结果", "").replace("类别", "")
    cleaned = "".join(cleaned.split())
    for label in ALLOWED:
        if label in cleaned:
            return label
    return cleaned


def run_eval(version: str, samples_path: Path, output_path: Path) -> Dict[str, Any]:
    api_key = os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = os.getenv("CLASSIFIER_MODEL")
    if not api_key:
        raise RuntimeError("ARK_API_KEY or OPENAI_API_KEY is required")
    if not model:
        raise RuntimeError("CLASSIFIER_MODEL is required")

    client = OpenAI(api_key=api_key, base_url=base_url)
    samples = load_json(samples_path)
    results = []
    correct = 0
    invalid = 0
    for item in samples:
        messages = render_messages(version, item["question"])
        response = client.chat.completions.create(model=model, messages=messages, temperature=0)
        raw = (response.choices[0].message.content or "").strip()
        pred = normalize_output(raw)
        ok = pred == item["label"]
        if ok:
            correct += 1
        if pred not in ALLOWED:
            invalid += 1
        results.append({
            "id": item["id"],
            "question": item["question"],
            "label": item["label"],
            "predicted_category": pred,
            "raw_output": raw,
            "ok": ok,
            "prompt_version": version,
        })

    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "prompt_version": version,
        "total": len(samples),
        "correct": correct,
        "accuracy": round(correct / len(samples) * 100, 1) if samples else 0.0,
        "invalid_output_rate": round(invalid / len(samples) * 100, 1) if samples else 0.0,
        "output_file": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", choices=["v1", "v2", "v3"], required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_eval(args.version, args.samples, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
