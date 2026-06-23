#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list")
    return data


def is_boundary_case(question: str, gold: str) -> bool:
    tokens = ["顺便", "太麻烦", "质量", "坏了", "投诉", "建议", "纯标点", "你好", "谢谢", "??", "??？", "异地登录", "退款的事", "流程"]
    return any(t in question for t in tokens) or gold in {"投诉建议", "其他"}


def evaluate(pred_path: Path, gold_path: Path) -> Dict[str, Any]:
    preds = load_json(pred_path)
    golds = load_json(gold_path)
    gold_map = {item["id"]: item for item in golds}

    total = 0
    correct = 0
    invalid = 0
    rule_hits = 0
    rule_correct = 0
    fallback_hits = 0
    by_label = defaultdict(lambda: {"total": 0, "correct": 0})
    boundary_total = 0
    boundary_correct = 0
    wrong_cases = []
    source_counter = Counter()

    for item in preds:
        sample = gold_map[item["id"]]
        gold = sample["label"]
        pred = item.get("predicted_category", "")
        question = sample["question"]
        total += 1
        by_label[gold]["total"] += 1
        source_counter[item.get("source", "unknown")] += 1
        if item.get("source") == "rule":
            rule_hits += 1
            if pred == gold:
                rule_correct += 1
        if item.get("source") in {"llm", "fallback", "error_fallback"}:
            fallback_hits += 1
        if pred not in {"退款退货", "物流查询", "账号问题", "商品咨询", "投诉建议", "其他"}:
            invalid += 1
        if pred == gold:
            correct += 1
            by_label[gold]["correct"] += 1
        else:
            wrong_cases.append({"id": item["id"], "question": question, "pred": pred, "label": gold})
        if is_boundary_case(question, gold):
            boundary_total += 1
            if pred == gold:
                boundary_correct += 1

    label_metrics = {
        label: {
            "total": stat["total"],
            "correct": stat["correct"],
            "accuracy": round(stat["correct"] / stat["total"] * 100, 1) if stat["total"] else 0.0,
        }
        for label, stat in by_label.items()
    }

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0.0,
        "invalid_output_rate": round(invalid / total * 100, 1) if total else 0.0,
        "rule_hit_rate": round(rule_hits / total * 100, 1) if total else 0.0,
        "rule_hit_correct_rate": round(rule_correct / rule_hits * 100, 1) if rule_hits else 0.0,
        "fallback_rate": round(fallback_hits / total * 100, 1) if total else 0.0,
        "boundary_accuracy": round(boundary_correct / boundary_total * 100, 1) if boundary_total else 0.0,
        "boundary_total": boundary_total,
        "boundary_correct": boundary_correct,
        "label_metrics": label_metrics,
        "source_distribution": dict(source_counter),
        "wrong_cases": wrong_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pred_file", type=Path)
    parser.add_argument("gold_file", type=Path)
    args = parser.parse_args()
    result = evaluate(args.pred_file, args.gold_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
