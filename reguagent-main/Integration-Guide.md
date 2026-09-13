# 监管变更响应系统 —— 前后端整合开发文档（合并版）

**这份文档取代之前分散在 `A-_logic.md`、`PartB-Final-Spec-v4.md`、`Part_C.md` 三份文档里的判断逻辑——那三份文档里"为什么这么设计"的论证过程不再重复，只把真正要写进代码的规则、公式、查找表搬过来。想看设计动机和实测过程，回头翻那三份原始文档；想直接写代码，看这一份就够。**

**前端已经用静态模拟数据完整跑通**（见 `frontend_app/`）。后端要做的事，是把前端 `data.js` 里的 `STATE` 对象，换成由四个真实 Agent 驱动的产出，前端的数据结构不用改。

---

## 一、系统架构总览

```
外部监测工具（独立进程，只产出候选检测结果，不触碰下面的流水线）
        │  人工确认"开始分析"
        ▼
Agent A（适用性判断）──不确定──→ 人工待办队列
        │ 确定
        ▼
Agent B（exposure/confidence计算）──不确定──→ 人工待办队列
        │ 确定
        ▼
Agent C（能力缺口 + 候选行动查表）──不确定──→ 人工待办队列
        │ 确定
        ▼
Agent D（产能/成本核实 + 打包成可执行方案）──不可行──→ 人工待办队列（资源仲裁）
        │ 可行
        ▼
人工响应（采纳/修改/不采纳）→ 执行 → 证据 → 复盘评估 → 判例库
```

**贯穿四个 Agent 的唯一规则：** 每个 Agent 只做"能不能确定"和"确定了怎么办"两件事。能确定就用代码算出结果、写日志、交给下一个 Agent；不能确定就生成一条待办、写日志说明原因和交给谁，暂停等答案。任何 Agent 都不允许在不确定的情况下自己编答案往下走。

---

## 二、数据模型——前端已经在用的形状，字段名不能改

### 2.1 监管事件（`STATE.events`）

```json
{
  "id": "EBA-ESG-001", "title": "...", "portfolio": "...", "status": "...",
  "updated": "2026-09-08 09:04", "stageIndex": 4,
  "summary": { "citation": "...", "published": "...", "effective": "...", "body": "...", "sourceUrl": "..." },
  "stages": [
    { "name": "适用性", "state": "done", "summary": "...", "detail": "...",
      "evidence": ["文件:字段", "..."],
      "human": { "question": "...", "submittedBy": "...", "submittedAt": "...", "answer": "..." } }
  ]
}
```

`stages` 固定5个：适用性(A) / 暴露度(B) / 能力缺口(C) / 建议行动(C→D交接) / 响应结果(D)。`state` 取值 `done`/`active`/`pending`。没走到的阶段留空，不编内容。

### 2.2 待办队列（`STATE.queue`）

```json
{ "section": "weight", "id": "q-weight-1", "stage": "Part B", "who": "Head of Credit Risk", "text": "...", "payload": {} }
```

| section | 触发场景 | payload 形状 |
|---|---|---|
| `detection` | 外部监测发现候选变更 | `{ source, detectedAt, rawTitle, rawSnippet, sourceUrl }` |
| `weight` | 两两比较表未确认 | `{ matrixTitle, pairs: [{a, b, ratio, reason}] }` |
| `fact` | 缺失字段，问具体问题 | `{ question, placeholder }` |
| `evidence` | 证据闭环签字 | `{ items: [清单文字] }` |
| `priority` | 产能冲突仲裁 | `{ options: [互相冲突的行动描述] }` |
| `response` | 行动方案等表态 | `{ actions: [{id, title, steps, owner, dept, ddl, acceptance, estimated_cost_eur}] }` |
| `closure` | 等提交完成证据 | `{ actionTitle }` |
| `earlyexit` | 可提前结束，等签字 | `{ reasonText, regulationTitle }` |

### 2.3 审计日志（`STATE.logs`）

```json
{ "t": "...", "eventId": "...|null", "stage": "Part A", "actorType": "agent|human",
  "actor": "Agent A|具体角色名", "data": "依据的文件", "proceed": "是|否", "reason": "操作依据的完整文字" }
```

### 2.4 通知 / 判例（`STATE.notifications` / `STATE.precedents`）

```json
{ "id": "n1", "strong": true, "text": "...", "link": { "view": "queue-item", "itemId": "..." } }
{ "id": "P-2026-100", "date": "...", "rating": "准确|部分准确|不准确", "note": "...", "context": "..." }
```

