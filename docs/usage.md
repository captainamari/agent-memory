# 使用与维护

## 从模板开始

克隆或复制此仓库；仓库启用 GitHub 的 Template repository 后，也可以使用 Use this template 创建副本。先安装 requirements.txt，运行 check_memory 和 demo，明确加载 AGENTS.md。正式 domains 初始没有业务资料。工程领域使用 engineering profile，其他领域使用 general；不需要手工复制 example-domain。

只要求用户解释资料的用途、范围和待解决问题。agent 负责分类建议、去重和草稿整理；重要事实冲突由用户判断。若 agent 无法执行命令，应明确报告未完成校验，不能伪称开箱运行成功。

## 一次维护

1. 查看工作区差异，读取规范和目标领域入口。
2. 通过 recall / read 检查已有结论及来源。
3. 编辑候选或既有正文；维护稳定身份、日期、来源和关系。
4. 新增候选使用 manage promote，移动/归档/删除先查看 impact。
5. 运行 build_index、check_memory；检查错误及维护提醒。
6. 查看 Git 差异，保存一次完整提交，汇报新增/修正、未知项及实际运行的检查。

命令帮助使用 --help。--root 默认是工具所在仓库，不是当前目录；操作另一份语料时务必显式指定。

## 生命周期演示

tools/demo.py 在临时副本建立虚构物流资料，验证领域限定、精确符号、关联约束、历史排除和无结果查询。不依赖模型、网络或真实业务系统。用户回归集保持为空；演示不会添加定时任务或发送通知。

## 新增类别

在 memory.config.json.categories 中定义目录与允许的 type，在 profile / domain.json.categories 中启用。当前内置 type 集合固定；新增类型属于 schema 变更，应修改 model.TYPES、规范、模板和测试。只启用分类不会创建空目录。

## 已有资料迁移

先做清单：原路径、目标路径、稳定 ID、类型、来源、当前状态、已知引用。填入 planning/migrations 的模板，先迁移一组样例检查。不要凭标题推断未读资料的事实或验证状态。历史内容保留历史身份，示例和工具日志不作为活动知识导入。

## 结果解释

error 阻止接受；warning 是复核或体例提醒。--strict 适合发布前审查，但复核到期不等于结论错误。初始上手只需默认校验，再按问题处理严格提醒。global 预算是字符预算，不是模型 token 数。

检查依赖需要真实文件存在，外部 URL 不发网络请求。当前检查器支持本库约定的 Markdown 子集；复杂格式先用小测试验证，不要以通过检查推断任何 Markdown 渲染器都一致。
