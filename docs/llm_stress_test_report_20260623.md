# LLM Only 压力测试报告（2026-06-23）

## 测试目标
- 构造 100 条**尽量避开当前规则词表**的样例，强制走 `llm_only`。
- 在高并发下验证节点的模型分类能力、吞吐、时延、token 消耗和稳定性。

## 测试文件
- 样例集：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\llm_stress_samples_100.json`
- 压测脚本：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\llm_stress_test.py`
- 结果 JSON：`F:\java\AIOPS\SuperBizAgent-release-2026-01-02\demo_wendanghua\SuperBizAgent-AgentFramework\web_rebuild_v2\task0107_review\docs\llm_stress_test_result_20260623.json`

## 压测配置
- 模式：`llm_only`
- 样本数：100
- 并发度：12
- 模型：`ep-20260616011833-tqqpk`
- provider：ARK OpenAI-compatible API

## 结果总览

| 指标 | 结果 |
|---|---:|
| 样本数 | 100 |
| 并发度 | 12 |
| 总准确率 | 96.0% |
| 无效输出率 | 0.0% |
| LLM 命中率 | 100.0% |
| 降级回退率 | 0.0% |
| 总耗时 | 36.4s |
| 吞吐 | 2.75 req/s |
| 平均响应时长 | 4229.59 ms |
| P50 | 3947.06 ms |
| P95 | 5764.65 ms |
| P99 | 6428.86 ms |
| Prompt Tokens | 9147 |
| Completion Tokens | 5180 |
| Total Tokens | 14327 |
| 平均单请求 Total Tokens | 143.27 |

## 分类维度准确率

| 类别 | 总数 | 正确 | 准确率 |
|---|---:|---:|---:|
| 退款退货 | 16 | 13 | 81.2% |
| 物流查询 | 16 | 15 | 93.8% |
| 账号问题 | 16 | 16 | 100.0% |
| 商品咨询 | 16 | 16 | 100.0% |
| 投诉建议 | 16 | 16 | 100.0% |
| 其他 | 20 | 20 | 100.0% |

## 结果分析

### 1. 高并发稳定性
- 在 12 并发、100 条全量走 LLM 的情况下，节点未出现服务级降级回退，`degraded_fallback_rate = 0.0%`。
- 说明当前节点在这一级别的并发下可稳定承压。

### 2. 准确率表现
- 总准确率达到 96.0%，说明结构化 prompt 对非规则覆盖样例也有较强分类能力。
- 薄弱点主要集中在 `退款退货` 的**隐式部分退/撤销售后**表达，以及一条 `物流地址修改` 的隐式物流表达。

### 3. 典型错例

1. `售后流程开始后还能恢复吗`
- 期望：`退款退货`
- 预测：`商品咨询`
- 说明：模型没有把“售后流程恢复”稳定理解为退款/退货语义。

2. `一笔里能只处理其中一件吗`
- 期望：`退款退货`
- 预测：`商品咨询`
- 说明：模型对“部分处理/部分退”的隐式说法理解不足。

3. `我不想全处理，只动一个可以吗`
- 期望：`退款退货`
- 预测：`其他`
- 说明：当退款词完全隐去时，模型更依赖上下文，单句识别会降级。

4. `我写的门牌错了，还来得及改吗`
- 期望：`物流查询`
- 预测：`其他`
- 说明：这是“收货/配送地址修正”的隐式物流表达，建议补 few-shot 或边界规则。

## 样例集质量说明
- 自动检查到 `keyword_violation_count = 3`，说明 100 条里仍有少量样例与现有规则词表发生交叉。
- 这不影响整体结论，但后续若要做更纯粹的 LLM benchmark，可把这 3 条再清洗掉。

## 改进建议

1. 在 `v2 structured prompt` 的 few-shot 中补充：
- 部分退款/部分处理
- 撤销售后/恢复售后
- 地址写错但想修改配送信息

2. 若上线要追求更稳的效果，建议保留当前“规则优先 + LLM 兜底”的混合模式：
- 高频显式问题由规则命中
- 隐式、自然化表达交给 LLM

3. 后续可增加的性能指标：
- 首字延迟
- 模型调用失败率
- 重试后成功率
- 按类别的平均 token 消耗
