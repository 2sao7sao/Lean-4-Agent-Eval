# Lean-4-Agent-Eval

**从简单沟通到评估合同与可复核评估集，让验收标准、过程证据和最终交付对应起来。**

<p align="center">
  <a href="#quick-start">快速开始</a> ·
  <a href="docs/intake.md">沟通与合同 API</a> ·
  <a href="docs/evaluation-dataset.md">评估集与参考核验</a> ·
  <a href="docs/architecture.md">系统架构</a> ·
  <a href="#status-and-roadmap">实现状态</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Stage-M2_offline_evalset-8bd5ca" alt="M2 offline evaluation dataset" />
  <img src="https://img.shields.io/badge/Lean-verdict_model-b7bdf8" alt="Lean verdict model only" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-8bd5ca" alt="Apache-2.0 license" /></a>
  <a href="https://github.com/2sao7sao/Lean-4-Agent-Eval/actions/workflows/ci.yml"><img src="https://github.com/2sao7sao/Lean-4-Agent-Eval/actions/workflows/ci.yml/badge.svg" alt="CI workflow status" /></a>
</p>

## 为什么做这个项目

Agent 完成了一次工具调用、写出了一份报告，并不直接说明用户的目标已经达成。可靠的评估需要先把需求变成明确标准，再收集独立证据，检查实际过程和交付物。

Lean-4-Agent-Eval 围绕 **需求拆解 → 验收标准生成 → 评估集构建 → 执行取证 → 分层验证 → 回归迭代** 建设。

| 能力 | 当前可用范围 |
|---|---|
| 澄清需求 | 从简短中文沟通识别销售到 PPT 的关键字段；缺失、不确定、冲突或已识别的超范围要求先提问。 |
| 生成验收标准 | 根据金额口径、月份、维度、语言、页数和权限，动态生成 6 条需求、8 个必检项及证据要求。 |
| 审查与更正 | 保存多轮记录和字段来源；绑定合同审查哈希；需求更正使旧确认失效。 |
| 检查合同 | 校验结构、引用、必检覆盖及确认一致性；未知不能算作通过。 |
| 自动构建评估集 | 从已确认合同和 CSV 生成 55 个正常、边界、异常场景，记录版本、种子和来源分区。 |
| 独立核验参考答案 | Python 精确金额计算生成参考；另一套 CSV 解析与 SQLite 聚合复算数值和逐行记录。 |
| 检验评分器 | 用 60 个合成控制样本检查正确结果、错误结果、缺证据和评估器故障。 |
| 形式化判定模型 | Lean 证明非空必检聚合、失败优先、遗漏检查阻止通过等明确性质。 |

当前是 **本地领域规则原型**，无需模型 API。M1 负责需求与合同，M2 已接通离线评估集构建和参考核验。真实 Agent 执行、PPT 文件解析与渲染、trace 采集仍在 M3；Lean 证明范围限于判定模型，不覆盖本轮 Python 实现。

<a id="quick-start"></a>
## 快速开始

需要 Python 3.11+。演示使用合成沟通记录，在本地运行。

```bash
git clone https://github.com/2sao7sao/Lean-4-Agent-Eval.git
cd Lean-4-Agent-Eval
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/intake.py demo
.venv/bin/python scripts/evalset.py build \
  --contract .artifacts/m1-demo/contract.json \
  --input examples/sales-to-ppt/input/sales.csv \
  --out .artifacts/m2-demo
.venv/bin/python scripts/evalset.py verify \
  --bundle .artifacts/m2-demo \
  --contract .artifacts/m1-demo/contract.json
```

预期输出包括：

```text
needs_clarification → needs_clarification → ready_for_review → requirements_confirmed
user_turns: 3
requirements: 6
acceptance_checks: 8
contract_status: draft
execution_ready: false
```

在 `.artifacts/m1-demo/` 查看 `contract.json`、`review.md`、`session.json` 和 `demo-report.json`。演示中的确认来自合成审查人，只验证沟通到合同的流程，不是实际用户批准或 Agent 性能分数。

