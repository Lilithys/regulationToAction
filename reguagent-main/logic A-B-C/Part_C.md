# ESG Part C: Capability Gap, Action Priority And Evidence Design

## 1. Purpose / 目标

Part C converts the ESG requirement and Part A/B assessment results into a bank-specific remediation plan.

Part C 将 ESG requirement 和 Part A/B 的 assessment result 转化为 Northstar 专属的整改行动计划（remediation plan）。

```text
New regulatory requirement
-> required bank capability
-> current evidence assessment
-> Missing / Partial / Evidenced gap
-> prioritised action plan
-> evidence-based closure decision
```

It does **not** issue legal advice or decide whether Northstar has breached a rule. It evaluates whether the bank has sufficient evidence that its current capabilities meet a reviewed requirement.

它不提供法律意见，也不判断 Northstar 是否违法。它只判断：针对已经 human-reviewed 的 requirement，银行是否有足够 evidence 证明其现有 capability 满足该 requirement。

## 2. Demo Scope / Demo 范围

### In Scope / 纳入范围

```text
Bank: Northstar Digital Bank plc
Portfolio: SME working-capital loans
Requirement family: EBA ESG-risk management
Functions: SME Lending, Credit Risk, Data/IT, Compliance
```

### Out Of Scope / 不纳入范围

```text
Legal interpretation of the full EBA Guidelines
Individual borrower credit approval decisions
External ESG vendor selection
Production-grade climate scenario modelling
Automatic closure without human compliance approval
```

