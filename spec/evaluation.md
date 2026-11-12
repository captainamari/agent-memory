---
id: spec-evaluation
title: 召回与质量评测规范
summary: 区分结构质量、参考召回覆盖与实际 agent 的证据使用。
type: rule
domain: null
status: active
created: '2026-11-12'
updated: '2026-11-12'
tags:
- governance
aliases: []
symbols: []
related: []
sources:
- kind: note
  ref: agent-memory 初始维护规范，由项目设计与实现共同定义
---

## 分开报告

check_memory 检查结构；eval_recall 运行确定性词法参考检索器；实际 agent 查阅和回答需要另行记录。参考召回得分不能宣称为模型回答正确率。文件式知识库依然存在导航与证据选择，需要真实问题来验证。

## 用例

evals/cases/user.yaml 初始为空。用实际使用中的漏查、误合并、版本冲突和无答案问题积累候选，由了解内容的人核对后改成 confirmed。retired 保留退出原因。修改业务事实可以同步修改预期，但不能根据被测输出自动重生成答案。

required_ids 是必须取得的证据；any_of 是等价证据组，每组至少取得一个；forbidden_ids 是不应取得的文档。无答案用例设置 expect_no_results，召回率分母为零时报告 null。全局偏好单独加载，不使无结果用例失败。

评测器只给实际返回完整 content 的文档计分，预算中遗漏的文档不算召回。报告逐条缺失、禁止证据、覆盖率和成本；对比同类基线时列出从通过变为失败的用例及消失用例，不能只看总分。

## 实际 agent 观察

使用 evals/agent-observation.example.json 的记录格式：固定语料提交、模型、提示词和工具版本，记录问题、工具返回的证据、最终回答、判定和预算。每次独立任务用干净会话；多轮任务明确提供历史。关键用例多次运行，区分稳定退化与随机波动。

answer_requirements 和 forbidden_claims 是为实际 agent 验收保留的字段。参考 eval_recall 不对自然语言答案评分，输出 answer_status=not_evaluated。证据 ID 覆盖也不证明读取了正确章节或正确理解条件，应检查原始工具返回及答案。

## 隔离

正式评测只向被测 agent 挂载允许的知识、入口和工具，预期答案及评测程序由外部评测器保管。仅从索引排除 evals 不足以隔离文件权限。当前仓库不提供受限执行沙箱，不声称已完成真实 agent 的防泄漏隔离。

examples/demo-suite.yaml 只用于虚构数据；tools/demo.py 在临时副本中运行它。合成演示通过说明工具路径可用，不说明用户知识质量。空用户集返回 not_evaluated / null，不算 100%。
