# v0.2 数据字典与集成约定

这是项目现有 Person 1 合同之上的跨组补充，不重命名其既有 schema。Person 1 文件继续使用 `schema_version=1.0` 的 envelope；整个数据包版本是 `dataset_version=0.2.1`。Person 2/4 的数组/对象和 Person 3 的 `_meta` envelope 保留，读取器按路径确定结构。

## 对象和关系

路径相对于 `calibrated_v0_2/`。`fact_ref` / `fact_path` 使用文件路径加可选 JSON Pointer；`#/` 后路径按 JSON Pointer 解释。原始文件 provenance 的 `source_file` 相对于原始 `data/` 根目录。参考登记的 `path` 相对于该登记文件所在目录。

| 文件 | 数据集合 / 主键 | 粒度、单位和含义 |
|---|---|---|
| `01_entity/bank_profile.json` | 单对象；`entity_id` | 合成法律实体、司法辖区、规模及分类。`snci_status=false` 是新增场景假设，不是资产阈值推导或律师结论 |
| `02_business/business_lines.json` | 数组；`business_line_id` | 组织/业务视角可重叠；客户数与余额不能无条件跨行相加 |
| `02_business/products.json` | 数组；`product_id` | 产品与渠道；VoP `unknown` 不等于 false 或不适用 |
| `03_exposure/lending_portfolio.csv` | `portfolio_record_id` | 一行一个 `portfolio_cohort`；余额为 EUR million；`borrower_count` 为组内客户数；PD/LGD 字段为百分数，不是 0—1 比率 |
| `03_exposure/esg_assessment_snapshot.csv` | `portfolio_record_id` | 14 个组合组的已给定合成数据状态；未覆盖某组不等于该组风险为零；已移走最终风险/优先级标签 |
| `03_exposure/mortgage_book.csv` | `mortgage_case_id` | 12 个 illustrative case；不是全量抵押组合，没有抽样权重，不能外推不良率；该表余额单位 EUR，与授信组合表的 EUR million 不同 |
| `03_exposure/payments.csv` | `payment_metric_id` | 选定月份/分段/渠道的汇总记录；`transaction_count` 是交易数；样本不完整，不按 12 行直接年化 |
| `03_exposure/trading_book.csv` | `position_id` | 3 个银行账簿持仓记录，市值 EUR million；文件名不代表其中都是交易账簿；不能证明完整市场风险范围 |
| `03_exposure/portfolio_summary.json` | 单对象 | 不重叠余额、全年基线与指标口径的独立登记 |
| `03_exposure/missing_facts.json` | `fact_id` | `value=null`、问题、拟访谈角色与原因；不是已答复的访谈记录 |
| `regulatory_sources/change_register.json` | `sources/source_id`；`changes/change_id` | 来源、发布/适用事件、变化候选；`content_sha256=null` 表示未保存可用原文件 |
| `regulatory_sources/requirements.json` | `requirements/requirement_id` | 原子要求、引用、条件、所需银行事实和候选覆盖映射 |
| `regulatory_sources/version_pairs.json` | `version_pair_id` | 咨询稿与最终稿的待取全文配对；不是已计算 diff |
| `04_governance/*.json` | `policies/policy_id`、`controls/control_id`、`procedures/procedure_id` | 政策意图、控制设计、执行步骤分别表示；`operating_status=unknown` 表示没有实操证据 |
| `05_operations/processes.json` | `processes/process_id` | 业务流程；`PROC-*` 与治理程序 `PRCD-*` 不是同一类对象 |
| `05_operations/systems.json` | `systems/system_id` | 合成系统及渠道、托管和数据关系 |
| `05_operations/data_assets.json` | `data_assets/data_asset_id` | 数据资产及已知限制，不是“存在文件就完整可信”的断言 |
| `05_operations/vendors.json` | `vendors/vendor_id` | 供应商与分包链已知状态；未识别的分包人口不能标记为映射完整 |
| `05_operations/critical_services.json` | `critical_or_important_functions/function_id` | 5 项关键/重要功能，使用现有 `CIF-*` ID |
| `05_operations/dependencies.json` | `dependency_mappings/dependency_mapping_id` | 5 组功能到流程、系统、数据、供应商的类型化关系；缺边可能是资料缺失 |
| `06_organisation/roles.json` | `role_id` | 合成岗位与责任线，非真人联系人；内部审计未给出的成本中心和独立替补保留空值 |
| `06_organisation/cost_centres.json` | `cost_centre_id` | 采用项目场景的 7 个中心；全年运行成本 EUR，不等于某项变更增量成本 |
| `06_organisation/raci.csv` | activity + role | 常设流程分工；行动示例 RACI 在评测目录，每项示例行动只有一个 A |
| `07_economics/operational_costs.csv` | `cost_centre_id` | 变更人日单价，EUR/person_day；情景约定一天 8 小时 |
| `07_economics/change_capacity.csv` | role + period | 2026-Q4 合成的指定角色额度；`remaining_days=available_days-committed_days`；不是完整交付团队产能 |
| `07_economics/response_options.json` | `option_id` | manual/automated/hybrid 的显式假设；成本为 EUR，自动化率 0—1，review_minutes 为单客户单次分钟数 |
| `08_evidence/*.json` | action/evidence 数组 | 初始为空，由实际 agent/工作流生成与收集；不载入参考答案 |