---

## 三、REST API 清单

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/events` / `/api/events/:id` | 结果总览列表 / 详情 |
| GET | `/api/queue` | 待办队列全量 |
| POST | `/api/queue/:id/resolve` | 提交待办处理结果，body 按 section 分支（见2.2） |
| GET | `/api/logs` / `/api/notifications` | 日志 / 通知 |
| POST | `/api/precedents` | 提交复盘评估 |
| POST | `/internal/detections` | 外部监测工具专用，不对前端暴露 |

`resolve` 收到请求后固定顺序：①服务端重新校验（第十二节）②执行状态变更 ③删除待办 ④写日志（human）⑤触发对应 Agent 重新运行 ⑥Agent 写日志（agent）⑦确定则推进事件阶段/触发下一个Agent，不确定则生成新待办。

---

## 四、Agent A —— 适用性判断

**五种结论：** 直接适用 / 间接适用 / 有限适用 / 不适用 / **待人工确认**。核心原则：只有资料完整且证据明确时才能给出"不适用"，资料缺失或冲突时不允许猜，必须给"待人工确认"。

### 4.1 判断流程（七道关卡，任何一关卡住就停）

```
① 监管要求资料完整吗（是否已人工审核、有无机构类型/地区/业务活动/生效日期）？
   否 → 待人工确认："监管要求资料不完整或尚未审核"
② 银行与产品资料完整、不冲突吗？
   缺失或冲突 → 待人工确认（冲突举例：银行说不在EEA经营，但产品说在EEA销售）
③ 监管要求当前有效吗？
   已失效 → 不适用 ｜ 未生效 → 间接适用（标记"即将生效"）
④ Northstar 是受监管机构类型吗？
   否 → 不适用："机构类型不匹配" ｜ 类型无法映射 → 待人工确认
⑤ 产品实际经营地区在覆盖范围内吗（用产品自己的地区，不只看总部）？
   不在 → 不适用："地区不匹配" ｜ 地区未知且银行多地经营 → 待人工确认
⑥ 产品是相关业务活动吗？
   不是但与银行整体要求有关 → 有限适用 ｜ 缺失/冲突 → 待人工确认
⑦ 全部通过 → 按标准产品分类查表（见4.2）
```

### 4.2 产品分类查表（Rule 7，纯查表，不需要LLM）

| 标准产品分类 | 结论 |
|---|---|
| `sme_credit` / `corporate_credit` | 直接适用 |
| `residential_mortgage` / `unsecured_consumer_lending` | 间接适用 |
| `liquidity_treasury` | 有限适用（仅监控，不建整改任务） |
| `other` / 未分类 | 待人工确认 |

**已知的字段对齐问题**：这张表用的分类值（`sme_credit`等）跟 `02_business/products.json` 实际的 `product_type` 字段值（`sme_term_loan`等）不一致，需要一张映射表，不能指望名字自动对上。

### 4.3 抽取分类值——这一步用LLM，读非结构化/半结构化输入

判断前先要拿到 `entity_type`、`operating_region`、`is_lending_activity`、`product_classification` 等具体取值，Prompt 见第七节 Prompt 1。抽取完全部交给上面的确定性代码判断，LLM 不参与④-⑦步骤本身。

### 4.4 人工覆盖规则

人工可以修改系统结论，但不能删除原始结论，每次覆盖必须记录：系统原结论、修改后结论、修改原因、支持证据、审核人、审核日期、审批状态（`已人工覆盖`）。

### 4.5 输出

```json
{ "requirement_id": "...", "applicability": "direct|indirect|limited|not_applicable|needs_human_review",
  "in_scope_products": ["PRD-..."], "out_of_scope_products": [...],
  "rationale": "...", "evidence_record_ids": [...] }
```

---

## 五、Agent B —— Exposure 与 Confidence 计算

**核心原则不重复论证（AHP为什么、为什么不用固定权重，见 `PartB-Final-Spec-v4.md` 第一节），这里只给已经验证过的权重和公式。核心计算全程不调用LLM。**

### 5.1 已验证权重（一致性检验通过，CR远低于0.10阈值）

```json
{
  "exposure": {"materiality": 0.40, "transition_risk": 0.25, "physical_risk": 0.15,
               "sector_concentration": 0.13, "review_urgency": 0.07},
  "confidence": {"sector_classification": 0.35, "esg_data_availability": 0.35,
                 "geography_coverage": 0.15, "assessment_freshness": 0.15}
}
```

**权重不是硬编码的常数，是"AI起草两两比较表→人工签字→AHP算法转换"这套流程（对应待办`section: weight`）跑出来的结果**——每接一条新监管，如果关心的维度不一样，要重新走一遍这个流程，不是复用同一组数字。流程细节和 Prompt 见第七节 Prompt 2。

### 5.2 五个 Exposure 维度打分（纯代码，if-else分档）

```python
def score_materiality(balance, book_total):
    share = balance / book_total
    if share >= 0.15: return 100
    if share >= 0.10: return 75
    if share >= 0.05: return 50
    return 25
    # 不用十分位法——记录数<20时十分位法会失效，已实测验证