M2 预期输出 `PASS_FOR_M2_DATASET_AND_CONTROLS`：55 份参考结果通过独立核验，60 个控制结果与预期一致（12 PASS、39 FAIL、6 UNKNOWN、3 ERROR）。这里的 FAIL 是故意错误的控制样本被正确拒绝。

在 `.artifacts/m2-demo/` 查看 `bundle.json` 和 `verification.json`；`agent/` 保存各场景的输入、任务与输出 Schema，`evaluator/` 保存参考答案、逐行计算记录和评分器反例。只将单个场景的 `agent/…` 目录交给被测 Agent。输出目录不可覆盖，重跑时更换 `--out`。也可通过 `scripts/evalset.py demo --out .artifacts/another-demo` 一步重放合成 M1→M2 流程。

开始一次交互式沟通：

```bash
.venv/bin/python scripts/intake.py chat \
  --request '帮我分析销售数据，做一份五页中文PPT给经营负责人，说明变化贡献。' \
  --session .artifacts/my-intake/session.json \
  --out .artifacts/my-intake/export
```

可以一次补充多个口径；修改已有口径时使用“更正：…”。标准齐全后显示审查稿，输入“确认”记录本次需求确认。支持保存后通过 `reply` 继续，详见 [沟通与合同 API](docs/intake.md)。

## 如何工作

```text
用户需求 → 提取显式字段 → 缺失/冲突澄清 → 生成合同与验收标准
                                     ↓
                      审查来源与规则 → 哈希绑定的需求确认
                                     ↓
               M2：场景变体 → 双实现参考核验 → 评分器控制
                                     ↓
                 M3：Agent 执行 → 实际产物/trace → 验收
```

关键口径未补齐时，`contract` 为 `null`；识别到冲突不会悄悄选择一方。每个字段保留来源轮次，编译器提议的通用规则与阈值单独展示，供用户审查。

**需求已确认不等于执行已就绪。** 当前业务检查器仍标为 `planned`，生成合同保持 `draft`。合同确认也不构成邮件、上传或其他外发批准。

## 复现销售分析到 PPT 的例子

| 沟通输入 | 行为 |
|---|---|
| “分析销售数据，五页中文 PPT，给经营负责人，说明变化贡献” | 识别交付目标，追问数据范围、金额口径与权限。 |
| “使用 input/sales.csv；基期2026-09，对比期2026-10” | 记录文件与月份来源，继续澄清统计定义。 |
| “订单快照，按订单业务日期；净销售额，仅 paid；CNY 分；退款扣回原订单月；按 region；仅本地交付” | 自动生成金额、分组贡献、结论依据、文件、跨产物一致性及权限验收项。 |
| 审查后确认；随后更正为“六页 PPT” | 先记录匹配哈希的确认；更正后重新生成标准并要求重新审查。 |

[样例目录](examples/sales-to-ppt/README.md) 提供十行合成 CSV。默认合同基准的月度净额为 2200 元和 1800 元，差额 -400 元、变化率 -18.18%。原有十二项人工覆盖计划保留作设计基准；M2 自动生成下列独立资产：

| 类型 | 数量 | 例子与预期行为 |
|---|---:|---|
| 正常 | 12 | 基准、打乱行序、增加取消订单或区间外订单；后几种保持业务数值不变。 |
| 边界 | 13 | 空数据先澄清；零基期的变化率为未定义；零对比期、全额退款、无 paid 订单按口径计算。 |
| 异常 | 30 | 重复订单、混合币种、缺字段、非法日期/状态/金额等；返回问题代码，不输出销售结论。 |
| 评分器控制 | 60 | 差一分钱、错分组/币种/单位、伪造增长率、关键词堆砌、缺证据、模拟提取故障。 |

