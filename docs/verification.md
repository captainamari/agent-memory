# 初始交付验证

验证日期：2026-11-12。初始正式语料为 5 篇维护规范，0 个业务领域，0 条真实用户评测用例。虚构物流与温室资料仅在临时副本运行。

## 本地结果

环境：Linux，Python 3.12.14，PyYAML 6.0.3。

| 检查 | 结果 |
| --- | --- |
| `python tools/check_memory.py --strict` | 0 error / 0 warning |
| `python tools/build_index.py --check` | 无过时索引 |
| `python -m unittest discover -s tests -v` | 38 项通过 |
| `python tools/demo.py` | 7 条虚构召回用例通过 |
| `python tools/eval_recall.py --suite evals/cases/user.yaml` | not_evaluated，pass_rate=null |
| `python -m compileall -q tools` | 通过 |

测试包含新增、提升、重命名、归档、删除、引用保护、索引保留手写导航、到期提醒、元数据异常、锁、I/O 失败回滚、跨平台路径、字符预算、领域隔离、历史与候选排除、无结果问题、空评测及逐用例退化检测。索引正文中的链接与用户回归集格式也纳入校验。

## CI

[Knowledge checks](https://github.com/captainamari/agent-memory/actions/workflows/checks.yml) 配置 Linux / Windows × Python 3.11 / 3.12 四个任务，不上传运行 artifacts。真实执行状态以对应提交的 Actions 记录为准，配置存在不等于已执行成功。

## 范围

合成召回通过只证明参考工具在这些样例上符合约定。尚未测量真实业务知识覆盖、模型回答质量、不同 agent 的规则遵守率或大规模语料性能。真实案例后续逐步加入 evals/cases/user.yaml；实际 agent 验收使用独立观察记录。
