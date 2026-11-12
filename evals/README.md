# 回归集

正式用例在 cases/user.yaml；初始为空。case.example.yaml 是格式示例，保持 candidate，不得拿它产生通过率。参考检索运行 python tools/eval_recall.py --suite evals/cases/user.yaml。

--output 创建新 JSON 报告，不覆盖旧报告；--baseline 比较相同 evaluator/suite_kind 的旧报告，列出退化与移除用例。报告记录语料摘要，进一步比较时还应固定代码版本和用例版本。空集 status=not_evaluated，pass_rate=null。

工具合成集在 examples/demo-suite.yaml，通过 tools/demo.py 在临时副本运行。实际 agent 的工具轨迹、正文证据与答案通过 agent-observation.example.json 约定保存；当前不包含模型接入或自动答案裁判。

运行产物放 runs/（不提交）；选择需要的基线摘要后另存有含义的文件，并注明提交、配置和范围。真实问题中的个人资料按使用者自己的保存范围处理。评测答案不能挂载到被测 agent 的工作区。
