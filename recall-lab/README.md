# 召回实验区

variants/ 保存候选算法和配置说明，data/ 与 runs/ 为本地实验产物并被 Git 忽略。使用同一语料版本、同一组已确认用例比较算法；保留每题结果，区分覆盖、错误证据和成本。不要将实验得分自动解释为实际 agent 回答正确率，也不要直接覆盖 tools/memorylib/retrieval.py 的基线。
