# M2：从已确认合同构建评估集

M2 将 M1 已确认的销售分析到 PPT 合同转为可复现的输入场景、任务包、参考答案和评分器控制。它实现离线评估资产的构建与核验；真实 Agent、PPTX 和 trace 的执行验收由 M3 接入。

## 输入与合同门禁

必须提供 M1 导出的 `contract.json` 和符合口径的基准 CSV。确认哈希必须有效、未决问题必须为空，且需求、检查项、输入/交付物、假设与判定策略须匹配当前 M1 模板。没有确认、修改后未重新确认、重新确认但包含不支持的自定义公式，均拒绝生成。非法基准 CSV 先返回问题代码，不能作为正常样本继续扩增。

**需求确认允许准备评估资产，不代表批准执行。** 合同保留 `draft` 和业务检查器 `planned` 状态；M2 的局部检查器不会擅自升级整个合同。

支持净/毛销售额、CNY/USD、分/元输入、两个不同的 2000–2099 年月份，以及 region/channel/product 的单维或多维汇总。PPT 页数、语言、受众及外发策略继承合同。多维按每个维度分别汇总，不生成维度间的交叉分组。

| 字段 | 规则 |
|---|---|
| `order_id` | 非空，全表唯一。 |
| `business_date` | 有效的 `YYYY-MM-DD` 日期；按业务日期归月。 |
| `currency` | 每行均与合同的单币种一致。 |
| `payment_status` | `paid`、`unpaid`、`cancelled`；仅 paid 纳入汇总。 |
| 分输入 | `gross_minor`、`refund_minor`，非负整数。 |
| 元输入 | `gross_amount`、`refund_amount`，最多两位小数；精确转换为分/美分。 |
| 金额限制 | 不接受指数、NaN、负数；退款不得超过毛额，每个金额不超过 10¹² 分/美分。 |
| 合同分组列 | 每个必需维度均非空；字符串值区分大小写，首尾空格去除。 |

最多 10 MiB、10000 条记录；基准输入须少于 10000 条，为变体添加行留出容量。所有行都先校验，包括未支付、取消和区间外订单。全额退款对净额贡献为零，对毛额不作扣减。零基期变化率为 `null`；空数据需要澄清，不能解释为确定的零销售。已存在订单但没有 paid 时可以得到零汇总。

## 运行

```bash
.venv/bin/python scripts/intake.py demo
.venv/bin/python scripts/evalset.py build \
  --contract .artifacts/m1-demo/contract.json \
  --input examples/sales-to-ppt/input/sales.csv \
  --out .artifacts/m2-demo --seed 42
.venv/bin/python scripts/evalset.py verify \
  --bundle .artifacts/m2-demo \
  --contract .artifacts/m1-demo/contract.json
```

M1 demo 中的确认是合成记录。真实使用应先通过 M1 沟通、审查和确认，再传入自己的合同和 CSV。`--input` 明确绑定基准内容，各场景 `task.json` 将合同 I01 映射到场景自己的 `input.csv`；它不自动读取合同路径上的其他文件。

支持重复使用 `--split development --split calibration` 选择分区；默认构建全部三分区。`--seed` 为 0 到 2³²−1。相同合同、输入、种子、分区和源码生成相同数据集标识。`demo --out <新目录>` 可一键执行合成 M1→M2 流程。

构建先在临时目录生成全部资产，独立核验通过后原子移动到目标目录。目标目录不可已存在；重跑请指定新目录。核验失败返回非零退出码，不留下被标记为成功的数据集。`verify` 在独立进程中重新计算，不信任已保存的 `verification.json`。

## 文件与参考隔离

```text
bundle.json                         # 合同/数据/源码指纹、覆盖与文件清单
verification.json                   # 构建时核验回执，可再次独立核验
agent/<split>/<case-id>/
  input.csv                         # 该场景输入
  task.json                         # 口径、任务、I01 映射及交付要求
  analysis.schema.json              # 数值与澄清输出约束
evaluator/
  contract.json                     # 包含 M1 确认记录的合同
  development-source.csv            # --input 的原始字节
  <split>/<case-id>/reference.json  # 私有参考分析与展示数值
  <split>/<case-id>/row-audit.json  # 可解析记录的纳入/排除及金额明细
  controls/*.json                   # 合成正确/错误/缺失/故障控制
```

只将单个 `agent/<split>/<case-id>/` 目录交给 Agent。核验器拒绝该目录的额外文件、跨区完全相同的输入和越界/符号链接路径。目录分离是一项交接约定，尚未形成进程权限隔离；把整个仓库或数据集挂载给 Agent 会泄漏参考答案。

