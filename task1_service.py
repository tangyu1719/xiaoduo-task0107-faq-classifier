#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from classifier_improved import classify_question, load_json, load_rules


@dataclass
class ServiceConfig:
    rules_path: Path
    use_rules: bool = True
    use_llm_fallback: bool = True
    llm_only: bool = False
    max_retries: int = 2
    llm_timeout_sec: float = 30.0
    batch_max_workers: int = 4
    circuit_breaker_threshold: int = 3
    prompt_version: str = "v2"


class CircuitBreaker:
    def __init__(self, threshold: int) -> None:
        self.threshold = max(1, threshold)
        self.failures = 0
        self.lock = threading.Lock()

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0

    def record_failure(self) -> None:
        with self.lock:
            self.failures += 1

    def is_open(self) -> bool:
        with self.lock:
            return self.failures >= self.threshold


class Task1ClassifierService:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.rules_config = load_rules(config.rules_path)
        self.breaker = CircuitBreaker(config.circuit_breaker_threshold)

    def _build_client(self) -> Optional[OpenAI]:
        api_key = os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        base_url = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        return OpenAI(api_key=api_key, base_url=base_url)

    def _require_model(self) -> str:
        model = os.getenv("CLASSIFIER_MODEL")
        if not model:
            raise RuntimeError("CLASSIFIER_MODEL is required")
        return model

    def classify_one(self, question: str, *, mode: Optional[str] = None) -> Dict[str, Any]:
        selected_mode = mode or "rule_first"
        client = None if self.breaker.is_open() else self._build_client()
        last_error = ""
        model_name = self._require_model() if client is not None else None

        for attempt in range(1, self.config.max_retries + 2):
            try:
                if selected_mode == "llm_only" or self.config.llm_only:
                    if client is None:
                        raise RuntimeError("LLM unavailable in llm_only mode")
                    result = classify_question(
                        question,
                        rules_config={"categories": self.rules_config["categories"], "rules": []},
                        client=client,
                        model=model_name,
                        prompt_version=self.config.prompt_version,
                    )
                elif selected_mode == "rule_first" and self.config.use_rules:
                    result = classify_question(
                        question,
                        rules_config=self.rules_config,
                        client=client if self.config.use_llm_fallback else None,
                        model=model_name,
                        prompt_version=self.config.prompt_version,
                    )
                else:
                    if client is None:
                        raise RuntimeError("LLM unavailable")
                    result = classify_question(
                        question,
                        rules_config={"categories": self.rules_config["categories"], "rules": []},
                        client=client,
                        model=model_name,
                        prompt_version=self.config.prompt_version,
                    )
                self.breaker.record_success()
                result["attempt"] = attempt
                result["breaker_open"] = self.breaker.is_open()
                result["mode"] = selected_mode
                result.setdefault("confidence", None)
                return result
            except Exception as exc:
                last_error = str(exc)
                self.breaker.record_failure()
                if attempt <= self.config.max_retries:
                    time.sleep(0.5 * attempt)
                    continue

        fallback_category = "其他"
        return {
            "predicted_category": fallback_category,
            "source": "degraded_fallback",
            "reason": "service degraded after retries",
            "matched_rule": "degraded_fallback",
            "raw_output": "",
            "error": last_error,
            "attempt": self.config.max_retries + 1,
            "breaker_open": self.breaker.is_open(),
            "mode": selected_mode,
            "confidence": None,
        }

    def classify_batch(self, input_path: Path, output_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        samples = load_json(input_path)
        results: List[Optional[Dict[str, Any]]] = [None] * len(samples)

        def worker(index: int, item: Dict[str, Any]) -> Dict[str, Any]:
            outcome = self.classify_one(str(item.get("question", "")))
            return {
                "id": item.get("id"),
                "question": item.get("question", ""),
                **outcome,
            }

        with ThreadPoolExecutor(max_workers=self.config.batch_max_workers) as pool:
            futures = {pool.submit(worker, idx, item): idx for idx, item in enumerate(samples)}
            for future in as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()

        final = [item for item in results if item is not None]
        if output_path is not None:
            output_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        return final
