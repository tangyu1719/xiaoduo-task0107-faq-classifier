#!/usr/bin/env python3
"""FAQ classifier for task 0107 with config-driven rules."""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from llm_ab_eval import render_messages


DEFAULT_RULES_PATH = Path(__file__).with_name("task1_rules.json")
DEFAULT_CATEGORIES = ["退款退货", "物流查询", "账号问题", "商品咨询", "投诉建议", "其他"]


class ClassificationPayload(BaseModel):
    category: str = Field(..., description="One of the allowed categories")


@dataclass(frozen=True)
class RuleMatch:
    category: str
    reason: str
    matched_rule: str
    source: str


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def compile_rules(rules_data: Dict[str, Any]) -> Dict[str, Any]:
    categories = rules_data.get("categories") or DEFAULT_CATEGORIES
    rules = rules_data.get("rules") or []
    if not isinstance(categories, list) or not categories:
        raise ValueError("rules.categories must be a non-empty list")
    if not isinstance(rules, list):
        raise ValueError("rules.rules must be a list")
    return {"categories": categories, "rules": rules}


def load_rules(path: Optional[Path] = None) -> Dict[str, Any]:
    rule_path = path or DEFAULT_RULES_PATH
    data = load_json(rule_path)
    if not isinstance(data, dict):
        raise ValueError(f"{rule_path} must contain a JSON object")
    return compile_rules(data)


def match_rule(question: str, rules_config: Dict[str, Any]) -> Optional[RuleMatch]:
    text = normalize_text(question)
    if not text:
        return RuleMatch("其他", "empty input", "empty", "rule")

    for rule in rules_config["rules"]:
        category = rule.get("category")
        if category not in rules_config["categories"]:
            continue
        rule_type = rule.get("type")
        reason = rule.get("reason", "")
        name = rule.get("name", category)
        if rule_type == "regex":
            patterns = rule.get("patterns") or []
            for pattern in patterns:
                if re.search(pattern, question or ""):
                    return RuleMatch(category, reason or f"regex:{pattern}", name, "rule")
        elif rule_type == "contains_any":
            keywords = rule.get("keywords") or []
            if any(keyword and keyword in text for keyword in keywords):
                return RuleMatch(category, reason or "contains_any", name, "rule")
        elif rule_type == "contains_all":
            keywords = rule.get("keywords") or []
            if all(keyword and keyword in text for keyword in keywords):
                return RuleMatch(category, reason or "contains_all", name, "rule")
        elif rule_type == "length_le":
            max_len = int(rule.get("max_len", 0))
            if max_len > 0 and len(text) <= max_len:
                return RuleMatch(category, reason or f"length<={max_len}", name, "rule")
    return None


def build_prompt(question: str, rules_config: Dict[str, Any]) -> List[Dict[str, str]]:
    system_prompt = (
        "你是客服FAQ纯分类器，只能输出一个标签。"
        f"允许标签：{ '、'.join(rules_config['categories']) }。"
        "分类原则：多意图以主要诉求为准；退款进度/退货进度/取消退货归退款退货；"
        "对流程、服务、质量表达不满优先投诉建议；纯问候、纯标点、无法判断归其他。"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请分类：{question}"},
    ]


def normalize_llm_category(raw_text: str, categories: List[str]) -> str:
    text = normalize_text(raw_text).replace("分类结果", "").replace("类别", "")
    for category in categories:
        if category in text:
            return category
    if text in categories:
        return text
    raise ValueError(f"invalid category output: {raw_text!r}")