ID 沿用定义对象，Person 4 的旧引用通过 [id_crosswalk.json](calibration/id_crosswalk.json) 显式映射。一个旧宽泛数据集名映射到现有较窄对象，不代表语义完全等价；映射记录明确如此标注。Validator 只从定义表建立主键索引，不能靠在别处重复一个字符串让悬空引用“通过”。

## 数值口径

1. **资产勾稽**：consumer 4,700 + home improvement 1,100 + SME 2,300 + mortgages 1,100 = loans 9,200；再加 liquidity 3,000 + other assets 300 = total assets 12,500。单位统一为 EUR million。抵押案例表不是余额加总来源。
2. **SME NACE**：9 个 SME 组合组，合成客户数合计 10,000；缺失/宽泛 NACE 组客户数 2,000，因此 20%；对应余额 910/2,300，因此 39.5652%。这些客户计数是本次为使场景口径明确而新增的假设，不是 bunq 观测，也不是按余额估出的真实客户数。
3. **支付**：选中行合计 3,563,000 笔，mobile 占 75.1052%；独立全年场景基线是 8.6m instant payments 和 direct-channel mobile 71%。71% 的分母为 mobile + web，API 不在这个已知分母内。不要把样本差异修成数值相等。
4. **工作量**：当前成本模型覆盖 10,000 个存量 SME 客户每年一次审核；32,000 年申请量属于另一工作流，没有叠加进该模型。
5. **费用**：Lending 52 EUR/hour × 8 = 416/day；Risk、Compliance 68 × 8 = 544/day；IT 850/day。Finance 的 544、Payments/Mortgage 的 416 是本次明确的类比假设。采用这些价格并不意味着工资、FTE 或 bunq 费用可直接互换。

成本计算：

```text
setup = Σ(各成本中心实施人天 × 人日价格)
        + technology_setup + data_vendor_setup + training_setup + legal_setup
annual_manual = SME客户数 × (1 - automation_rate)
                × 单次审核分钟 / 60 × Lending小时成本
annual_run = annual_manual + annual_fixed_run
three_year_TCO = setup + 3 × annual_run
```

low/base/high 使用 20/30/45 分钟，属于敏感性情景，不是统计置信区间。TCO 为一次建设加三个完整稳态运营年、未折现；没有建模实施爬坡期现金流、税费/通胀或全部经济收益。annual_fixed_run 是额外固定运行项，已计入 annual_run，不能重复加总。自动化率表示减少人工处理的假设，不是控制有效性或合规概率。

## 时间、来源和状态