开发/校准/保留分区分别为 19/18/18 个场景；同源变体不跨区，完全相同的空 CSV 只留一份。这是可复现的合成分区，尚无真正未见样本或访问隔离。PPT 控制仅使用合成的提取字段，不能证明实际 PPT 正确或可读。

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check_project.py
```

这些检查覆盖沟通状态、确认失效、合同边界、精确计算、场景生成、分区、篡改参考、评分器反例及独立 CLI 核验；不是对通用语言理解或办公 Agent 的性能评价。

本地验收记录及可复现命令见 [M1 验收](docs/m1-validation.md) 和 [M2 验收](docs/m2-validation.md)。形式模型另有 11 个命名定理及 4 个负向控制，与离线业务检查分别报告。

<a id="status-and-roadmap"></a>
## 实现状态与路线

| 阶段 | 状态 | 下一项验收证据 |
|---|---|---|
| M0 产品架构与合同骨架 | 已建立 | 持续保持引用、数值和判定模型检查有效。 |
| M1 需求沟通到合同 | 销售到 PPT 的规则流程已实现 | 增加真实需求表达与用户审查样本；扩展解析覆盖，保持不确定口径不被猜测。 |
| M2 自动构建评估集 | 销售模板的离线流程已实现 | 55 场景、独立参考复算、60 个评分器控制；生产保留集访问隔离仍待接入。 |
| M3 真实业务闭环 | 待实现 | Agent、工具边界、实际 analysis.json / PPTX 和全页渲染证据。 |
| M4 可信迭代 | 待实现 | 裁判校准、预算化实验、固定合同回归，禁止放宽标准换取高分。 |

执行冻结还需检查器实现、校准与注册表、确认身份和运行适配器；不因 M1 会话完成而跳过。[详细路线](docs/roadmap.md)

CI 每次 push / PR 都会跑两件事：全量 unittest 测试，以及 scripts/check_formal.py（用固定工具链重建判定模型、逐个审计定理的公理依赖、跑四个负向控制），后者产出的报告作为构建产物上传。它验证的是判定模型，不是 Agent 性能。

## 类 Lean 验证的边界

精确标准、证据与独立检查共同构成验收依据。`formal/` 中有 11 个命名定理，覆盖必检判定聚合；不证明需求理解、Python、数据真实性、trace 完整性或 PPT 质量。

已安装 `lake` 并配置 [固定工具链](formal/lean-toolchain) 后：

```bash
python3 scripts/check_formal.py
```

脚本构建模型、审计公理依赖并运行四个负向控制。形式证明、确定性检查、经验评分和统计区间分别报告；详见 [验证范围与信任边界](docs/verification-boundary.md)。

## 文档与代码

| 资源 | 用途 |
|---|---|
| [沟通与合同 API](docs/intake.md) | 支持口径、CLI、Python API、会话状态和错误处理。 |
| [评估集与参考核验](docs/evaluation-dataset.md) | 场景覆盖、输入规则、生成与核验命令、参考答案和评分器边界。 |
| [系统架构](docs/architecture.md) | 需求、场景、执行、证据、检查器与迭代边界。 |
| [合同语义](docs/evaluation-contract.md) · [Schema](schemas/contract.schema.json) | 字段、来源、确认、四种判定与冻结条件。 |
| [样例](examples/sales-to-ppt/README.md) | 沟通重放、数据口径、参考值和验收计划。 |
| [M1 验收](docs/m1-validation.md) · [M2 验收](docs/m2-validation.md) | 检查结果、复现命令与尚未验证的范围。 |
| [实现](src/lean4_agent_eval) · [测试](tests) · [Lean 核心](formal) | 当前可运行代码与性质检查。 |

项目只维护产品设计、实现与验收资产。真实沟通记录、数据、输出、凭据和本地检查回执应留在忽略提交的目录中。

相关项目：[Agent Peak Bench](https://github.com/2sao7sao/agent-peak-bench) 提供评估运行与实验组织参考；[EvolveMemory](https://github.com/2sao7sao/EvolveMemory) 提供可审查运行时与项目文档组织参考。它们是独立项目，当前没有运行时集成。