RISK_BAND_SCORE = {"high": 100, "medium": 60, "low": 20}
def score_risk_band(band):
    return RISK_BAND_SCORE.get(band)  # None时不给分，进入5.4的补全流程

def score_sector_concentration(sector_share):
    if sector_share >= 0.20: return 100
    if sector_share >= 0.15: return 75
    if sector_share >= 0.10: return 50
    return 25
    # 不用原始20%阈值——实测最高占比19.57%，一分不到永远碰不到，权重会失效

def score_review_urgency(days_past_due, remaining_maturity_years):
    if days_past_due > 0: return 100
    if remaining_maturity_years <= 1.0: return 75
    if remaining_maturity_years <= 2.0: return 50
    return 25
```

### 5.3 四个 Confidence 维度打分

```python
NACE_SCORE = {"validated_nace": 100, "broad_nace": 60, "missing_nace": 0}
ESG_COVERAGE_SCORE = {"full": 100, "partial": 70, "limited": 40, "missing": 0}
def score_geography(country): return 100 if country else 0
def score_freshness(assessment_date, as_of):
    if not assessment_date: return 0
    age_days = (as_of - date.fromisoformat(assessment_date)).days
    return 100 if age_days <= 365 else 50
```

### 5.4 缺失维度：AI先推断，推断不了就生成具体问题（不能给假分数）

```python
def compute_exposure_with_gaps(known_dims, unresolved_dims, weights):
    base = sum(known_dims[k] * weights[k] for k in known_dims)
    if not unresolved_dims:
        return {"exposure_score": round(base, 1), "indeterminate": False}
    lower = base + sum(20 * weights[d] for d in unresolved_dims)   # 最好情形
    upper = base + sum(100 * weights[d] for d in unresolved_dims)  # 最坏情形
    return {"exposure_score": None, "exposure_range": [round(lower,1), round(upper,1)],
            "indeterminate": True, "unresolved_dimensions": unresolved_dims}
```

维度确实缺失时：①AI先尝试从同一借款人的关联记录推断（Prompt见第七节）②推断不了，生成具体问题（对应`section: fact`）。**已知数据限制**：当前demo每个借款人只有一笔贷款，推断这条路径实测永远走不到，会直接落到生成问题这条路。

### 5.5 Data Debt

```python
def score_data_debt(balance, book_total, confidence_score, urgency_score):
    exposure_weight = min(balance / book_total / 0.15, 1.0)
    missing_severity = (100 - confidence_score) / 100
    urgency = urgency_score / 100
    product = exposure_weight * missing_severity * urgency
    return round((product ** (1/3)) * 100, 1) if product > 0 else 0.0
    # 用几何平均，不用纯乘积——纯乘积会把分数压到0-33区间，分档失效
```

### 5.6 输出

```json
{ "record_id": "...", "exposure_score": 85.5, "exposure_range": [85.5,85.5],
  "exposure_indeterminate": false, "confidence_score": 89.5, "data_debt_score": 2.6,
  "gap_resolution_log": [], "human_review_status": "not_reviewed" }
