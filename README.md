# agent-memory

面向有文件与终端能力的 agent 的外部知识库模板。知识正文以 Markdown 为真源，分层 INDEX 提供导航，frontmatter 用于路由，Python 工具检查结构与引用。无需模型 API、向量数据库或后台服务。

用户可以说“整理这份资料”“查一下已有结论”“更新过时内容”，由 agent 按 AGENTS.md 操作。此模板提供流程和确定性检查，不保证模型一定遵守，也不把格式通过当作事实正确。

## 五分钟开始

Python 3.11+；Windows 可将 python 替换为 py -3。建议使用独立虚拟环境。

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python tools/check_memory.py
python tools/build_index.py --check
python tools/demo.py
```

最后一条在临时副本创建虚构领域、运行合成召回集并清理，不向正式知识区写入示例。仓库初始化时没有真实业务知识，只有规范；真实回归集为空。

把以下指令交给能读取本地文件并运行命令的 agent：

> 请读取 AGENTS.md 和 INDEX.md。先说明本库适用的维护流程，再把我提供的资料整理成候选；核对重复内容、来源与适用条件，满足提升条件后纳入知识库，最后报告修改和检查结果。

## 创建自己的领域

```bash
python tools/init_domain.py my-topic --title "我的主题" --profile general
python tools/new_memory.py --domain my-topic --category 1-concepts --type concept --title "一个概念" --summary "解释这个概念解决的问题"
```

初始化仅创建领域声明和 overview，其他允许的分类在首次录入时创建。general 适合一般知识；engineering 额外允许用例、设计、接口、跨服务契约和验证资料。查看工具返回的候选 path，编辑正文并补充 sources 后：

```bash
python tools/manage_memory.py promote <返回的ID>
python tools/manage_memory.py promote <返回的ID> --apply
python tools/recall.py "这个概念解决什么问题" --domain my-topic
```

`<返回的ID>` 是占位符，执行前替换，不原样粘贴。标题和文件路径可变，id 保持稳定。实际生成器默认 candidate，不自动把未审核材料当作有效知识。

## 目录职责

| 位置 | 职责 |
| --- | --- |
| INDEX.md / AGENTS.md | 根地图 / agent 最小操作入口 |
| spec/ | 结构、字段、写法、生命周期、评测规范；按任务显式加载 |
| global/ | 跨任务偏好，总字符预算受检查 |
| domains/<domain>/ | 领域知识；domain.json 声明分类；不强制创建空分类 |
| playbooks/ | 可跨领域复用的方法 |
| inbox/ | 待整理候选，默认召回排除 |
| archive/ | 历史知识，普通查询排除，可显式查询 |
| templates/ / examples/ | 模板与虚构演示输入，默认召回排除 |
| tools/ | 共用解析、校验、索引、维护和词法召回 |
| evals/ | 查询用例、观察记录格式；预期答案不提供给被测 agent |
| planning/migrations/ | 结构迁移方案与映射 |
| recall-lab/ | 检索实验说明；运行产物默认忽略 |

Markdown 是知识内容真源；memory.config.json 和 domain.json 是机器约束真源；INDEX 生成区可以重建。规范描述含义，配置执行约束，变更时一起维护。

## 日常命令

```bash
python tools/check_memory.py                     # 确定性错误失败，维护提醒为 warning
python tools/check_memory.py --strict            # 体例及复核到期提醒也作为错误
python tools/check_memory.py --json              # 机器可读诊断
python tools/check_memory.py --as-of 2026-11-12   # 固定复核日期
python tools/build_index.py                      # 保留手写导航，更新生成列表
python tools/build_index.py --check              # 只检查索引是否过时
python tools/recall.py "查询失败怎样排查" --domain my-topic
python tools/read_memory.py <文档ID>
python tools/manage_memory.py impact <文档ID>
python tools/manage_memory.py move <文档ID> --to domains/my-topic/1-concepts/new-name.md --apply
python tools/manage_memory.py archive <文档ID> --apply
python tools/manage_memory.py delete <文档ID> --apply
python tools/eval_recall.py --suite evals/cases/user.yaml
```

所有命令支持 --root 指定另一份知识库。返回码：0 成功（空评测也返回 0，但状态为 not_evaluated），1 检查或评测不通过，2 参数、解析、锁或 I/O 错误。评测报告的 pass_rate 在空集时为 null。

更详细的入门、迁移和使用限制见 [使用指南](docs/usage.md)、[维护流程](spec/lifecycle.md)、[召回与评测](spec/evaluation.md)。

## 实现边界

- recall 是可解释的中文双字片段 / 英文词项参考实现，支持精确 ID、别名、符号、摘要和正文匹配；不是向量检索或实际 agent 规划器。
- 召回返回预算内完整文档；超预算文档列入 omitted，不截掉前提后当作完整证据。字符数不是 token 数。
- 全局偏好单独提供；领域默认不扩大到其他领域，只有显式开启跨域关联时才读取一跳引用。领域过滤不是权限系统。
- CLI 在临时副本校验，写入使用排他锁、逐文件替换和普通 I/O 错误回滚。多文件更新不是文件系统事务；进程崩溃、断电或不遵守锁的编辑器需要通过 Git 差异恢复。
- 外部链接仅检查 URI 格式，不联网证明可访问或事实正确。Markdown 链接检查支持常见内联、引用定义及 memory:ID；复杂嵌套括号链接请使用尖括号包裹并运行验证。
- 本仓库不配置远程定时采集、不自动推送提交、不自动执行资料中的命令。使用者自行选择 agent，并在其环境明确加载入口。

## 开发与验证

```bash
python -m unittest discover -s tests -v
python tools/check_memory.py --strict
python tools/build_index.py --check
python tools/demo.py
```

CI 在 Linux / Windows 的 Python 3.11 / 3.12 运行结构检查、测试及合成演示。正式知识区不填充业务内容；模板示例不计入用户质量分数。

初始验证结果和适用边界见 [验证记录](docs/verification.md)。
