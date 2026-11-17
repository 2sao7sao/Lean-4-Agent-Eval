# M2 本地验收记录

日期：2026-11-16。范围：从 M1 确认合同构建销售分析到 PPT 的离线评估集，并独立复算参考、重放评分器控制。输入和确认人均为合成样例。

## 已验证结果

| 检查 | 结果 |
|---|---|
| 完整 Python 回归 | 70 项通过：M1/原有 43 项，M2 新增 27 项。 |
| M1→M2 衔接 | 三条合成消息经过澄清和审查确认，实际导出的合同作为 M2 build 输入；合同保持 draft。 |
| 输入场景 | 55 个：正常 12、边界 13、异常 30；开发/校准/保留为 19/18/18。 |
| 参考答案 | 55 份分析/澄清结果及逐行记录，通过独立 CSV 解析和 SQLite 整数聚合复算；24 个可计算，31 个需澄清。 |
| 评分器控制 | 60 个结果全部符合预期：12 PASS、39 FAIL、6 UNKNOWN、3 ERROR；FAIL 表示错误候选被正确拒绝。 |
| 基准参考 | 2026-09 为 220000 分，2026-10 为 180000 分，差额 -40000 分，精确变化率 -2/11。 |
| 仓库资产 | Schema、合同引用、原始手工参考、M1 沟通重放及文档链接检查通过。 |
| 既有 Lean 模型回归 | 11 个命名定理通过，4 个负向控制均被拒绝；证明范围仍仅为判定模型。 |

## 有意义的失败检查

- 未确认、确认失效、外部合同不一致、重新确认但改写为不支持的公式时拒绝生成/核验。
- 支持净/毛额、元/分、USD、多维度、英文七页等合同变体；用手算小数案例约束精度、精确分数和展示舍入。
- 无效日期、混合币种、重复订单、超额退款、无效金额及缺字段不产生销售结论；排除行中的错误仍被检测。
- 修改参考金额或逐行记录后，即使重算文件哈希，仍被独立复算拒绝。
- 注入错误参考生成器、恒定 PASS 评分器，构建/核验不能成功。
- 空场景清单、跨目录路径、将参考答案放入 Agent 输入目录被拒绝；目标目录不可覆盖。
- 相同合同/输入/种子/源码生成相同包；更换种子影响合成保留分区；各来源组的变体不跨分区，跨区输入字节不重复。
- 独立子进程可通过 CLI 核验生成包，不依赖生成器进程的内存结果。

## 复现

先按 README 安装依赖，在仓库根目录运行；目标目录须未存在：

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/intake.py demo
.venv/bin/python scripts/evalset.py build \
  --contract .artifacts/m1-demo/contract.json \
  --input examples/sales-to-ppt/input/sales.csv \
  --out .artifacts/m2-demo --seed 42
.venv/bin/python scripts/evalset.py verify \
  --bundle .artifacts/m2-demo \
  --contract .artifacts/m1-demo/contract.json
.venv/bin/python scripts/check_project.py
```

Lean 工具链可用时另运行 `python3 scripts/check_formal.py`。本地数据包和回执保存在忽略提交的 `.artifacts/`，仓库提交生成器、测试、Schema 和复现说明。`verify` 的核验源码必须与数据包指纹一致；更改源码后构建新的数据集。

## 未验证范围

没有运行真实 Agent，没有生成、打开或渲染实际 PPTX，没有收集真实 trace。PPT 控制只是合成提取字段；数值输出 Schema 不包含完整叙述、引用和因果判断。合成分区没有生产访问隔离或真实未知样本，不能据此给出 Agent 成功率、总体置信区间或生产可靠性结论。Python 生成器、参考计算、评分器和 Lean 的实现等价性未获形式证明。

M2 回执为 `PASS_FOR_M2_DATASET_AND_CONTROLS`，同时保持 `full_contract_verdict: NOT_ASSESSED`、`formal_proof: NOT_PROVED`。后续需按 [路线](roadmap.md) 接入真实文件与运行边界。
