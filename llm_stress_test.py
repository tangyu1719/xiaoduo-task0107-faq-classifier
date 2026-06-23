#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from task0107_review.task1_service import ServiceConfig, Task1ClassifierService


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def contains_rule_keyword(question: str, rules_path: Path) -> bool:
    data = load_json(rules_path)
    for rule in data.get("rules", []):
        for keyword in rule.get("keywords", []):
            if keyword and keyword in question:
                return True
    return False


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def run_stress(samples_path: Path, rules_path: Path, concurrency: int, prompt_version: str) -> Dict[str, Any]:
    samples = load_json(samples_path)
    violations = [item for item in samples if contains_rule_keyword(item["question"], rules_path)]

    service = Task1ClassifierService(
        ServiceConfig(
            rules_path=rules_path,
            use_rules=False,
            use_llm_fallback=True,
            llm_only=True,
            max_retries=2,
            batch_max_workers=concurrency,
            circuit_breaker_threshold=50,
            prompt_version=prompt_version,
        )
    )

    start_all = time.perf_counter()
    results: List[Dict[str, Any]] = []

    def worker(item: Dict[str, Any]) -> Dict[str, Any]:
        start = time.perf_counter()
        response = service.classify_one(item["question"], mode="llm_only")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "id": item["id"],
            "question": item["question"],
            "label": item["label"],
            "predicted_category": response.get("predicted_category"),
            "source": response.get("source"),
            "reason": response.get("reason"),
            "matched_rule": response.get("matched_rule"),
            "attempt": response.get("attempt", 0),
            "breaker_open": response.get("breaker_open", False),
            "usage": response.get("usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
            "error": response.get("error", ""),
            "latency_ms": round(elapsed_ms, 2),
            "ok": response.get("predicted_category") == item["label"],
        }

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, item) for item in samples]
        for future in as_completed(futures):
            results.append(future.result())

    total_elapsed = time.perf_counter() - start_all
    results.sort(key=lambda x: x["id"])

    latencies = [item["latency_ms"] for item in results]
    correct = sum(1 for item in results if item["ok"])
    invalid = sum(1 for item in results if item["predicted_category"] not in {"退款退货", "物流查询", "账号问题", "商品咨询", "投诉建议", "其他"})
    llm_hits = sum(1 for item in results if item["source"] == "llm")
    degraded = sum(1 for item in results if item["source"] == "degraded_fallback")
    prompt_tokens = sum(item["usage"].get("prompt_tokens", 0) for item in results)
    completion_tokens = sum(item["usage"].get("completion_tokens", 0) for item in results)
    total_tokens = sum(item["usage"].get("total_tokens", 0) for item in results)
    by_label = defaultdict(lambda: {"total": 0, "correct": 0})
    for item in results:
        by_label[item["label"]]["total"] += 1
        if item["ok"]:
            by_label[item["label"]]["correct"] += 1

    report = {
        "sample_count": len(samples),
        "concurrency": concurrency,
        "prompt_version": prompt_version,
        "keyword_violation_count": len(violations),
        "accuracy": round(correct / len(samples) * 100, 1) if samples else 0.0,
        "invalid_output_rate": round(invalid / len(samples) * 100, 1) if samples else 0.0,
        "llm_hit_rate": round(llm_hits / len(samples) * 100, 1) if samples else 0.0,
        "degraded_fallback_rate": round(degraded / len(samples) * 100, 1) if samples else 0.0,
        "throughput_rps": round(len(samples) / total_elapsed, 2) if total_elapsed else 0.0,
        "total_elapsed_sec": round(total_elapsed, 2),
        "latency_avg_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "latency_p50_ms": round(percentile(latencies, 50), 2),
        "latency_p95_ms": round(percentile(latencies, 95), 2),
        "latency_p99_ms": round(percentile(latencies, 99), 2),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "avg_total_tokens_per_request": round(total_tokens / len(samples), 2) if samples else 0.0,
        "label_metrics": {
            label: {
                "total": stat["total"],
                "correct": stat["correct"],
                "accuracy": round(stat["correct"] / stat["total"] * 100, 1) if stat["total"] else 0.0,
            }
            for label, stat in by_label.items()
        },
        "wrong_cases": [item for item in results if not item["ok"]][:20],
        "results": results,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--prompt-version", type=str, default="v2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_stress(args.samples, args.rules, args.concurrency, args.prompt_version)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"results", "wrong_cases", "label_metrics"}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