```

---

## 六、Agent C —— 能力缺口与候选行动

### 6.1 输入数据契约

| 输入 | 最小字段 | 来源 |
|---|---|---|
| 适用性结果 | `requirement_id`, `applicability`, `in_scope_products` | Agent A |
| 暴露结果 | `exposure_score`, `confidence_score`, `data_debt_score` | Agent B |
| 现有能力证据 | `capability_id`, `status`, `evidence_ids`, `last_review_date` | `04_governance/controls.json`, `policies.json`, `procedures.json` |
| 归属 | `owner_id`, role, cost centre | `06_organisation/roles.json`, `raci.csv`（**只用来填owner，不用来算产能**——产能计算是Agent D的事，见第七节） |
| 行动目录 | 见第十七节新增数据文件 | `08_evidence/action_catalogue.json` |

**如果某项输入记录不存在，必须返回 `insufficient_evidence`，不能假设能力已经具备。**

### 6.2 六项能力目录

`CAP-ESG-SECTOR-DATA` / `CAP-ESG-RISK-DATA` / `CAP-ESG-METHODOLOGY` / `CAP-ESG-MONITORING` / `CAP-ESG-POLICY` / `CAP-ESG-GOVERNANCE`

### 6.3 状态判断规则（四选一，LLM抽取+人工兜底，Prompt见第七节）

| 状态 | 规则 |
|---|---|
| `evidenced` | 证据存在、当前有效、覆盖要求、控制测试通过 |
| `partial` | 有部分证据，但覆盖范围/质量/频率不足 |
| `missing` | 确认查过、确实不存在相关证据 |
| `insufficient_evidence` | 无法确定"真的不存在"还是"没搜到"——**不允许因为大概率是missing就直接判missing** |

### 6.4 优先级公式（当前是Part_C.md给定的常数，不是AHP推导出来的）

```
优先级分数 = 35%×截止日期紧迫度 + 30%×exposure材料性 + 20%×缺口严重度 + 15%×依赖影响
```

| 因子 | 条件 | 分数 |
|---|---|---|
| 截止日期紧迫度 | 已逾期或90天内到期 / 91-180天 / 181-365天 / 超过365天 | 100/70/40/20 |
| exposure材料性 | High/Material/Potential/Monitor | 100/70/40/10 |
| 缺口严重度 | Missing/Partial/insufficient_evidence/Evidenced | 100/60/70/0 |
| 依赖影响 | 阻塞3+能力/阻塞1-2个/独立 | 100/60/20 |

分档：81-100=P1（立即启动+升级汇报） / 61-80=P2（当前变更周期） / 41-60=P3（纳入计划） / 0-40=P4（仅监控）

**注意 `insufficient_evidence`（70分）比`Partial`（60分）还高**——这是有意设计：信息缺失本身要优先去查清楚，不是"缺信息=风险低"。

### 6.5 行动目录查表（纯查表，见第十七节完整数据文件）

Agent C 判断出`gap_id`后，直接去`action_catalogue.json`按`gap_id`查出对应的候选行动，不现场生成。**必须把目录那一行的全部字段都带出来**（包括`delivery_owners`、`estimated_effort_days`），不能只抄`accountable_owner`——Agent D 算产能要用到这些字段。

### 6.6 证据闭环状态机（规则由Agent C定义，运行时由Agent D驱动状态转移）

```
Draft → Assigned → In progress → Evidence submitted → Control tested → Compliance approved → Verified
```

| From | To | 必要条件 |
|---|---|---|
| Draft | Assigned | 责任人和截止日期存在 |
| Assigned | In progress | 交付方接受任务 |
| In progress | Evidence submitted | 必需的证据材料已附上 |
| Evidence submitted | Control tested | 控制责任人完成测试 |
| Control tested | Compliance approved | 测试通过且合规审核人批准 |

### 6.7 输出（比 Part_C.md 原文档示例多带 `delivery_owners`）

```json
{
  "requirement_id": "REQ-ESG-001",
  "capability_assessments": [{"capability_id": "CAP-ESG-SECTOR-DATA", "status": "partial", "gap_id": "GAP-ESG-DATA-001"}],
  "recommended_action": {
    "action_id": "ACT-ESG-DATA-REMEDIATION", "priority": "P1", "priority_score": 91,
    "accountable_owner": "ROLE-HEAD-CREDIT-RISK", "delivery_owners": ["ROLE-CIO"],
    "estimated_effort_days": {"ROLE-HEAD-CREDIT-RISK": 5, "ROLE-CIO": 3},
    "required_evidence": ["NACE remediation log", "data-quality report", "control-test result", "compliance sign-off"],
    "closure_status": "draft"
  },
  "human_review_status": "required"
}
```

Agent C 到这里结束——**它不知道这个人现在忙不忙、这事要花多少钱，这些不是它该管的。**

---

## 七、Agent D —— 产能核实与方案打包

这是新写的部分，之前的三份文档都没覆盖，逻辑基于本次讨论确定。

### 7.1 输入

Agent C 的输出（6.7节）+ 三张真实数据文件（字段已核对，不是猜的）：

| 文件 | 关键字段 |
|---|---|
| `06_organisation/roles.json` | `role_id`, `cost_centre_id`（连接下面两张表的桥梁） |
| `07_economics/change_capacity.csv` | `role_id`, `period`, `remaining_days` |
| `07_economics/operational_costs.csv` | `cost_centre_id`, `cost_type`（取`internal_day`那一行）, `unit_cost_eur` |

### 7.2 算法

```python
def check_feasibility_and_cost(recommended_action):
    owners = [recommended_action["accountable_owner"]] + recommended_action["delivery_owners"]
    results = {}
    all_feasible = True

    for role_id in owners:
        remaining = change_capacity_repo.get(role_id).remaining_days
        cost_centre_id = roles_repo.get(role_id).cost_centre_id
        day_rate = operational_costs_repo.get(cost_centre_id, cost_type="internal_day").unit_cost_eur
        needed_days = recommended_action["estimated_effort_days"][role_id]

        feasible = remaining >= needed_days
        all_feasible = all_feasible and feasible
        results[role_id] = {
            "needed_days": needed_days, "remaining_days": remaining,
            "feasible": feasible, "cost_eur": needed_days * day_rate,
        }

    return {"all_feasible": all_feasible, "by_owner": results,
            "total_cost_eur": sum(r["cost_eur"] for r in results.values())}
