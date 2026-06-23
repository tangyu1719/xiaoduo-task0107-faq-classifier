# LLM Prompt A/B 测试结果（2026-06-23）

## 文件
- A/B 评测脚本：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\llm_ab_eval.py`
- Prompt v1：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\prompts\classification_prompt_v1_baseline.xml`
- Prompt v2：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\prompts\classification_prompt_v2_structured.xml`
- 测试集：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\XiaoDuo\yuanwen\task1_test_samples.json`

## A/B 结果

| 版本 | 准确率 | 无效输出率 | 说明 |
|---|---:|---:|---|
| v1 baseline | 13.3% | 83.3% | 只有 user prompt，分类边界和输出约束过弱 |
| v2 structured | 100.0% | 0.0% | 使用 XML 分层、system+user 分离、边界规则和 few-shot |

## 结论
- v1 的主要问题不是纯语义能力不足，而是输出协议严重失控，模型经常输出重复标签、解释性文本或非标准格式。
- v2 通过以下改造显著提升效果：
  - system / user prompt 分离
  - XML 结构化分层
  - 明确唯一标签输出约束
  - 注入 categories 定义与 boundary rules
  - 增加 few-shot 边界样例

## Prompt 改动理由
1. `system + user` 分离：把稳定约束和单条问题解耦，减少用户文本对整体指令的污染。
2. `XML 分层`：让角色、约束、分类定义、边界规则、示例彼此清晰，便于后续维护版本。
3. `边界规则显式化`：解决“退款 vs 物流”“投诉 vs 退货流程”“问候 vs 其他”等真实易错点。
4. `few-shot`：直接给模型示范多意图、流程抱怨、无效输入这三类关键边界。
5. `强输出约束`：显著降低无效输出率，避免重复标签、解释文本污染分类结果。
