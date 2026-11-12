---
id: spec-metadata
title: 文档元数据规范
summary: 定义稳定身份、状态、来源、日期、关系和路由字段。
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

## 必填字段

id、title、summary、type、status、created、updated、sources。domain 在全局内容中为 null，领域内容中与目录一致。领域文档的 category 与路径分类一致；候选可预填目标 category。

id 是小写字母、数字、连字符或下划线组成的稳定标识。程序新建使用随机 ID；已有内容可以使用稳定语义 ID。重命名和归档不改变身份。title 面向人和 agent 描述具体问题，summary 说明范围与用途而非复制开头。

status 仅允许 active、candidate、archived。active 位于 spec/global/domains/playbooks，candidate 位于 inbox，archived 位于 archive。发布状态不证明知识正确；结论的依据、争议和适用版本写在正文。

sources 是列表，每项有 kind 和 ref。kind=url 表示 HTTP(S) 来源；file 表示仓库根相对文件路径；note 表示明确归属的用户陈述或整理说明；observation 表示可说明过程的观察。活动文档至少一项来源，候选可以暂缺。来源存在不等于已核实。

## 可选字段

tags、aliases、symbols、related、supersedes 都是无重复的字符串列表。aliases 保存自然语言问法，symbols 保存精确 API、错误码、类名等标识。related 是相关证据 ID，一跳召回不会递归展开整库；supersedes 表示明确替代关系，不能把所有新观点自动当成对旧观点的更正。

review_after 是建议复核日期。活动文档到期只提醒复核，strict 可升级为错误；归档文档不触发到期提醒。created 和 updated 为 YYYY-MM-DD，updated 不早于 created。created 为入库日期，原资料发表时间在来源说明中单独记录，不能混用。

## 引用

优先使用 related ID，或正文链接 `[文档标题](memory:document-id)`。如果引用具体章节，使用 memory:document-id#章节锚点。锚点按小写标题、保留中文和数字、空格转连字符计算；明确 span/a 的 id 也受支持。重命名标题要检查锚点影响。

普通相对 Markdown 链接同样支持，但移动文件时若断链，整次变更会被拒绝，需要先修正相关正文。file 来源路径也应纳入移动影响审查。