```

**`estimated_effort_days` 从哪来**：默认应该已经写在 `action_catalogue.json` 里（人工提前定好，见第十七节），不是Agent D现场猜的。如果目录里这个行动缺这个字段，走`section: fact`问一次，问完建议把答案写回目录，下次同一行动不用再问。

**多个待处理行动同时抢同一个 `role_id` 的产能**（比如这次和另一条监管触发的行动用了同一个人），需要在内存/数据库里维护一个"本轮已经临时预占了多少天"的计数，不能只查 `change_capacity.csv` 的静态值——那张表不会实时反映"系统刚刚生成的、还没人确认的候选行动"。

### 7.3 决策分支

```
all_feasible = true
  → 打包成 section: "response" 待办，见7.4
all_feasible = false
  → 生成 section: "priority" 待办，列出互相冲突的行动，交给人排序
  → 不生成 response 待办（方案还不确定，不该先让人表态采不采纳）
```

### 7.4 打包成响应方案（对应前端 `response` payload）

```json
{
  "id": "ACT-ESG-DATA-REMEDIATION", "title": "ESG数据整改",
  "steps": "补齐SME组合中NACE行业码缺失或过宽的贷款记录，使有效NACE覆盖率达到95%以上",
  "owner": "Head of Credit Risk", "dept": "CIO / 技术团队",
  "ddl": "2026-12-15", "acceptance": "有效NACE覆盖率≥95%，控制测试通过，合规签字",
  "estimated_cost_eur": 5590
}
```

`steps`/`acceptance` 的文字来自 `action_catalogue.json` 里的静态描述（人工写好，不需要LLM现场编）；`owner`/`dept` 把 role_id 转成人类可读的角色名（查`roles.json`的`title`字段）；`estimated_cost_eur`是7.2算出来的`total_cost_eur`。

---

## 八、每个 Agent 具体读哪些数据文件——总表

| Agent | 文件 |
|---|---|
| **A** | `regulatory_sources/requirements.json`、`01_entity/bank_profile.json`、`02_business/business_lines.json`、`02_business/products.json` |
| **B** | Agent A 的 `in_scope_products`、`03_exposure/lending_portfolio.csv`、`03_exposure/esg_assessment_snapshot.csv`、`model_config/pairwise_matrix_registry.json`（需新建） |
| **C** | Agent B 的输出、`04_governance/controls.json`、`policies.json`、`procedures.json`、`06_organisation/roles.json`（只取owner）、`08_evidence/action_catalogue.json`（需新建，见十七） |
| **D** | Agent C 的输出、`06_organisation/roles.json`（取cost_centre_id）、`07_economics/change_capacity.csv`、`07_economics/operational_costs.csv` |
| **判例库（跨Agent）** | `evaluation_ground_truth/precedent_log.json`（需新建） |

---

## 九、LLM Prompt 清单

**总原则：LLM只做①把非结构化文本抽取成结构化字段 ②把已经算好的结果讲成一句人话，永远不直接产出最终分数/优先级/缺口状态。**

### Prompt 1 —— Agent A 抽取分类值

```
你的任务是从下面的法规适用条件和银行数据中，抽取出用于查表判断的分类值。
你不能自己判断"适用不适用"，只能填写字段取值，取值必须能在提供的数据中找到依据。