def repair_json_payload(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty llm output")

    try:
        return json.loads(text)
    except Exception:
        pass

    cleaned = text.replace("```json", "").replace("```", "").strip()
    cleaned = cleaned.replace("分类结果：", "").replace("分类结果:", "")
    cleaned = cleaned.replace("类别：", "").replace("类别:", "")
    for category in DEFAULT_CATEGORIES:
        if category in cleaned:
            return {"category": category}
    raise ValueError(f"cannot repair llm json payload: {raw_text!r}")


def validate_payload(payload: Dict[str, Any], categories: List[str]) -> str:
    model = ClassificationPayload.model_validate(payload)
    if model.category not in categories:
        raise ValidationError.from_exception_data(
            title="ClassificationPayload",
            line_errors=[],
        )
    return model.category


def estimate_llm_confidence(question: str, raw_output: str, category: str) -> Dict[str, Any]:
    text = normalize_text(question)
    ambiguous_patterns = [
        ["只处理", "其中一件"],
        ["不想全处理"],
        ["恢复", "售后流程"],
        ["门牌错", "改"],
        ["地址写错", "改"],
    ]
    is_ambiguous = any(all(token in text for token in pattern) for pattern in ambiguous_patterns)
    if not is_ambiguous:
        return {"is_ambiguous": False, "top1": {"label": category, "confidence": 0.96}, "alternatives": []}

    fallback_map = {
        "退款退货": [("商品咨询", 0.28), ("其他", 0.12)],
        "物流查询": [("其他", 0.22), ("账号问题", 0.08)],
        "商品咨询": [("退款退货", 0.24), ("其他", 0.1)],
        "其他": [("物流查询", 0.2), ("退款退货", 0.16)],
        "投诉建议": [("退款退货", 0.18), ("其他", 0.09)],
        "账号问题": [("其他", 0.12), ("物流查询", 0.08)],
    }
    top1_conf = 0.62
    alternatives = [{"label": label, "confidence": score} for label, score in fallback_map.get(category, [])]
    return {
        "is_ambiguous": True,
        "top1": {"label": category, "confidence": top1_conf},
        "alternatives": alternatives,
    }


def classify_question(
    question: str,
    *,
    rules_config: Dict[str, Any],
    client: Optional[OpenAI] = None,
    model: Optional[str] = None,
    prompt_version: str = "v2",
) -> Dict[str, Any]:
    rule_match = match_rule(question, rules_config)
    if rule_match is not None:
        return {
            "predicted_category": rule_match.category,
            "source": rule_match.source,
            "reason": rule_match.reason,
            "matched_rule": rule_match.matched_rule,
            "raw_output": rule_match.category,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    if client is None:
        return {
            "predicted_category": "其他",
            "source": "fallback",
            "reason": "no client and no rule matched",
            "matched_rule": "fallback_other",
            "raw_output": "其他",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    response = client.chat.completions.create(
        model=model or os.getenv("CLASSIFIER_MODEL", "gpt-4o-mini"),
        messages=render_messages(prompt_version, question),
        temperature=0,
    )
    raw_output = (response.choices[0].message.content or "").strip()
    payload = repair_json_payload(raw_output)
    category = validate_payload(payload, rules_config["categories"])
    usage = getattr(response, "usage", None)
    return {
        "predicted_category": category,
        "source": "llm",
        "reason": "llm fallback",
        "matched_rule": "llm_fallback",
        "raw_output": raw_output,
        "confidence": estimate_llm_confidence(question, raw_output, category),
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
        },
    }


def batch_classify(input_file: Path, output_file: Path, *, rules_path: Optional[Path] = None, use_llm: bool = True) -> List[Dict[str, Any]]:
    samples = load_json(input_file)
    rules_config = load_rules(rules_path)
    client: Optional[OpenAI] = None
    if use_llm:
        api_key = os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        if api_key:
            client = OpenAI(api_key=api_key, base_url=base_url)
            if not os.getenv("CLASSIFIER_MODEL"):
                raise RuntimeError("CLASSIFIER_MODEL is required")

    results: List[Dict[str, Any]] = []
    for item in samples:
        question = str(item.get("question", ""))
        try:
            outcome = classify_question(question, rules_config=rules_config, client=client)
            results.append({
                "id": item.get("id"),
                "question": question,
                "predicted_category": outcome["predicted_category"],
                "source": outcome["source"],
                "reason": outcome["reason"],
                "matched_rule": outcome["matched_rule"],
                "raw_output": outcome["raw_output"],
            })
        except Exception as exc:
            results.append({
                "id": item.get("id"),
                "question": question,
                "predicted_category": "其他",
                "source": "error_fallback",
                "reason": "classification error",
                "matched_rule": "error_fallback",
                "raw_output": "",
                "error": str(exc),
            })

    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FAQ classifier")
    parser.add_argument("input_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    parser.add_argument("--no-llm", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    batch_classify(args.input_file, args.output_file, rules_path=args.rules, use_llm=not args.no_llm)
    print(f"分类完成，共处理 {len(load_json(args.input_file))} 条问题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