`bundle.json` 绑定完整确认合同（包括确认记录）、原始输入、规范化场景文件及生成/核验源码指纹。M2 的 JSON 文件哈希采用 UTF-8、键排序、两空格缩进和末尾换行；M1 审查哈希采用紧凑 JSON 并排除确认记录。二者不能互换。源码发生变化后，需要检出匹配版本核验旧包，或构建新包。哈希检测内容变化，不认证身份，也不抵御攻击者同时替换代码、合同和哈希。

## 场景覆盖与分区

| 场景族 | 每个来源组的变体 | 验证目标 |
|---|---|---|
| 正常 | baseline、reordered、excluded_orders、outside_period | 行序与无关订单不改变月度金额、变化率或分组贡献。 |
| 边界 | empty、zero_baseline、zero_current、full_refund、no_paid | 缺数据、零分母、零销售、退款与状态筛选语义。 |
| 异常 | duplicate_order、mixed_currency、missing_amount、excessive_refund、invalid_date、unknown_status、negative_amount、invalid_precision、missing_dimension、missing_column | 返回确定的问题代码，禁止编造数值结果。 |

开发集从传入 CSV 生成；校准集和保留集分别使用种子生成新的 13 行、21 行来源表，具有不同金额、订单 ID 和分组标签。同源变体全部留在同一区。空 CSV 不随来源变化，只保留在第一个选中分区，因此默认是 **19 + 18 + 18 = 55** 场景：正常 12、边界 13、异常 30。默认样例其中 24 个可计算、31 个应澄清。

这些分区共享公开的场景模板，是合成的分区机制验证；不是隐藏的真实业务保留集，不能据此推断总体可靠性或统计置信区间。来源组标记和字节去重也不等同于业务语义去重。

## 两条参考计算路径

1. [参考生成器](../src/lean4_agent_eval/sales_reference.py)：CSV 字典读取 → Decimal 解析金额 → 整数汇总 → Fraction 精确变化率 → Decimal 展示舍入。
2. [独立复算器](../src/lean4_agent_eval/sales_reference_sql.py)：CSV 位置读取 → 字符串拆分为整数分 → SQLite `SUM/GROUP BY` → gcd 分数 → 整数除法舍入。它不调用或导入参考生成器。

两条实现必须逐字段一致，包括输入哈希、状态、问题代码、月度总额、差额、精确比例、每个维度的分组贡献、纳入数量、展示字符串和逐行记录。非法输入的逐行记录可能不完整，不能据此计算销售结论。`row_number` 是逻辑 CSV 记录序号加表头偏移，不是包含多行引号字段时的物理文件行号。金额全程避免二进制浮点误差，展示用两位小数和 ROUND_HALF_UP，避免 `-0.00%`。

同一个问题的两个实现仍可能共享错误假设。手算基准、元/分小数案例、变形不变性、异常预期、篡改参考与故障注入测试进一步约束结果；它们提供工程证据，不是形式证明或数据真实性保证。

## 评分器与合同覆盖

[sales-analysis.schema.json](../schemas/sales-analysis.schema.json) 定义严格的数值/澄清封套：正常输入提供月度金额、分组、精确比例等；异常输入只提供问题代码。它尚未定义完整分析叙述、引用和因果边界，也不能替代整个 `analysis.json` 的业务验收。精确比例允许等价分数。

| 控制结果 | 默认数量 | 解释 |
|---|---:|---|
| PASS | 12 | 正确分析、合理澄清及正确的合成 PPT 提取字段。 |
| FAIL | 39 | 错金额/币种/分组/输入指纹/比例、零基期虚假增长、错澄清、关键词堆砌、错 PPT 单位/页数。 |
| UNKNOWN | 6 | 未提供分析或 PPT 提取证据。 |
| ERROR | 3 | 模拟评估器提取故障；不是被测 Agent 业务错误。 |

每个选中分区含 20 个控制，构建与核验都要求实际评分结果匹配预期，不能用空控制集通过。控制候选均标为合成评估器夹具，未由真实 Agent 产生。缺失候选这里只代表没有观测证据；M3 若确认运行结束且应交文件确实不存在，应按合同判 FAIL。

| 合同要求 | M2 覆盖 |
|---|---|
| R01 数据范围与口径 | 输入规则、数值筛选和输入指纹；未验运行来源和 trace。 |
| R02 金额与贡献 | 月度总额、差额、精确比例、每个分组及总和。 |
| R03 结论依据 | 未验；待真实分析内容与证据。 |
| R04 文件交付 | 只检查合成提取字段中的页数；未打开实际 PPT。 |
| R05 跨产物一致性 | 只检查合成 PPT 汇总数值、单位、月份、语言等字段。 |
| R06 权限与副作用 | 未验；待 Runner/工具边界。 |

所有局部评分回执保留 `full_contract_verdict: NOT_ASSESSED`、`formal_verification: NOT_PROVED`。不存在“55 个 Agent 任务通过”或“PPT 全部通过”的结果。后续衔接见 [架构](architecture.md) 与 [验证边界](verification-boundary.md)。