需要填写：entity_type / operating_region / legal_entity / product_region /
is_lending_activity / product_classification

规则：
1. 每个字段标注数据来源（文件名+字段名）。
2. 找不到依据就填 null，列入 missing_fields，不能编造。
3. 数据互相矛盾时列入 conflicts，不要自己选一个。

法规适用条件：{applicability_conditions_json}
银行数据节选：{bank_data_json}

输出JSON：{ "entity_type": {"value":..., "source":...}, ..., "missing_fields": [...], "conflicts": [...] }
```

### Prompt 2 —— 共享"决策叙事"生成器（四个 Agent 共用，写日志`reason`和事件`detail`）

```
把一个已经做出的确定性判断，转写成一到两句中文说明文字。
规则：
1. 不能修改或重新评估判断本身，只能忠实转写。
2. 必须点出依据了哪个文件的哪个字段，不能写"根据相关数据"这种空话。
3. 必须说明结论是什么、因此继续处理交给谁，或暂停交给谁。
4. 80字以内，客观专业，不用比喻。

输入：{ "agent": "...", "data_sources": [...], "decision": "...", "proceed": true/false,
        "handoff_to": "...", "handoff_reason_code": "..." }

只输出这一到两句话。
```

生成的文字**只用于展示，不是判断依据本身**——真正决定continue/pause的是输入里的`decision`/`proceed`字段，这些是确定性代码算出来的。

### Prompt 3 —— Agent B 两两比较表起草（每接一条新维度不同的监管都要走一次）

```
你要为监管要求"{requirement_id}"起草一份两两比较表草稿，用于计算"{dimension_set}"。
需要比较的维度：{dimension_list}
对每一对维度给出1-9的重要性倍数（Saaty标度）并写清楚理由，理由要结合这条监管具体关心什么。
只输出比较结果和理由，不要输出最终权重百分比。
严格JSON数组格式：[{dimension_a, dimension_b, ratio, reasoning}, ...]
```

草稿生成后必须走人工签字（对应`section: weight`），签字后才能用AHP算法转换成权重，一致性检验（CR<0.10）不通过要退回重新起草。

### Prompt 4 —— Agent B 缺失维度推断 + 生成具体问题

```
【推断】下面这条记录缺少"{missing_dimension}"字段。同一借款人的其他记录：{related_records_json}。
只有明确、直接相关的信息才给出推断值，模糊线索不算；无法推断就返回 cannot_infer，不要编造。
推断结果仅为建议，不直接采用，需转交人工确认。

【生成问题】推断失败后，为负责这个客户的经理生成一个具体、可直接回答的问题，
不要写"请补充数据"这种空泛的话，要具体到这条记录本身。
```

### Prompt 5 —— Agent C 判断能力证据状态

```
判断某项能力要求在提供的治理文档里处于哪种状态：Missing/Partial/Evidenced/insufficient_evidence。
规则：
- 确认文档范围内根本不存在相关记录 → Missing
- 存在记录但覆盖/频率/审批不足 → Partial
- 存在记录且完全满足 → Evidenced
- 无法确定"真的不存在"还是"没搜到" → insufficient_evidence，
  绝不允许因为"大概率是Missing"就直接判Missing

能力要求：{capability_requirement}
治理文档节选：{governance_docs_excerpt}
检索范围说明：{search_scope_description}

输出：{ "status": "...", "evidence_found": [...], "reasoning": "...",
        "search_completeness": "complete | uncertain" }
```

`search_completeness: uncertain` 时，即便`status`判Missing，也要在下游转成`insufficient_evidence`交人复核。

### Agent D 不需要新的判断类Prompt

产能/成本是纯计算（第七节），候选行动来自Agent C的查表结果，Agent D只用Prompt 2写日志文字。

---

## 十、Agent 的"恢复运行"怎么实现

```python
def resolve_queue_item(item_id, body):
    item = queue_repo.get(item_id)
    validate(item.section, body)          # 第十二节的规则，服务端必须再做一遍
    apply_resolution(item, body)
    queue_repo.delete(item_id)
    log_repo.append(actor_type="human")   # 其余字段（event_id/stage/actor/data/proceed/reason）省略

    result = {"Part A": agent_a, "Part B": agent_b,
              "Part C": agent_c, "Part D": agent_d}[item.stage].run(item.event_id)
    log_repo.append(actor_type="agent")   # 其余字段省略

    if result.needs_human:
        queue_repo.create(result.new_queue_item)
        notification_repo.create(strong=True)   # 其余字段省略
    else:
        event_repo.update_stage(item.event_id, done=True)
        # 有下一个Agent就继续调用，同样遵循"确定则走、不确定则停"