The EBA Guidelines require institutions to identify, measure, manage, and monitor ESG risks. This demo uses three human-reviewed synthetic requirements derived from that requirement family. [EBA Guidelines on the management of ESG risks](https://eba.europa.eu/publications-and-media/press-releases/eba-publishes-its-final-guidelines-management-esg-risks)

## 3. Human-Reviewed Demo Requirements / Demo 使用的审核后要求

These are prototype requirements, not a substitute for legal interpretation.

| Requirement ID | Human-reviewed requirement / 审核后的 requirement | Required capability / 所需能力 |
| --- | --- | --- |
| `REQ-ESG-001` | Identify material ESG risk drivers in SME credit exposures. | Sector, geography, exposure, and risk-driver data |
| `REQ-ESG-002` | Measure and monitor ESG risk in the material SME portfolio on a recurring basis. | Approved methodology, thresholds, monitoring report, data-quality control |
| `REQ-ESG-003` | Maintain governance and controls that evidence ESG risk management. | Approved policy, accountable owner, control testing, compliance sign-off |

## 4. Inputs And Data Contract / 输入与数据接口

Part C consumes outputs from Parts A and B, plus governance and organisation records.

| Input | Minimum fields / 最小字段 | Example source |
| --- | --- | --- |
| Applicability result | `requirement_id`, `applicability`, `in_scope_products` | Part A output |
| Exposure result | `exposure_score`, `confidence_score`, `data_debt_score`, `affected_exposure` | Part B output |
| Portfolio data | `portfolio_record_id`, `outstanding_balance`, `nace_code`, risk bands, review date | `lending_portfolio.csv` |
| ESG assessment data | screening status, sector data quality, ESG-data status, follow-up | `esg_assessment_snapshot.csv` |
| Current capabilities | `capability_id`, `status`, `evidence_ids`, `last_review_date` | `04_governance/controls.json`, `policies.json`, `procedures.json` |
| Ownership | `owner_id`, role, function, cost centre | `06_organisation/roles.json`, `raci.csv` |
| Delivery assumptions | person-days, daily rate, deadline, capacity | `07_economics/operational_costs.csv`, `change_capacity.csv` |
| Evidence records | `evidence_id`, type, status, approval date | `08_evidence/evidence_register.json` |

If an input record is absent, the model must return `insufficient_evidence`; it must not assume that the capability exists.

如果某项输入记录不存在，模型必须返回 `insufficient_evidence`，不能假设银行已经具备该 capability。

## 5. Capability Catalogue / 能力目录

Part C evaluates the following six capabilities.

| Capability ID | Capability / 能力 | Requirement link | Northstar current demo state |
| --- | --- | --- | --- |
| `CAP-ESG-SECTOR-DATA` | Reliable sector/NACE classification for material SME borrowers | `REQ-ESG-001` | Partial: valid, broad, and missing classifications coexist |
| `CAP-ESG-RISK-DATA` | ESG risk-driver data: transition, physical-risk, and transition-plan evidence | `REQ-ESG-001` | Partial: many values are proxies or missing |
| `CAP-ESG-METHODOLOGY` | Approved method to score and aggregate portfolio ESG risk | `REQ-ESG-002` | Missing |
| `CAP-ESG-MONITORING` | Recurring ESG portfolio monitoring and threshold escalation | `REQ-ESG-002` | Missing |
| `CAP-ESG-POLICY` | Portfolio-wide ESG-risk policy | `REQ-ESG-003` | Missing |
| `CAP-ESG-GOVERNANCE` | Named owner, control test, and compliance sign-off | `REQ-ESG-003` | Partial: owners exist, but ESG-specific control evidence does not |

## 6. Capability Status Logic / 能力状态判断逻辑

### 6.1 Status Values / 状态定义

| Status | Rule / 规则 | Meaning / 含义 |
| --- | --- | --- |
| `evidenced` | Required evidence exists, is current, covers the requirement, and control test passes. | 已有可验证能力 |
| `partial` | Some evidence exists, but coverage, quality, scope, or review frequency is insufficient. | 有部分能力，但不能证明满足 requirement |
| `missing` | No relevant approved evidence exists. | 缺少能力 |
| `insufficient_evidence` | The system cannot find enough facts to determine the status. | 信息不足，不得推定合规 |

### 6.2 Generic Decision Rule / 通用判断规则

```text
IF applicability != Direct
THEN capability assessment = Not required for this demo scope

IF approved evidence exists
AND evidence covers the required scope
AND evidence is current
AND required control test = Pass
THEN status = Evidenced

ELSE IF some relevant evidence exists
THEN status = Partial

ELSE IF required evidence sources are available but contain no supporting record
THEN status = Missing

ELSE status = Insufficient evidence
```

### 6.3 ESG Data-Coverage Rule / ESG 数据覆盖规则

The data capability is assessed by **exposure-weighted coverage**, not simply record count.

```text
Valid NACE coverage =
sum(outstanding exposure with valid NACE)
/ sum(total SME outstanding exposure)

Complete ESG assessment coverage =
sum(outstanding exposure with complete ESG screening)
/ sum(total SME outstanding exposure)
```

Suggested prototype thresholds:

| Measure | Evidenced | Partial | Missing |
| --- | ---: | ---: | ---: |
| Valid NACE coverage by SME exposure | >= 95% | 1-94% | 0% |
| Complete ESG assessment coverage by SME exposure | >= 90% | 1-89% | 0% |
| High-materiality borrowers with valid NACE | 100% | 1-99% | 0% |
| High-materiality borrowers with ESG review | 100% | 1-99% | 0% |

`broad_nace` and `missing_nace` do not count as valid NACE for this prototype.

`broad_nace` 和 `missing_nace` 在本 prototype 中不视为 valid NACE。

## 7. Gap Determination / 缺口识别

### 7.1 Requirement-To-Capability Matrix / 要求到能力的映射

| Requirement | Required capabilities | Initial demo result |
| --- | --- | --- |
| `REQ-ESG-001` | `CAP-ESG-SECTOR-DATA`, `CAP-ESG-RISK-DATA` | Partial |
| `REQ-ESG-002` | `CAP-ESG-METHODOLOGY`, `CAP-ESG-MONITORING` | Missing |
| `REQ-ESG-003` | `CAP-ESG-POLICY`, `CAP-ESG-GOVERNANCE` | Missing / Partial |

### 7.2 Expected Initial Gaps / 预期初始缺口

| Gap ID | Gap type | Description / 描述 | Evidence basis / 证据基础 |
| --- | --- | --- | --- |
| `GAP-ESG-DATA-001` | Data gap | Material SME exposure has broad or missing NACE/ESG data. | `PORT-SME-003`, `004`, `007`, `008`; ESG snapshot |
| `GAP-ESG-METHOD-001` | Methodology gap | No approved portfolio ESG scoring and aggregation methodology. | No methodology evidence record |
| `GAP-ESG-MONITOR-001` | Control gap | No recurring ESG monitoring control or control-test result. | No ESG monitoring control evidence |
| `GAP-ESG-POLICY-001` | Policy gap | No approved portfolio-wide ESG risk policy. | No approved ESG policy evidence |

## 8. Action Priority Model / 行动优先级模型

### 8.1 Priority Formula / 优先级公式

```text
Action priority score =
  35% deadline pressure
  + 30% exposure materiality
  + 20% gap severity
  + 15% dependency impact
```

The action score is a prioritisation tool. It is not a regulatory risk rating and not a legal conclusion.

该分数用于 action prioritisation，不是监管风险等级，也不是法律结论。

### 8.2 Deterministic Input Conversion / 输入转换规则

| Driver | Condition | Score |
| --- | --- | ---: |
| Deadline pressure | Requirement overdue or due within 90 days | 100 |
|  | Due within 91-180 days | 70 |
|  | Due within 181-365 days | 40 |
|  | More than 365 days | 20 |
| Exposure materiality | Exposure band = High / Material / Potential / Monitor | 100 / 70 / 40 / 10 |
| Gap severity | Missing / Partial / Insufficient evidence / Evidenced | 100 / 60 / 70 / 0 |
| Dependency impact | Blocks 3+ capabilities / blocks 1-2 / standalone | 100 / 60 / 20 |

### 8.3 Priority Bands / 优先级分级

| Score | Priority | Required response / 要求的响应 |
| ---: | --- | --- |
| 81-100 | P1 | Start immediately; executive escalation required. / 立即启动并升级汇报。 |
| 61-80 | P2 | Start in current change window. / 当前变更周期启动。 |
| 41-60 | P3 | Include in planned remediation. / 纳入计划整改。 |
| 0-40 | P4 | Monitor only. / 仅监控。 |

### 8.4 Dependency Rules / 依赖逻辑

```text
ESG data remediation
-> enables methodology calibration
-> enables portfolio monitoring

ESG methodology approval
-> enables monitoring thresholds

ESG policy and governance approval
-> enables formal control ownership and sign-off
```

Actions may be started in parallel, but `ACT-ESG-MONITORING-CONTROL` cannot be verified until data coverage and methodology evidence are sufficient.

行动可以并行启动，但 `ACT-ESG-MONITORING-CONTROL` 在 data coverage 和 methodology evidence 足够之前不能变成 `Verified`。

## 9. Action Catalogue / 行动目录

| Action ID | Addresses / 解决缺口 | Accountable owner | Delivery owners | Dependency | Initial priority |
| --- | --- | --- | --- | --- | --- |
| `ACT-ESG-DATA-REMEDIATION` | `GAP-ESG-DATA-001` | Head of Credit Risk | Data/IT, SME Lending | None | P1 |
| `ACT-ESG-METHODOLOGY` | `GAP-ESG-METHOD-001` | Head of Enterprise Risk | Credit Risk, Model Risk | Data remediation inputs | P1 |
| `ACT-ESG-POLICY-CONTROL` | `GAP-ESG-POLICY-001`, `GAP-ESG-MONITOR-001` | Chief Compliance Officer | Compliance, Risk | Methodology design | P1 |
| `ACT-ESG-MONITORING-CONTROL` | `GAP-ESG-MONITOR-001` | Head of Credit Risk | Risk Reporting, Data/IT | Data + methodology + policy | P2 |

### 9.1 Recommended Initial Action / 推荐的第一行动

```text
Recommended action: ACT-ESG-DATA-REMEDIATION

Why:
- High data debt prevents Northstar from reliably classifying part of the SME portfolio.
- The data gap blocks both methodology calibration and recurring monitoring.
- The action is concrete, measurable, and easy to demonstrate in seven minutes.
```

## 10. Evidence Closure State Machine / 证据闭环状态机

```text
Draft
-> Assigned
-> In progress
-> Evidence submitted
-> Control tested
-> Compliance approved
-> Verified
```

### 10.1 State Transition Rules / 状态转移规则

| From | To | Mandatory condition / 必要条件 |
| --- | --- | --- |
| Draft | Assigned | Accountable owner and due date exist |
| Assigned | In progress | Delivery owner accepts task |
| In progress | Evidence submitted | Required evidence artifacts are attached |
| Evidence submitted | Control tested | Control owner performs test |
| Control tested | Compliance approved | Test passes and compliance reviewer approves |
| Compliance approved | Verified | All closure rules are satisfied |

### 10.2 Closure Rules By Action / 各行动的完成条件

#### `ACT-ESG-DATA-REMEDIATION`

```text
Verified only when:
- valid NACE coverage >= 95% of SME exposure;
- 100% of high-materiality SME exposures have valid NACE;
- complete ESG assessment coverage >= 90% of SME exposure;
- data-quality control test = Pass;
- compliance sign-off exists.
```

#### `ACT-ESG-METHODOLOGY`

```text
Verified only when:
- methodology document is approved;
- sector, geography, transition, physical-risk, and data-quality inputs are defined;
- scoring thresholds are versioned;
- Model Risk review is recorded;
- Compliance sign-off exists.
```

#### `ACT-ESG-POLICY-CONTROL`

```text
Verified only when:
- ESG-risk policy is approved;
- policy references the portfolio scope and methodology;
- control owner and control frequency are assigned;
- control test = Pass;
- Compliance sign-off exists.
```

## 11. Part C Output Schema / 输出结构

```json
{
  "assessment_id": "ASM-ESG-2026-001",
  "requirement_id": "REQ-ESG-001",
  "applicability": "direct",
  "exposure_score": 72,
  "confidence_score": 64,
  "capability_assessments": [
    {
      "capability_id": "CAP-ESG-SECTOR-DATA",
      "status": "partial",
      "evidence_record_ids": ["PORT-SME-003", "PORT-SME-004", "PORT-SME-007", "PORT-SME-008"],
      "gap_id": "GAP-ESG-DATA-001"
    },
    {
      "capability_id": "CAP-ESG-METHODOLOGY",
      "status": "missing",
      "evidence_record_ids": [],
      "gap_id": "GAP-ESG-METHOD-001"
    }
  ],
  "recommended_action": {
    "action_id": "ACT-ESG-DATA-REMEDIATION",
    "priority": "P1",
    "priority_score": 91,
    "accountable_owner": "ROLE-HEAD-CREDIT-RISK",
    "required_evidence": [
      "NACE remediation log",
      "data-quality report",
      "control-test result",
      "compliance sign-off"
    ],
    "closure_status": "draft"
  },
  "rule_version": "part-c-esg-v1.0",
  "human_review_status": "required"
}
```

## 12. Presentation Demo Script / Presentation 演示脚本

### Screen 1: Gap Summary / 缺口总览

Show:

```text
EBA ESG Requirement: Directly applicable
Affected portfolio: EUR 2.3bn SME working-capital lending
Exposure: High (72/100)
Confidence: Medium (64/100)
```

Say:

> The regulation is relevant, but the agent does not simply call Northstar non-compliant. It checks which required capabilities have evidence.

> 该法规与 Northstar 直接相关，但 agent 不会直接判断银行不合规；它会检查每一项 required capability 是否有 evidence。

### Screen 2: Explain The Data Gap / 展示数据缺口

Select `PORT-SME-008`.

```text
Exposure: EUR 110m
NACE: missing
ESG data: missing
Result: Partial assessment capability, high data debt
```

Say:

> Missing NACE does not prove the borrower is high ESG risk. It proves Northstar cannot evidence that its ESG assessment is complete.

> 缺失 NACE 不代表 borrower 一定是高 ESG risk；它代表 Northstar 无法证明自己的 ESG assessment 是完整的。

### Screen 3: Action And Verification / 行动与验证

Show:

```text
P1: ESG Data Remediation
Owner: Head of Credit Risk
Delivery: Data/IT + SME Lending
Dependencies: none
Status: Draft

Verification threshold:
95% valid NACE coverage by SME exposure
100% high-materiality exposure classified
90% complete ESG assessment coverage
```

Say:

> The action cannot be closed by uploading a policy document. It becomes verified only after coverage thresholds, control testing, and compliance sign-off are all present.

> Action 不能因为上传一个 policy document 就关闭；只有达到数据覆盖 threshold、通过 control test 并获得 compliance sign-off 后，才可以变为 Verified。

## 13. Test Cases / 测试案例

| Test ID | Input condition | Expected result |
| --- | --- | --- |
| `TC-C-001` | Direct applicability; NACE/ESG data incomplete; no methodology/policy/control | P1 data remediation; gaps are Partial/Missing; not Verified |
| `TC-C-002` | Valid NACE >=95%, high-materiality borrowers all classified, but no control test | Evidence submitted or Control tested; not Verified |
| `TC-C-003` | All coverage thresholds met, methodology and policy approved, control test passes, compliance sign-off exists | Capability = Evidenced; action = Verified |
| `TC-C-004` | Applicability = Limited | Monitor only; no ESG remediation action created |
| `TC-C-005` | Required controls file is absent | Insufficient evidence; raise targeted request, do not assume Missing or Evidenced |

## 14. Design Handoff Checklist / 交付给技术同学的清单

The Part C design owner should deliver:

```text
[ ] capability catalogue
[ ] requirement-to-capability mapping
[ ] status decision table
[ ] priority formula and configuration values
[ ] action catalogue and dependency rules
[ ] state transition table
[ ] closure conditions by action
[ ] output JSON schema
[ ] five test cases with expected outputs
[ ] rule version and human reviewer name
```

## 15. Related References / 相关参考

- [EBA Guidelines on the management of ESG risks](https://eba.europa.eu/publications-and-media/press-releases/eba-publishes-its-final-guidelines-management-esg-risks)
- [Part C overview in ESG Deterministic Logic Design Pack](ESG_Deterministic_Logic_Design_Pack.md)
- [Northstar bank context](Bank_Context_Fictional_Digital_Bank.md)
- [Northstar SME lending and ESG data](generated_business_customer_exposure/README.md)
