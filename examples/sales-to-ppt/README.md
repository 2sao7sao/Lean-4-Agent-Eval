# 销售数据分析到 PPT 交付

这是销售分析到 PPT 的产品样例。数据完全合成；原有 contract.json 和覆盖计划保留为人工基准，M1 通过沟通自动生成合同与标准，M2 从确认合同自动构建场景、私有参考与评分器控制。没有接入真实 Agent，也没有实际 PPT 或业务通过回执。

## 文件与角色

| 文件 | 角色 |
|---|---|
| [request.md](request.md) | 示例用户需求与明确口径 |
| [intake-conversation.json](intake-conversation.json) | M1 三条合成用户消息，实际进入澄清与编译流程 |
| [input/sales.csv](input/sales.csv) | 十行合成订单快照 |
| [contract.json](contract.json) | 六条需求、八个必检项、五类证据；状态为草案 |
| [reference.json](reference.json) | 评估器私有参考；不得提供给被测 Agent |
| [rubric.md](rubric.md) | 结论依据与 PPT 质量量表草案 |
| [case-plan.json](case-plan.json) | 原始六个 Agent 场景与六个评分器反例的设计计划；包含尚待 M3 的实际文件/工具故障等要求，不是 M2 生成结果 |
| [数值输出 Schema](../../schemas/sales-analysis.schema.json) | M2 的数值/澄清封套；不包含完整分析叙述 |

## 基准口径与参考结果

每行是一笔订单在同一快照下的状态，按订单业务日期归月。只纳入 `paid`，净额为 `gross_minor - refund_minor`，金额统一为 CNY 分。不得把这份订单快照当成现金流收付明细。

- 2026-09：220000 分，即 2200 元。
- 2026-10：180000 分，即 1800 元。
- 差额：-40000 分；变化率为精确分数 `-2/11`，展示为 `-18.18%`。
- East 分组变化 -50000 分，West +10000 分，加总等于总差额。

上述分解仅表明哪些分组贡献了变化，不足以证明下降由投放、需求、价格或服务问题导致。受评内容若提出这些因素，必须标为待验证假设。

## 预期交付与证据

Agent 应在隔离运行的输出目录提交 `analysis.json` 和 `report.pptx`。完整分析应表达月度净额、差额、精确变化率、region 分组变化、来源定位、数据口径与解释边界。M2 的严格 Schema 只定义数值/澄清部分；完整叙述及证据接口在 M3 接入。不能把私有参考文件直接当成 Agent 输出。

五页 PPT 的主题：执行摘要；月度对比；分组贡献；口径与限制；建议及待验证问题。评估器收集实际文件并渲染全部页面，检查内容、数字对应和可读性。文本中声称“已生成 PPT”不满足交付要求。

输入指纹和工具事件由运行器采集；文件哈希用于绑定内容，不能单独证明事件真实或采集完整。基准场景不给予外发批准，文件创建仅允许发生在运行输出目录。

## 复现当前检查

在仓库根目录按 README 安装依赖后：

```sh
.venv/bin/python scripts/intake.py demo
.venv/bin/python scripts/evalset.py build \
  --contract .artifacts/m1-demo/contract.json \
  --input examples/sales-to-ppt/input/sales.csv \
  --out .artifacts/m2-demo
.venv/bin/python scripts/evalset.py verify --bundle .artifacts/m2-demo \
  --contract .artifacts/m1-demo/contract.json
.venv/bin/python scripts/check_project.py
```

第一条命令将模糊需求经过两次补充，自动生成 6 条需求、8 个验收项，再记录合成审查确认。产物在 `.artifacts/m1-demo/`，确认不意味着执行就绪。生成标准可以随月份、净/毛额、单位、维度、页数、语言和权限变化，不读取 reference.json 作为答案。

M2 构建 55 个场景、60 个评分器控制；参考计算与 SQLite 独立复算一致后保存到 `.artifacts/m2-demo/`。输出目录不可覆盖；重跑时更换目录。空数据和 30 个异常场景要求澄清，不能编造数值。PPT 控制只使用合成提取字段。

最后一条命令检查合同结构、引用、原始场景计划、手工参考和文档链接。以上均不是 Agent 性能评估。真实 Agent、实际 PPT 和完整业务验收器需后续接入。详见 [M1 沟通说明](../../docs/intake.md) 与 [M2 评估集](../../docs/evaluation-dataset.md)。
