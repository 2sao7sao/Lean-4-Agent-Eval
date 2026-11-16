# 一手资料与阅读路径

查阅日期：2026-11-14。以下区分官方机制说明、作者研究、工程经验与本项目建议；没有复现论文实验，也没有完整读完所有教材。`latest` 文档会变化，开始实现时应固定 Lean／依赖／规范版本。

## 先读这些

| 编号 | 资料 | 本轮查阅范围 | 为什么读／读后要能回答 |
|---|---|---|---|
| L1 | [Theorem Proving in Lean 4 — Introduction](https://lean-lang.org/theorem_proving_in_lean4/Introduction/) | 引言 | 形式化验证是把什么变成精确命题？ |
| L2 | [Dependent Type Theory](https://lean-lang.org/theorem_proving_in_lean4/Dependent-Type-Theory/) | 章节介绍和基础类型部分 | 表达式、类型、依赖类型是什么？无需第一天理解全部技术细节。 |
| L3 | [Propositions and Proofs](https://lean-lang.org/theorem_proving_in_lean4/Propositions-and-Proofs/) | 命题与证明的机制 | 为什么证明可以成为机器检查的对象？ |
| L4 | [Tactics](https://lean-lang.org/theorem_proving_in_lean4/Tactics/) | tactic 与证明项关系 | 搜索证明和核验生成的证明有什么不同？ |
| L5 | [Lean Reference — Elaboration and Compilation](https://lean-lang.org/doc/reference/latest/Elaboration-and-Compilation/) | elaboration、kernel 相关段落 | 用户写的代码如何变成核心理论中的项？ |
| L6 | [Validating a Lean Proof](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) | 证明核验、公理审计、重新检查、语义边界 | 为什么“看起来编译通过”仍要检查定理内容和依赖？ |
| E1 | [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | 评分器分类、过程／结果、重复运行相关部分 | 如何组合程序、模型和人的评分？属于工程经验，不是可靠性定理。 |
| S1 | [NIST — Confidence intervals for proportions](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) | 比例置信区间与 Wilson 公式 | 为什么成功率必须同时报告样本量和不确定性？ |

推荐顺序：L1 → L3 → 本项目第一课 → L2／L4 → L6 → E1 → S1。不要把通读数学教材设为做第一个评估实验的前提。

## 按建设阶段补充

| 编号 | 资料 | 本轮查阅范围 | 用途与边界 |
|---|---|---|---|
| L7 | [Axioms and Computation](https://lean-lang.org/theorem_proving_in_lean4/Axioms-and-Computation/) | 公理与计算的说明 | 理解证明依赖哪些前提；标准公理和临时塞入的业务断言需要区别对待。 |
| L8 | [Functional Programming in Lean](https://lean-lang.org/functional_programming_in_lean/) | 目录、教材定位 | 后续写数据类型、递归和纯函数；本轮未通读。 |
| L9 | [Mathematics in Lean](https://leanprover-community.github.io/mathematics_in_lean/) | 目录、逻辑与结构章节索引 | 第二阶段选读逻辑、结构、归纳，不必先学分析或拓扑。 |
| L10 | [Verifying Imperative Programs Using vcgen](https://lean-lang.org/doc/tutorials/latest/vcgen/) | 官方教程介绍、示例入口 | 程序验证进阶。当前机制有版本要求，v0.1 不依赖它。 |
| L11 | [Lean 4.34.0 release notes](https://lean-lang.org/doc/reference/latest/releases/v4.34.0/) | kernel soundness 说明 | 官方记录了内核可靠性修复；提醒我们记录工具链版本，不能把可信内核解释为实现永不出错。 |
| E2 | [τ-bench 作者论文](https://arxiv.org/abs/2406.12045) | 摘要和研究问题 | 工具／用户交互、最终环境状态、重复运行可靠性；不是办公场景的完整现成题库。 |
| E3 | [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) | 摘要和已报告偏差类型 | 位置、冗长、自我偏好等评分偏差；论文中的一致率不能直接作为我们任务的评分准确率。 |
| E4 | [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai) | 官方仓库 README；[旧站迁移说明](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) | 作为 trace 互操作参考。字段规范还需按实现时的 commit 核验；有 telemetry 不等于有完整证据。 |
| E5 | [Inspect 官方文档](https://inspect.aisi.org.uk/) | 框架介绍、Dataset／Solver／Scorer 组合 | 候选实验执行底座，可减少重复建设；未安装，未作工具选型结论。 |
| S2 | [NIST — Exact Binomial Confidence Limits](https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm) | 精确二项区间说明 | 小样本、罕见失败和单侧置信界的基础；适用性仍取决于抽样假设。 |

## 与本项目最接近的既有工作

| 编号 | 资料 | 本轮查阅范围 | 与本项目的关系 |
|---|---|---|---|
| E6 | [EvalGen — Who Validates the Validators?](https://arxiv.org/abs/2404.12272) | 作者摘要 | 协助生成评估标准和检查函数，再用人的评分选择更匹配的实现；强调看过结果后标准会变化。需求沟通和校准模块应参考它。 |
| E7 | [Agent-as-a-Judge](https://arxiv.org/abs/2410.10934) | 作者摘要 | 用 agent 评价 agent，覆盖任务解决中的中间反馈；研究结果不能直接推广为办公全任务的准确率。 |
| E8 | [AgentSpec](https://arxiv.org/abs/2503.18666) | 作者摘要与发表信息 | 用结构化触发条件、谓词和执行机制描述运行约束；运行时约束与离线评估有关，但任务不同。 |
| E9 | [Formalizing LLM Guardrails with AgentSpec and Lean](https://jfulfo.github.io/files/agentspec-formal.pdf) | 作者公开 PDF 的摘要、语义及 Discussion 段落 | 直接连接 Lean 与 agent 规则机制。作者报告对核心语义做机械证明，同时明确不覆盖解析器、具体领域谓词和 Python 实现正确性；本轮未编译其代码或确认同行评审状态。 |

这些工作表明，我们无需从零发明“自动生成评估”或“用 Lean 验证 agent 规则”。本项目的待验证价值在于把需求澄清、规则证据、办公产物验收、评分校准与迭代实验连成可用流程。不能把现有工作局部实验或形式化语义的结论扩大到整个办公 agent。

## 资料支持与本项目推导分开

- 官方 Lean 文档支持：证明项、类型检查、tactic、内核、公理与证明验证机制。
- 作者论文和工程文章支持：agent 评估可涉及交互、结果、重复运行，以及模型评分的局限。
- 本项目提出：需求合同、规则到证据的映射、四态结论、办公适配器、冻结评估与迭代流程。它们是设计建议，尚未通过跨任务实验验证。
- 尚需后续专题调研：形式化规约到监控器的可靠编译、时序／并发约束、统计序贯检验、模型评分校准、办公产物的渲染和语义验证。第一版不声称覆盖全部相关研究。