```

**返回值必须明确区分"确定往下走"和"不确定生成待办"，不要用抛异常表示"不确定"——不确定是正常业务状态，不是错误。**

---

## 十一、判例库

复盘评估（`POST /api/precedents`）存下来的东西不是只存档——Agent 做判断前（尤其Agent A的分类判断、Agent C的证据缺失判断），先查有没有"高度相似"的历史判例，有就在`evidence`/`reason`里带上判例编号和日期。**相似度怎么判断还没定**，需要专门讨论，不要为了赶进度跳过。

---

## 十二、后端必须重复的前端校验规则

| section | 规则 |
|---|---|
| `weight` | 倍数被改动，`adjustment_reason`必须非空 |
| `fact` | `answer`不能为空 |
| `evidence` | 所有清单项都要为true |
| `priority` | `chosen_index`必须是合法索引 |
| `response` | 每个action都要有decision；decision=reject时reject_reason必填 |
| `closure` | `evidence_files`不能是空数组 |
| `earlyexit` | decision合法；decision=agree时signer_role必填 |
| `detection` | action合法；action=dismiss时reason必填 |
| 判例评估 | rating必选；rating≠"准确"时note必填 |

---

## 十三、外部监测工具接入

独立进程，跑完一轮调用内部接口：

```
POST /internal/detections
{ "source": "regwatch-eu", "detectedAt": "...", "rawTitle": "...", "rawSnippet": "...", "sourceUrl": "..." }
```

后端生成`section: detection`待办 + 知会通知（`strong: false`）。**外部工具不允许自己判断"这条重不重要"，重要性判断留给人在待办队列里做。**

---

## 十四、端到端例子

```
1. 外部工具检测 → POST /internal/detections → 生成detection待办
2. 人点"开始分析" → 创建event，触发 Agent A

3. Agent A：读requirements.json+bank_profile.json+business_lines.json
   → 判定direct，确定 → 日志(agent,是) → 触发 Agent B

4. Agent B：发现没有已确认两两比较表
   → 生成weight待办 → 日志(agent,否，交给Head of Credit Risk) → 暂停

5. 人签字确认矩阵 → 日志(human,是) → 重新触发 Agent B

6. Agent B：AHP计算通过，逐条打分完成，确定 → 日志(agent,是) → 触发 Agent C

7. Agent C：查controls.json，判CAP-ESG-METHODOLOGY为missing
   → 查action_catalogue.json，gap_id=GAP-ESG-DATA-001 → 命中 ACT-ESG-DATA-REMEDIATION
   → 输出（含delivery_owners=[ROLE-CIO]，estimated_effort_days）→ 触发 Agent D

8. Agent D：
   - ROLE-HEAD-CREDIT-RISK：remaining_days=8，需要5天，cost_centre=CC-210，650欧元/天 → 可行，成本3250
   - ROLE-CIO：remaining_days=8，需要3天，cost_centre=CC-500，780欧元/天 → 可行，成本2340
   - all_feasible=true → 打包成response待办，总成本5590欧元

9. 人打开待办，看到完整方案：做什么/负责人/部门/截止日期/验收标准/预估成本
   选择"采纳" → 日志(human,是) → 事件"响应结果"阶段更新为active

10. 行动执行完毕，人从待办队列主动找到closure条目，上传证据 → 触发复盘评估

11. 评估"准确" → POST /api/precedents → 存入判例库
```

---

## 十五、建议的后端目录结构

```
backend/
  agents/
    agent_a_applicability.py
    agent_b_exposure.py
    agent_c_gaps.py
    agent_d_feasibility.py        # 第七节，读capacity/cost两张表
  orchestrator.py                  # 第十节
  validators.py                    # 第十二节
  precedent_matcher.py              # 第十一节，相似度规则待设计
  api/
    events.py / queue.py / logs.py / notifications.py / precedents.py
    internal_detections.py
  models/                          # 第二节的数据结构
