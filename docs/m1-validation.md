# M1 实现验收记录

日期：2026-11-16。范围：本地销售到 PPT 需求沟通、验收标准生成、审查确认与既有判定模型。

| 检查 | 本次结果 | 能说明什么 |
|---|---|---|
| Python 回归 | 43 项通过 | 合同边界、澄清、动态参数、否定/不确定表达、冲突、来源、确认失效、CLI 标准输入流程 |
| M1 合成沟通重放 | 3 条用户消息，生成 6 条需求和 8 个验收项 | 需要澄清 → 可审查 → 合成确认的流程可运行 |
| 仓库资产检查 | 通过 | Schema、引用、场景计划、原始夹具哈希、参考金额独立重算、本地 Markdown 链接有效 |
| Lean 模型 | 11 个命名定理通过构建和公理审计，4 个负向控制有效 | 既有必检聚合模型的声明性质；不涵盖 M1 Python 实现 |

复现：

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/intake.py demo
.venv/bin/python scripts/check_project.py
# lake 在 PATH，使用 formal/lean-toolchain 固定版本
python3 scripts/check_formal.py
```

演示产物位于 `.artifacts/m1-demo/`，形式检查回执位于 `.artifacts/formal-verification.json`，均忽略提交。演示确认人是 `synthetic-demo-reviewer`，不代表真实业务用户已接受标准。

测试中特别覆盖了“分析”一词不能被当作金额单位“分”、文件名中的年月不能代替用户指定的比较期间、按日区间不能扩成整月、净额与不扣退款的矛盾需要澄清，以及旧确认不能覆盖已更正的合同。

没有调用真实模型或 Agent，没有生成或验收实际 PPT，没有生产冻结、身份认证、通用自然语言理解或总体可靠性结论。当前规则模板的未识别表达和混合额外要求仍需用户对照原始需求审查；下一步应增加真实需求校准样本并实现 M2 场景构建。
