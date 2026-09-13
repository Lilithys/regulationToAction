# Northstar 校准数据 v0.2

版本：0.2.1；场景/研究截止：2026-09-08。Northstar 是虚构的爱尔兰数字银行，bunq 仅为真实同业参考。此目录由原始四组文件重建，不修改 `data/person1`—`person4`。

主线是 SME 存量授信的 ESG 监测：`REQ-ESG-CREDIT-MONITORING-001`，关联数据缺口要求，覆盖 Lending、Risk、Data/IT、Finance、Compliance。IPS、DORA、FRTB 保留为辅助场景。本版只选取部分义务，不代表四套法规完整覆盖。

## 内容

| 层 | 记录规模 | 用法 |
|---|---:|---|
| 实体与业务 | 1 银行、6 业务线、13 产品 | 合成机构事实；业务线可重叠，不跨线累加余额 |
| 敞口 | 22 授信组合组、12 抵押案例、12 支付汇总行、3 持仓行、14 ESG 数据状态行 | 先看粒度、日期和分母，再计算 |
| 监管 | 4 变化、11 来源、18 原子要求、1 待补全文的版本配对 | 来源定位与候选解释；全部要求需人工审核 |
| 治理与运营 | 4 政策、5 控制、5 程序；17 流程、18 系统、12 数据资产、8 供应商、5 关键功能/映射记录 | 稳定 ID 连接；当前控制有效性未知 |
| 组织与经济 | 13 角色、7 成本中心、8 角色产能行、3 响应方案 | 显式人天/费用/自动化假设；团队交付产能待确认 |
| 开发评测 | 12 silver 用例、5 参考行动、11 待收集证据、1 模拟访谈 | 只供开发者/评测器；不是模型运行时输入或正式测试集 |

`08_evidence/actions.json` 和 `evidence_register.json` 初始为空，表示 agent 尚未生成行动、尚未收集证据。可供人审阅的示例计划在 [evaluation_ground_truth/reference_actions.json](evaluation_ground_truth/reference_actions.json)，证据清单在 [reference_evidence.json](evaluation_ground_truth/reference_evidence.json)。这些示例没有被批准或执行。

## 重建、验证和计算

在工作区根目录使用 Python 3.10+；新脚本仅用标准库。重建先在临时目录生成并验证，再备份与发布；未合并的本地修改会阻止覆盖。指定 `--build-timestamp` 可复现相同文件。人工矩阵位于工作区 `config/`，运行输出位于 `runs/`。

```bash
python3 scripts/calibrate_dataset.py
python3 data/regulatory-governance-dataset/scripts/validate_person1_data.py --root calibrated_v0_2 --strict
python3 scripts/validate_dataset.py
python3 -m unittest discover -s scripts -p 'test_dataset_runtime.py' -v
python3 scripts/dataset_runtime.py --output runs/demo_calculations.json
```

最新验证见 [M1 实施报告](../research/m1_implementation_2026-09-12.md)。`calibration/` 中旧校验/计算输出是历史记录。结构检查不等于法律准确率，本轮没有调用 LLM 进行端到端评测。

## 给 agent 的输入

不要递归索引整个工作区。根目录构想、银行叙述和原始团队文档含预设答案；同业参考不应混入本行事实；开发答案必须单独保管。使用 [dataset_manifest.json](dataset_manifest.json) 和运行脚本的允许目录清单。

```bash
# 已有结构化义务与映射时：适用性、敞口和响应分析
python3 scripts/dataset_runtime.py --export-inputs assessment --output /tmp/northstar-assessment-inputs.json

# 抽取任务：去除整理好的 requirements 和治理映射
python3 scripts/dataset_runtime.py --export-inputs extraction --output /tmp/northstar-extraction-inputs.json

# 映射任务：去除预填的交叉链接、覆盖结论和关联方案
python3 scripts/dataset_runtime.py --export-inputs mapping --output /tmp/northstar-mapping-inputs.json
```

`extraction` 视图只是输入隔离机制：当前官方全文快照不足，因此不能用它宣称已经能独立复现法规抽取或版本差异。`assessment` 明确允许使用既有候选要求/映射，不应拿这个视图给“从零抽取/映射”打分。

可复用函数位于 [dataset_runtime.py](../scripts/dataset_runtime.py)：`portfolio_metrics`、`calculate_options`、`deadline_status`、`closure_gate`。最后一个函数只检查证据元数据和文件完整性；审核人的资质、真实身份与证据实质仍需要实际工作流确认。

## 当前边界

- 全部 18 条要求是 silver；不存在已获人工确认的 gold 标签。
- EBA ESG 指定段落已在官方 PDF 中目视核对；其他法规的现行正文及 FRTB OJ 状态仍需补审。两份官方全文未本地保存，`diff_status=not_computed`。
- 2026-06-30 等历史快照保留原日期，不包装为 9 月实时头寸。补救目标日与过去的法规适用日分开。
- `null` 表示未知；能源数据覆盖率、完整当前 FRTB 头寸、standard SCT/API VoP、团队交付产能、损失模型等不能按零处理。
- 最低成本不等于获批方案；运行结果的 `recommended_option_id` 保留空值。

依据和变更说明：[数据字典](DATA_DICTIONARY.md)、[校准报告](../research/calibration_report.md)、[来源审计](../research/source_audit.md)、[市场研究](../research/market_landscape_2026-09-08.md)。
