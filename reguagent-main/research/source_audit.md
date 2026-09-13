# 来源审计与法律状态边界

审计日期：2026-09-08。此文件记录“本次真正读到了什么”；数据中 `verified` 只表示指定来源/片段已核对，不表示法律结论、机构适用性或控制有效性获批。全部要求保留 `record_status=needs_review`、`label_status=silver`，人工审核人和时间为空。

## 官方来源

| 主题 | 本次证据 | 已据此调整 | 仍待完成 |
|---|---|---|---|
| EBA ESG | 在官方域名 PDF 阅读器逐页核对最终稿第 17、22、23、27、29、32 页；[官方指南页面](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/sustainable-finance/guidelines-management-esg-risks)、[最终 PDF](https://www.eba.europa.eu/sites/default/files/2025-01/fb22982a-d69d-42cc-9d62-1023497ad58a/Final%20Guidelines%20on%20the%20management%20of%20ESG%20risks.pdf) | 把复合要求拆为较窄的段落级意译；区分监管要求、适用机构条件和实施日期的引用 | 未保存官方 PDF 字节副本；完整咨询稿—最终稿 diff 未执行；未核对爱尔兰主管机构最新 comply/explain 明细；机构级法律判断待审核 |
| Instant Payments / VoP | [CBI 官方说明](https://www.centralbank.ie/consumer-hub/explainers/how-can-i-send-a-payment-from-my-bank) 可读，解释 VoP 同时涉及 standard 与 instant SCT，及 2025-10-09 日期 | 纠正把 standard SCT 或 API 直接视为范围外的暗示；移动端是已给定的合成缺口，standard/API 保留未知 | [2024/886 正文](https://eur-lex.europa.eu/eli/reg/2024/886/oj/eng) 本次未取得可用全文；准确条件、例外及条文时效待复核。CBI 说明不替代正文 |
| DORA | 原数据提供 [2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj/eng) 等官方定位，但本次 EUR-Lex 返回空响应/无法读取 | 删除登记册义务与未经充分证实的统一报送截止日期绑定；区分一般 ICT 功能识别与关键功能的额外映射；保留例外条件 | Article 8、28、64 及相关技术标准的现行正文、范围和具体报送安排仍待核对；更改后的表述是待复核候选，未升级为 verified |
| FRTB / CRR | 阅读欧委会 [C(2026)3647 文件](https://finance.ec.europa.eu/document/download/d7962418-d7d8-4d03-a999-ec760637a67c_en?filename=crr-delegated-act-2026-3647_en.pdf)，其日期为 2026-06-04，并仍有 EU 编号占位；既有 CRR/延期来源未完成现行合并审计 | 将 adoption 与 OJ publication/in-force 分开；停用原始小交易账簿阈值自动规则；保留“补当前头寸与法律证据”的行动 | 截止研究日的 OJ 发布/生效状态、现行 Article 94 全部条件、最新完整头寸及银行账簿 FX/商品风险均待确认；不能只因没有交易台判定全面豁免 |

上述 DORA 和 FRTB 记录的保留日期/候选描述不是本次完成现行法律审定的证明。尤其 FRTB 不将旧归档 Q&A 的数值照搬进当前规则，也不把采用 `OR` 的旧阈值表达式换个数就继续自动执行。

## ESG 精确定位

| 位置 | 支持的内容 | 对应数据 |
|---|---|---|
| 第 17 页 §8 | 指南收件/适用机构的定义入口 | 每条 ESG 要求的 SCOPE citation |
| 第 17 页 §10 | 一般机构 2026-01-11；SNCI 最迟 2027-01-11 | DATE citation；`snci_status` 为显式合成分类，不能凭单期资产表自行推断 |
| 第 22 页 §27 | 识别 ESG 数据缺口、影响、补救及估计/代理值依赖 | `REQ-ESG-DATA-GAPS-001` |
| 第 23 页 §29 | 非大型企业对手方所需数据的选择、比例性与 §28 的关系 | `REQ-ESG-DATA-SELECTION-001`；没有把大型企业清单强制复制给所有 SME |
| 第 27 页 §44、§45 | 融入日常风险框架；短中长期及至少十年的长期视角 | `REQ-ESG-RISK-INTEGRATION-001`、`REQ-ESG-LONG-HORIZON-001` |
| 第 29 页 §50、§51 | 风险偏好与相应指标 | `REQ-ESG-RISK-APPETITE-001`、`REQ-ESG-RISK-KRI-001` |
| 第 32 页 §68、§69 | 授信准入标准、信用监测与重要组合的环境风险指标 | `REQ-ESG-CREDIT-POLICY-001`、`REQ-ESG-CREDIT-MONITORING-001` |

保存的是意译和定位，不是拼接后伪装的逐字引文。§27/29 也不能反推本银行有多少客户具备能源数据；这个事实单独进入访谈缺失清单。

版本配对登记在 [version_pairs.json](../data/calibrated_v0_2/regulatory_sources/version_pairs.json)。旧版是 EBA/CP/2024/02 咨询稿，新版是 EBA/GL/2025/01 最终指南；二者法律状态不同。咨询期信息可以从 [EBA 咨询页面](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/sustainable-finance/guidelines-management-esg-risks?phase=consultation) 核对，但没有因此宣称已读完两个全文或已算出变更。

## 本地 bunq 参考的处理

已从用户提供的五份 PDF 提取文本，保存在 [source_text](source_text/)；文件哈希与用途在 [bunq_reference_registry.json](../data/calibrated_v0_2/reference_only/bunq_reference_registry.json)。哈希只能标识本地副本，尚未与出版方下载逐字节核对。

可借鉴的例子包括：[2025 年报](<../data/bunq_reference bank/bunq-report-annual-2025-en.pdf>) PDF 第 43 页的三道防线结构和第 79 页的人员/费用披露；[Pillar 3](<../data/bunq_reference bank/bunq-report-pillar-3-disclosures-2025-en.pdf>) 第 10、24、33 页的风险治理；[ESG 报告](<../data/bunq_reference bank/bunq-report-esg-2025-en.pdf>) 第 16、23 页的 ESG 与治理安排。页码为 PDF 文件页序，从 1 开始。

年报披露的 2025 平均 FTE 658 属于 bunq；Northstar 场景是 1,150 FTE。旧成本表混入的真实银行公开费用已归档至 `reference_only/legacy_operational_costs.csv`，不再作为 Northstar 行动成本输入。云基础设施、风险角色和报告结构可以启发合成设计，不能证明 Northstar 使用了某供应商或已经通过某项控制。

## 检索完整性与审批限制

[retrieval_log.json](retrieval_log.json) 保留下载尝试结果：GitHub 文档保存成功；EBA 下载返回 403；EUR-Lex 的零字节响应标为 `empty_response_not_a_source_snapshot`。空响应的哈希只记录在尝试日志中，不写进法规的 `content_sha256`，也不作为已保存正文。

浏览器可阅读 EBA 最终稿，但浏览器安全策略阻止下载页面访问，自动审批随后拒绝了 PDF 保存动作，理由是该动作被视为绕过下载限制。已停止保存尝试，后续只读核对。由此保留的限制是“缺少可复现全文快照”，不是虚构一个本地 PDF 或声称下载成功。

后续补齐时，需要合法取得两个官方全文、记录版本/生效状态与 SHA-256，再计算差异并审核义务级变化。当前结构校验通过不能消除这一来源缺口。