| 字段/概念 | 解释 |
|---|---|
| 包级 2026-09-08 | 数据校准/研究截止日；不改写历史业务快照为实时事实 |
| `snapshot_date` / `assessment_as_of_date` | 数据实际场景快照日；判断当前适用性时应检查陈旧程度 |
| `publication` / `adoption` / `application` | 发布、采用、适用分别记录；发布日期不自动等于生效/适用日 |
| `regulatory_due_date` | 保留法规日期与审核状态；不是内部项目承诺 |
| `target_date` | 未批准的内部补救计划日期；不延长原法规期限 |
| `synthetic=true` | 合成机构事实或假设，不代表“已经验证的真实银行事实” |
| citation `verified` | 本次实际可读片段的核对状态；不提升整个 requirement 为人工审定 |
| `evidence_status=verified` 的银行文件引用 | 文件/字段存在于合成数据中；不代表对应法规条件和控制有效性成立 |
| `silver` / `needs_review` | 模型/分析整理的开发标签，待合资格审核；本版没有 gold |
| JSON `null` / CSV 空字段 | 缺失或未知；不是 false、0、不适用。各 CSV 列需按合同解析，不使用字符串 truthiness |
| `required` evidence | 需要收集的证据，不是已收集或接受；不能据此结案 |

## 输入、答案、参考三者分离

`assessment` 视图允许已有要求和覆盖候选，供后续影响分析；`extraction` 去除准备好的要求及治理记录；`mapping` 去除准备好的 ID 链接、覆盖标签和关联选项。具体允许目录由脚本和 manifest 双重限制。

`evaluation_ground_truth/` 的目录名为兼容已有项目习惯保留，里面实际是 **silver development labels**，不是 gold。模拟访谈给出的 65% 只能在明确的测试事件中注入，不能回填为已从负责人取得的事实。`reference_only/` 仅供开发者阅读；`calibration/` 包含可推导答案与校验结果，也不进入运行上下文。

未来建立正式评测时，应独立人工审核标注、冻结来源快照，并按版本和义务家族划分留出集。本版的 12 个开发案例不足以训练或报告可靠的模型泛化表现。


## M1 合同补充（0.2.1）

- 唯一数据根目录由 `scripts/project_paths.py` 定义。人工矩阵在 `config/`；案件答复和运行输出不写回 baseline。
- `extensions.snci_selector` 属于日期事件；不作为排除机构的条件。`extensions.jurisdiction_basis` 区分机构范围与产品地域。
- 适用性结果分别包含 `legal_scope`、`temporal_status`、`demo_scope`、`review_status`；`unresolved_product_ids` 不可忽略。`application_date_reached` 不代表获得法律批准。
- `evidence_references` 使用 `{path, pointer}` 或 `{path, id_field, record_id}`；不可把数组内记录 ID 当成 JSON Pointer。
- 要求的 `extensions.coverage_criteria` 与控制的 `extensions.requirement_mappings` 是待审核的具体判据和支持范围；`mapping_review` 保存撤回支持链接的原因，旧注释归档在 `superseded_mapping_annotations`。这些不是新造的控制事实，也不是全面合规判定。
- 覆盖结果分为 `mapping_support`、`design_coverage`、`operating_evidence`。运行证据必须解析到实际记录/文件，绑定要求、控制、测试判据、内容 hash、审核与有效日期；具体人工身份、内容判断和任务状态服务由后续阶段实现。
- 主输出为 `portfolio-facts-v1`。稳定业务单位为产品×行业×经营国家；保留 `source_record_ids`。数据质量类别不自动转换成实际 ESG 数据点的覆盖百分比；国家有效也不代表资产地点/物理风险数据充分。
- 可选 `esg-priority-v2` 只用于合成调查优先级，维度为 transition_risk、physical_risk、review_urgency；不再将余额份额重复加入分数。`field_quality_index` 是非概率的字段质量指标，`risk_confidence=null`；原 materiality/concentration 方法的人工确认不自动迁移到新方法。
- `calibration/build_manifest.json` 记录生成文件和构建输入 hash。更改 baseline 后应先审查并迁移修订；不要仅重写 hash 来绕过差异检查。
