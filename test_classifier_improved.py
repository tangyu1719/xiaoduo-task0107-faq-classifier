from pathlib import Path

import pytest

from classifier_improved import ClassificationError, batch_classify, normalize_category


def test_normalize_category_accepts_exact_labels() -> None:
    assert normalize_category("退款退货") == "退款退货"
    assert normalize_category("物流查询") == "物流查询"


def test_normalize_category_accepts_common_aliases() -> None:
    assert normalize_category("退款") == "退款退货"
    assert normalize_category("快递") == "物流查询"
    assert normalize_category("分类结果：投诉") == "投诉建议"


def test_normalize_category_rejects_unknown_output() -> None:
    with pytest.raises(ClassificationError):
        normalize_category("我觉得像售后")


def test_batch_classify_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    input_file = tmp_path / "samples.json"
    output_file = tmp_path / "out.json"
    input_file.write_text('[{"id": 1, "question": "你好"}]', encoding="utf-8")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        batch_classify(input_file, output_file)