```

---

## 十六、给写代码同学的几句话

- 不要让LLM直接给出`exposure_score`/`priority_score`/`estimated_effort_days`这类最终数字，这些要么是确定性代码算的，要么是人提前定好写进配置/目录文件的
- 遇到不确定，先看能不能生成一个具体问题问人，不要抛错误或卡死
- 前端已经跑通并测试过，接口对不上先改后端，除非四个人一起决定改前端交互

---

## 十七、需要新建的数据文件——行动目录

**这是目前唯一缺失、必须有人补上才能让 Agent C→D 这段链路真正跑起来的文件。** 内容取自 `Part_C.md` 第9节的表格，补充了 `delivery_owners`（原文档有但输出JSON漏掉的字段）和 `estimated_effort_days`（原文档完全没有、这次讨论新增的字段）。**天数是占位示例，需要熟悉这几项工作的人核实调整，不是最终数字。**

```json
{
  "_meta": {
    "file": "08_evidence/action_catalogue.json",
    "purpose": "缺口类型到候选行动的确定性查找表。Agent C 只查表，不现场生成内容。estimated_effort_days 由人工提前估算，Agent D 用它去核对 change_capacity.csv 里的剩余产能，不由AI临时猜测。",
    "note": "天数为占位示例，正式使用前需要熟悉具体工作量的人核实。"
  },
  "actions": [
    {
      "action_id": "ACT-ESG-DATA-REMEDIATION",
      "addresses_gap_ids": ["GAP-ESG-DATA-001"],
      "title": "ESG数据整改",
      "steps": "补齐SME组合中NACE行业码缺失或过宽的贷款记录，并补齐对应ESG评估数据，使有效NACE覆盖率达到95%以上",
      "accountable_owner": "ROLE-HEAD-CREDIT-RISK",
      "delivery_owners": ["ROLE-CIO"],
      "dependency": "none",
      "initial_priority": "P1",
      "estimated_effort_days": { "ROLE-HEAD-CREDIT-RISK": 5, "ROLE-CIO": 3 },
      "required_evidence": ["NACE remediation log", "data-quality report", "control-test result", "compliance sign-off"]
    },
    {
      "action_id": "ACT-ESG-METHODOLOGY",
      "addresses_gap_ids": ["GAP-ESG-METHOD-001"],
      "title": "ESG评估方法论",
      "steps": "制定并批准一套可复算的ESG组合风险评分方法，明确权重来源与阈值",
      "accountable_owner": "ROLE-CHIEF-RISK",
      "delivery_owners": ["ROLE-HEAD-CREDIT-RISK"],
      "dependency": "依赖数据整改的输出",
      "initial_priority": "P1",
      "estimated_effort_days": { "ROLE-CHIEF-RISK": 4, "ROLE-HEAD-CREDIT-RISK": 2 },
      "required_evidence": ["方法论文件", "模型风险委员会审批记录"]
    },
    {
      "action_id": "ACT-ESG-POLICY-CONTROL",
      "addresses_gap_ids": ["GAP-ESG-POLICY-001", "GAP-ESG-MONITOR-001"],
      "title": "ESG政策与控制建设",
      "steps": "制定组合层面的ESG风险政策，设计对应的监控控制并完成首次测试",
      "accountable_owner": "ROLE-HEAD-COMPLIANCE",
      "delivery_owners": ["ROLE-CHIEF-RISK"],
      "dependency": "依赖方法论设计",
      "initial_priority": "P1",
      "estimated_effort_days": { "ROLE-HEAD-COMPLIANCE": 6, "ROLE-CHIEF-RISK": 2 },
      "required_evidence": ["经批准的ESG政策", "监控控制设计文档", "控制测试结果"]
    },
    {
      "action_id": "ACT-ESG-MONITORING-CONTROL",
      "addresses_gap_ids": ["GAP-ESG-MONITOR-001"],
      "title": "ESG组合持续监控",
      "steps": "建立ESG组合的定期监控报告和阈值预警机制",
      "accountable_owner": "ROLE-HEAD-CREDIT-RISK",
      "delivery_owners": ["ROLE-CIO"],
      "dependency": "依赖数据+方法论+政策全部完成",
      "initial_priority": "P2",
      "estimated_effort_days": { "ROLE-HEAD-CREDIT-RISK": 3, "ROLE-CIO": 4 },
      "required_evidence": ["监控报告模板", "阈值预警配置记录"]
    }
  ]
}
```

**用到的 `role_id` 请对照 `06_organisation/roles.json` 实际存在的角色核实**（本文档第七节已核实过 `ROLE-HEAD-CREDIT-RISK`→`CC-210`、`ROLE-CIO`→`CC-500` 这两组映射是真实存在的；`ROLE-CHIEF-RISK`→`CC-100`、`ROLE-HEAD-COMPLIANCE`→`CC-120` 同样已在 `roles.json` 里核实存在）。
