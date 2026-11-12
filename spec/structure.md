---
id: spec-structure
title: 目录与分类规范
summary: 定义基础目录、工程扩展以及分层索引的生成方式。
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

## 结构

只扫描 spec、global、domains、playbooks、inbox、archive 六个受管根目录中的 Markdown。INDEX.md 是导航，不是普通知识文档；其他 Markdown 必须有 frontmatter。受管目录不允许符号链接。examples、evals、templates、planning、recall-lab 不属于默认语料。

每个实际存在的受管目录有 INDEX.md。维护者编辑生成区外的范围、适用问题和阅读顺序；生成区根据直接子目录和文档元数据构建，禁止手工维护重复清单。根 INDEX 指向六个受管根，各层逐级可达。已知 ID 可以直接读取，不必沿目录逐层遍历。

## 分类

目录编号只控制展示顺序，实际允许类型由 memory.config.json 的 categories 指定，领域通过 domain.json 选择。配置声明不代表必须创建所有目录；0-overview 及一个 overview 文档是领域最低要求。新建分类需同时更新配置、规范与测试。

| 分类 | 内容边界 |
| --- | --- |
| 0-overview | 领域用途、范围、常见问题和入口 |
| 1-concepts | 概念、实体及状态 |
| 2-rules | 业务成立条件、限制和判定 |
| 3-decisions | 决策理由、替代方案和影响 |
| 4-runbooks | 可执行的操作、排障、恢复步骤 |
| 5-pitfalls | 故障经验、反例和已知陷阱 |
| 6-design | use-case 用户目标或 design 系统实现视角 |
| 7-interfaces | 单接口输入、输出、错误和调用约束 |
| 8-contracts | 多处复用的技术契约；不重复接口定义，不指业务合同实体 |
| verification | 领域系统的测试与验收资料；不是知识召回评测 |

use-case 与 design 可以描述同一场景的不同视角，用 related 稳定 ID 建立关系；主场景入口引用规则、接口和 runbook。by-deploy、by-use-case 优先做导航，不复制正文。单接口只有一篇说明时直接使用 operation.md；有多份附件时再建立 operation/，由 INDEX 导航。允许中文文件名，避免仅大小写不同及跨平台保留名称。

## 共享与实验

global 只存跨任务偏好，总字符预算受检查；playbooks 保存跨领域方法。规范在维护前显式加载，不能等查询偶然召回。通用模板不附带真实业务服务清单，虚构输入放 examples。领域初始化通过工具完成，避免复制示例后遗漏重命名。
