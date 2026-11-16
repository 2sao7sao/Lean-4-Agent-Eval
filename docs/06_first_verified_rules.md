# 第二课：从草稿到实际通过检查的规则

更新：2026-11-15（本地日期）。本轮已安装项目内的 Lean 4.35.0，固定版本，并运行证明构建、公理审计、证明导出与复核。完整命令、输出和源码哈希见 [验证记录](../evidence/formal_verification.json)。

## 这次建立了什么

第一部分是[金额检查器](../Lean4Agent/TotalCheck.lean)：金额用整数“分”表示，支持负数退款。我们证明了检查通过时申报额等于合计，正确申报会被接受，以及分组求和与整体求和一致。

第二部分是[验收汇总器](../Lean4Agent/Verdict.lean)：它接收每条必检规则的结果，根据明确规则形成整体结论。

| 输入情况 | 整体结果或约束 |
|---|---|
| 非空清单，所有项目 PASS | PASS |
| 含 FAIL | FAIL，即使同时存在 ERROR |
| 无 FAIL，但含 ERROR | ERROR |
| 无 FAIL／ERROR，但含 UNKNOWN | UNKNOWN |
| 没有任何必检项 | UNKNOWN |
| 合同要求某个项目，但没有该项目结果 | 不能 PASS |

最后一行很重要。如果让 agent 自己选择提交哪些检查结果，它可能只提交好看的部分。`evaluateRequired` 先读取合同里的必检 ID，再查询每个 ID 的结果；没有结果就按 UNKNOWN 处理。额外提交其他 PASS 不能替代缺失的必检结果。

## 读懂一个真正的定理

```lean
theorem aggregate_pass_iff (vs : List Verdict) :
    aggregate vs = .pass ↔ vs ≠ [] ∧ ∀ v ∈ vs, v = .pass
```

可以逐段读：

- `vs : List Verdict`：vs 是一份检查结果列表。
- `aggregate vs = .pass`：这份列表的整体判断是通过。
- `↔`：当且仅当，两个方向都成立。
- `vs ≠ []`：至少有一个检查项目。
- `∀ v ∈ vs, v = .pass`：列表中的每个结果都是通过。

它表达的是：**对任意有限的合法结果列表，整体通过，当且仅当清单非空且每项通过。**

这比“试过几组状态，程序似乎没问题”更强，因为命题覆盖定义中的所有有限列表。但它仍要求输入确实来自全部必检项目，并且每个单项判断本身可靠。

因此，我们进一步证明了 `missing_required_blocks`：只要合同要求某个 ID，而结果查询中没有它，`evaluateRequired` 就不能给出 PASS。这保护的是清单覆盖，不会证明合同本身没有漏掉用户需求。

## 实际检查结果

- 14 个命名定理通过构建，包括辅助定理。
- 传递公理审计只出现 `propext` 与 `Quot.sound`，都在标准允许列表中；没有 `sorryAx` 或自定义公理。
- 选定定理及其依赖导出后，分别通过默认 Lean kernel、paranoid kernel 和 lean4lean 的新进程复核。lean4lean 报告检查了 595 个声明，这包含依赖，不等于我们新写了 595 个定理。
- 错误合计、“UNKNOWN 仍然通过”、“漏掉必检项仍然通过”这 3 个错误命题均被拒绝。
- 使用 `sorry` 或人为公理的 2 个控制样例虽然能编译，却被公理策略判为不可接受。这说明构建成功不是唯一验收条件。
- 原 Python 离线实验的 11 个场景和 3 个边界检查再次通过。

Lean 区分定理含义、公理依赖和证明核验；官方指南也介绍了重新检查证明的方法。[Validating a Lean Proof](https://lean-lang.org/doc/reference/latest/ValidatingProofs/)

## 如何重现

在项目目录执行：

```sh
# 已完成安装的当前工作区可直接运行这一条
python3 scripts/check_proofs.py

# 新的 Apple Silicon Mac 工作区先安装固定工具链
python3 scripts/setup_lean.py

# 单独查看构建和公理依赖
sh scripts/lean.sh build
sh scripts/lean.sh env lean labs/AxiomAudit.lean
```

工具链保存在 `.tools/elan`；`lean-toolchain` 固定为 `leanprover/lean4:v4.35.0`。初次下载量较大，后续检查使用本地工具链。安装器版本和 SHA-256 固定在脚本中。检查不调用模型 API。

## 证据的准确边界

本机为 macOS，`lake check --from-export=... --paranoid` 的平台检查返回 exit 2，提示需要 `bwrap`／Linux namespaces。本轮使用的是工具链直接对导出文件进行核验的入口。没有完成“隔离构建并审查不可信第三方源码”的完整流程，也没有使用关闭沙箱的参数。

三个检查进程核验的是导出的形式化声明。项目源码到导出的对应由本地构建、明确的定理列表和记录的哈希支持；构建／导出工具及计算机实现仍在信任范围内。公理审计脚本针对当前项目结构编写，不是任意 Lean 工程的安全审计器。

这些证明不自动覆盖 Python 实现、CSV 解析、真实 trace 完整性、单项评分器的准确性、PPT 渲染或业务分析结论。`receipts : Nat → Option Verdict` 是形式模型中的查询函数；实际 JSON、数据库或文件到它的转换尚未接入。

## 我们接下来学什么

下一步把这条规则落到一个小型真实文件任务：给定 CSV 和报告，合同指定必检项目，运行器采集数据与输出，各检查器提交结果，再由汇总器判断。先做可复算的数字与溯源，之后扩展到 PPT 呈现和分析质量。

一个适合继续讨论的例子：合同要求“金额正确、引用来源、文件可打开”，系统只收到前两项 PASS。现在已经有形式化规则保证：在这个模型中，它不能整体通过。下一步需要解决的是，如何可靠地取得第三项结果，以及这三项是否足够表达用户真正的要求。
