# 规则版测试结果（2026-06-23）

## 文件
- 分类器：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\classifier_improved.py`
- 规则配置：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\task1_rules.json`
- 评测器：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\evaluate_task1.py`

## 指标
- 总准确率：100.0%
- 规则命中率：100.0%
- 规则命中准确率：100.0%
- 无效输出率：0.0%
- 边界样本准确率：100.0%
- LLM 兜底率：0.0%

## 说明
- 这轮结果说明当前 30 条测试集可被规则层完全覆盖。
- 这不是最终唯一方案；后续需要补一轮“全量走 LLM”的 A/B prompt 测试，验证降级场景下模型自身是否也能稳定分类。
