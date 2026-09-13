# Part B — Exposure & Confidence Intelligence
## 最终实现规格（可直接用于开发，已用真实数据验证跑通）

**Stage：** 2 — Exposure Intelligence
**回答的问题：** Should / where / how much should we care?
**产出：** Exposure map, confidence, missing facts

---

## 0. 这一部分做什么

**输入：** Part A 判定为适用的产品清单 + 该产品下每一笔贷款/组合的客观数据。
**输出：** 每一笔记录的 exposure 分数（影响多大）、confidence 分数（我们有多确定）、data debt 分数（数据缺口多急）、以及一份"缺什么数据"的清单。

**这一部分不做：** 不判断适用性（Part A 已做）、不判断缺口类型或生成整改行动（Part C 做）、不给出法律结论。

---

## 一、为什么不能用固定权重，必须用 AHP

### 1.1 固定权重的问题

给"材料性"、"转型风险"、"物理风险"这些维度直接定权重（比如"材料性占40%"），是一个业务判断，不是数学计算。如果这个判断是某个人拍脑袋写下来的，会有两个致命问题：

**第一，经不起追问。** 答辩或审计时如果被问"为什么材料性是40%不是35%"，唯一的回答只能是"我们觉得差不多"，这站不住脚。

**第二，不同人给出的权重会天差地别，而且没有办法判断谁对谁错。** 调研了业界真实做法后可以确认这不是猜测：连专业评级机构给同一类风险因素的权重都完全不统一——(<cite index="13-1">Moody's 给资金与流动性因素35%的权重，Fitch 只给10%，而 S&P 干脆不用一套固定的财务比率和权重，改用委员会讨论决定最终评级</cite>。学术研究也指出(<cite index="11-1">不同评级机构对同一家公司给出差异极大的分数，且评分标准本身随时间变化</cite>。

**结论：权重该是多少，本来就没有唯一正确答案。真正重要的不是数字本身，是这个数字从哪来、能不能被复核、能不能被重新推导。**

### 1.2 直接问"占几个百分点"，人很难给出可靠答案

如果直接问"材料性该占多少权重"，大部分人会卡住，因为这是一个抽象的绝对数值判断。但如果换成问"材料性和转型风险比，哪个更重要，重要几倍"，人反而容易给出有把握的答案——这是一个相对判断，而且有具体的参照物。

**AHP（Analytic Hierarchy Process，层次分析法）解决的正是这个问题。** (<cite index="21-1">由 Saaty 在1970年代提出，是一种把主观判断转化为可比较数值权重的结构化方法，特别适用于基于主观判断的复杂决策</cite>。它的做法是让评估者对同一层级的因素做两两比较，而不是直接给出百分比，(<cite index="20-1">同时还能量化判断的内部一致性</cite>——也就是能检测出"你的这些两两判断，逻辑上自相矛盾了吗"。

### 1.3 AHP 具体是什么，怎么运作

**输入：一张两两比较表。** 比如五个维度要两两比较，就有一张5×5的表，每一格填"这一行的因素，比这一列的因素重要几倍"（用1到9的Saaty标度）。

**运算：三步，从两两比较表推出最终权重。**
1. 把表格每一列加起来
2. 每个格子的数字，除以它所在那一列的总和（归一化）
3. 每一行取平均，得到这一行对应因素的权重

**检验：一致性比率（CR）。** 如果你的两两判断自相矛盾（比如"A比B重要，B比C重要，但C又比A重要"），AHP会算出一个偏高的CR值，提示这组判断不可信，必须重新填。CR低于0.10才算通过。

**这套方法的核心价值：权重不再是一个孤零零的数字，而是有一整套"如何得出"的过程附在后面，这个过程可以被质疑、被重新推导、被追溯。**

---

## 二、两两比较表从哪来——嵌入 Part A 交接节点的强制检查

### 2.1 核心设计：不是"先建好所有监管的对比表"，而是"用到哪个监管，才检查/生成哪张表"

每一类监管关心的维度不一样（ESG关心材料性和转型风险，VoP可能关心渠道覆盖率和交易量，DORA可能关心依赖层级），**不存在一张能通用所有监管的对比表**。因此正确的做法不是提前把所有可能用到的表都做好，而是：**Part B 每次启动时，先看这次要处理的监管，有没有现成的、已经人工确认过的对比表；没有，就先走一遍生成流程，通过审核之后才能往下算分。**

### 2.2 完整流程

```
Part A 输出:
  requirement_id = "REQ-ESG-001"
  in_scope_products = ["PRD-SME-WORKING-CAPITAL"]
        │
        ▼
【代码】查找：pairwise_matrix_registry 里，
        有没有 requirement_id 对应的、状态为 "confirmed" 的两两比较表？
        │
        ├── 有，且已确认 ──────────────────────┐
        │                                        │
        └── 没有，或状态还是 "draft" ──┐         │
                                          ▼         │
                            【AI】起草两两比较表草稿  │
                                          ▼         │
                            【人】审核、修改、签字确认 │
                                          ▼         │
                            存入 registry，标记为    │
                            "confirmed"             │
                                          │         │
                                          └────┬────┘
                                               ▼
                            【代码】AHP 算法，把已确认的表
                                    转换成具体权重数字
                                    + 一致性检验（不通过则退回上一步）
                                               │
                                               ▼
                            【代码】权重写入配置文件，
                                    本次 exposure/confidence 计算开始
```

### 2.3 代码：Part B 启动时的第一件事——一次性检查所有需要的表

```python
def ensure_confirmed_matrices(requirement_id: str, needed: list[tuple[str, list[str]]],
                                registry: dict) -> dict:
    """
    needed: [(dimension_set, dimension_names), ...]
            同一条 requirement 下，exposure 和 confidence 各自需要一张独立的两两比较表，
            这里一次性把两者都需要的表检查完，不要一张一张分开检查。

    【实测踩过的坑，已修正】最初版本写成"发现第一张表缺失就立刻中止"，
    这样跑一次只能补全一张表（比如exposure），confidence那张表根本没机会被生成，
    人工确认完exposure表、重新运行，又会在confidence这里再中止一次——
    实际跑起来变成"运行三次才能真正开始算分"，体验很差，也容易让人以为流程卡住了。
    修正后：一次性检查全部需要的表，缺哪张就把哪张的草稿都生成出来，
    一次性汇总告诉人"这几张表需要确认"，人一次性签完，第二次运行就能跑通。
    """
    pending = []
    result = {}
    for dimension_set, dimension_names in needed:
        key = f"{requirement_id}::{dimension_set}"
        existing = registry.get(key)
        if existing and existing["status"] == "confirmed":
            result[dimension_set] = existing
            continue
        if not existing:
            existing = draft_pairwise_matrix(requirement_id, dimension_set, dimension_names)
            registry[key] = existing
        pending.append(key)

    if pending:
        raise RuntimeError(
            f"以下两两比较表尚未经人工确认，流程中止：{pending}。"
            f"已为缺失项生成/保留草稿，调用 human_confirm_matrix 确认后重新运行。"
        )
    return result
```

**这里刻意设计成"抛异常中止"，不是"自动往下走"。** 原因：如果代码在没有人工确认的情况下，用AI生成的草稿直接去算权重，等于绕过了"人必须签字"这道关卡，跟第一节强调的"权重要经得起追问"这个原则直接冲突。

### 2.4 AI 起草两两比较表——具体 prompt

```python
DRAFT_MATRIX_PROMPT = """
你要为监管要求 "{requirement_id}" 涉及的 SME 信贷组合，起草一份两两比较表草稿，
用于计算 "{dimension_set}"（{dimension_set_meaning}）。

需要比较的维度：
{dimension_list}

任务：对每一对维度，给出一个 1-9 的重要性倍数（Saaty标度），并写清楚具体理由，
理由必须结合这条监管要求本身在关心什么，不能写空泛的话。

只输出比较结果和理由，不要输出最终权重百分比（权重由后续代码用AHP算法计算，不是你的任务）。

以严格 JSON 数组格式输出，每个元素包含：
dimension_a, dimension_b, ratio, reasoning
"""

def draft_pairwise_matrix(requirement_id: str, dimension_set: str,
                            dimension_names: list[str]) -> dict:
    meaning = "影响暴露程度" if dimension_set == "exposure" else "判断置信度"
    prompt = DRAFT_MATRIX_PROMPT.format(
        requirement_id=requirement_id,
        dimension_set=dimension_set,
        dimension_set_meaning=meaning,
        dimension_list="\n".join(f"- {d}" for d in dimension_names),
    )
    response = call_llm(prompt)   # 实际项目替换为真实模型调用
    pairs = json.loads(response)

    return {
        "requirement_id": requirement_id,
        "dimension_set": dimension_set,
        "dimension_names": dimension_names,
        "pairs": pairs,
        "status": "draft",
        "drafted_by": "llm",
        "drafted_at": date.today().isoformat(),
    }
```

**AI 输出示例（针对 REQ-ESG-001 的 exposure 维度）：**

```json
{
  "pairs": [
    {
      "dimension_a": "materiality",
      "dimension_b": "transition_risk",
      "ratio": 2,
      "reasoning": "贷款金额是EBA指引里material credit exposure概念的直接量化指标，比转型风险更直接反映暴露程度"
    },
    {
      "dimension_a": "transition_risk",
      "dimension_b": "physical_risk",
      "ratio": 2,
      "reasoning": "EBA本次指引的重点在转型风险（碳定价、政策变化），物理风险的信贷传导证据链更弱"
    }
  ],
  "status": "draft",
  "drafted_by": "llm"
}
```

### 2.5 人工审核、签字——通过之后才能解除第2.3节的中止状态

```python
def human_confirm_matrix(draft: dict, reviewer: str,
                          adjustments: dict[tuple, float] | None = None) -> dict:
    """
    reviewer:    审核人姓名/角色（如 "Head of Credit Risk"）
    adjustments: 人工修改的格子，{(dimension_a, dimension_b): new_ratio}
                 人有权修改AI草稿里的任意一格数值
    """
    for pair in draft["pairs"]:
        key = (pair["dimension_a"], pair["dimension_b"])
        if adjustments and key in adjustments:
            pair["original_ratio"] = pair["ratio"]
            pair["ratio"] = adjustments[key]
            pair["adjusted_by"] = reviewer

    draft["status"] = "confirmed"
    draft["confirmed_by"] = reviewer
    draft["confirmed_at"] = date.today().isoformat()
    return draft
```

人工确认后的表，重新写回 `registry`，第2.3节的查找函数下次运行就能直接命中 `status == "confirmed"`，不再中止。

### 2.6 已确认的表，用 AHP 算法转换成具体权重

```python
import numpy as np

def matrix_from_pairs(pairs: list[dict], dimension_names: list[str]) -> np.ndarray:
    n = len(dimension_names)
    idx = {name: i for i, name in enumerate(dimension_names)}
    M = np.eye(n)
    for p in pairs:
        i, j = idx[p["dimension_a"]], idx[p["dimension_b"]]
        M[i, j] = p["ratio"]
        M[j, i] = 1 / p["ratio"]
    return M

def ahp_weights(M: np.ndarray, dimension_names: list[str]) -> tuple[dict, float]:
    n = M.shape[0]
    eigvals, eigvecs = np.linalg.eig(M)
    idx = np.argmax(eigvals.real)
    w = eigvecs[:, idx].real
    w = w / w.sum()

    lam_max = eigvals[idx].real
    CI = (lam_max - n) / (n - 1)
    RI = {3: 0.58, 4: 0.90, 5: 1.12}[n]
    CR = CI / RI

    if CR >= 0.10:
        raise ValueError(
            f"一致性比率 CR={CR:.4f} 超过0.10阈值，说明两两判断内部矛盾，"
            f"必须退回第2.5节，让审核人重新调整矩阵，不能用这组权重。"
        )
    return dict(zip(dimension_names, w)), CR
```

### 2.7 权重存储——版本化，可追溯到是谁、哪一份矩阵算出来的

```json
{
  "requirement_id": "REQ-ESG-001",
  "dimension_set": "exposure",
  "rule_version": "esg-exposure-v4.0",
  "weights": {
    "materiality": 0.40, "transition_risk": 0.25, "physical_risk": 0.15,
    "sector_concentration": 0.13, "review_urgency": 0.07
  },
  "consistency_ratio": 0.0098,
  "derived_from_matrix": { "...": "第2.5节确认后的完整pairs记录" },
  "confirmed_by": "Head of Credit Risk",
  "confirmed_at": "2026-09-08"
}
```

代码往后只从这份配置文件里读权重数字，**打分函数里不允许出现任何写死的百分比**。

### 2.8 中止之后：谁接手、在哪确认、如何重新触发

第2.3节的 `ensure_confirmed_matrices` 抛出异常之后，整个 Part B 流程停在那里——**但异常本身不会自动通知任何人，也不会自动生成一个人可以操作的界面**。这一层如果不明确写清楚，负责实现的同学只能知道"要抛异常"，不知道异常之后系统具体该做什么，这是本节要补的空白。

**这是一个两周原型的范围，所以设计上刻意选最轻量的实现方式，不是完整的审批系统。**

**第一步：异常发生时，把待确认的草稿写入一个人可以查看的队列文件（原型阶段用文件，不需要数据库）。**

```python
import json
from pathlib import Path

PENDING_REVIEW_PATH = Path("06_organisation/pending_matrix_review.json")

def raise_and_queue_for_review(requirement_id: str, pending_keys: list[str], registry: dict):
    """
    ensure_confirmed_matrices 抛异常之前，先把待确认的草稿完整写入队列文件，
    这样审核人不需要读代码或读日志，直接打开这个文件就能看到要审什么。
    """
    queue = []
    if PENDING_REVIEW_PATH.exists():
        queue = json.loads(PENDING_REVIEW_PATH.read_text())

    for key in pending_keys:
        queue.append({
            "queue_id": key,
            "requirement_id": requirement_id,
            "matrix_draft": registry[key],
            "status": "pending_review",
            "queued_at": date.today().isoformat(),
            # 责任人从 06_organisation/roles.json 里查，与该 requirement 所属业务线对应的风险负责角色
            "assigned_reviewer_role": "ROLE-HEAD-CREDIT-RISK",
        })
    PENDING_REVIEW_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2))

    raise RuntimeError(
        f"{pending_keys} 已写入待审核队列 {PENDING_REVIEW_PATH}，"
        f"通知 ROLE-HEAD-CREDIT-RISK 前往确认。流程中止。"
    )
```

**第二步：审核人用一个最简单的命令行脚本来看草稿、做决定——原型阶段不需要做网页界面。**

```python
"""
review_matrix.py —— 审核人在终端里运行这个脚本来处理待审队列
用法：python3 review_matrix.py
"""

def run_review_session():
    queue = json.loads(PENDING_REVIEW_PATH.read_text())
    pending = [q for q in queue if q["status"] == "pending_review"]

    if not pending:
        print("当前没有待审核的两两比较表。")
        return

    for item in pending:
        print(f"\n=== 待审核: {item['queue_id']} ===")
        draft = item["matrix_draft"]
        for pair in draft["pairs"]:
            print(f"  {pair['dimension_a']} vs {pair['dimension_b']}: "
                  f"比例={pair['ratio']}  理由: {pair['reasoning']}")

        decision = input("直接确认输入 y，需要修改输入 adjust，跳过输入 skip：").strip()
        if decision == "skip":
            continue
        if decision == "adjust":
            adjustments = {}
            for pair in draft["pairs"]:
                new_ratio = input(f"  {pair['dimension_a']} vs {pair['dimension_b']} "
                                   f"[回车保留{pair['ratio']}，或输入新数值]：").strip()
                if new_ratio:
                    adjustments[(pair["dimension_a"], pair["dimension_b"])] = float(new_ratio)
            confirmed = human_confirm_matrix(draft, reviewer="当前登录用户", adjustments=adjustments)
        else:
            confirmed = human_confirm_matrix(draft, reviewer="当前登录用户")

        # 写回 registry（原型阶段用文件持久化，正式环境换成数据库）
        registry_path = Path("model_config/pairwise_matrix_registry.json")
        registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
        registry[item["queue_id"]] = confirmed
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2))

        item["status"] = "confirmed"
        print(f"  已确认，写入 {registry_path}")

    PENDING_REVIEW_PATH.write_text(json.dumps(queue, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_review_session()
```

**第三步：谁负责重新触发 Part B——原型阶段是人工重跑，不做自动事件监听。**

审核人确认完矩阵之后，需要有人重新运行一次 Part B 的主流程（`run_part_b`），这次因为 `registry` 里已经有 `confirmed` 状态的矩阵，`ensure_confirmed_matrices` 就不会再中止。**两周原型的范围内，这一步允许是人工手动重跑**（比如审核人在 `review_matrix.py` 跑完之后，被提示"确认完成，请重新运行 Part B"）；如果以后要做成正式产品，这里应该换成审核动作触发的事件（比如往消息队列发一条消息，Part B 服务订阅这个事件自动重跑），但这是超出两周原型范围的工程，本规格不覆盖。

**这一层完整的责任划分：**

| 环节 | 谁负责 | 用什么工具 |
|---|---|---|
| 异常发生，草稿写入队列 | 代码自动完成 | `raise_and_queue_for_review` |
| 通知审核人 | 原型阶段：审核人自己定期看队列文件；不做自动推送 | `pending_matrix_review.json` |
| 审核、确认或修改 | 人（`assigned_reviewer_role` 指定的角色） | `review_matrix.py` 命令行脚本 |
| 重新触发 Part B | 人工手动重跑 | 直接再次调用 `run_part_b` |

---

## 三、表通过之后——硬代码计算 exposure 和 confidence

到这一步，两两比较表已经确认、权重已经算出来，接下来全部是纯代码，不再需要AI。

### 3.1 输入数据

| 文件 | 用到的字段 |
|---|---|
| `03_exposure/lending_portfolio.csv` | `portfolio_record_id`, `product_id`, `outstanding_balance_eur_millions`, `sector_name`, `days_past_due`, `remaining_maturity_years`, `transition_risk_band`, `physical_risk_band`, `esg_data_coverage`, `operating_country`, `borrower_id` |
| `03_exposure/esg_assessment_snapshot.csv` | `portfolio_record_id`, `sector_data_quality`, `assessment_as_of_date` |

### 3.2 Exposure 五个子维度

```python
def score_materiality(balance: float, book_total: float) -> tuple[float, str]:
    """按占组合总额比例分档，不用十分位法（记录数<20时十分位法会失效）"""
    share = balance / book_total
    if share >= 0.15:
        return 100, f"占组合总额 {share:.1%}"
    if share >= 0.10:
        return 75, f"占组合总额 {share:.1%}"
    if share >= 0.05:
        return 50, f"占组合总额 {share:.1%}"
    return 25, f"占组合总额 {share:.1%}"


RISK_BAND_SCORE = {"high": 100, "medium": 60, "low": 20}

def score_risk_band(band: str | None) -> tuple[float | None, str]:
    """转型风险、物理风险共用这套映射。unknown 不给分数，返回None交由第四节处理"""
    if band in RISK_BAND_SCORE:
        return RISK_BAND_SCORE[band], band
    return None, "unknown"


def score_sector_concentration(sector_share: float) -> tuple[float, str]:
    """20%阈值在实测数据上碰不到（最高19.57%），改为分档"""
    if sector_share >= 0.20:
        return 100, f"行业占比 {sector_share:.1%}"
    if sector_share >= 0.15:
        return 75, f"行业占比 {sector_share:.1%}"
    if sector_share >= 0.10:
        return 50, f"行业占比 {sector_share:.1%}"
    return 25, f"行业占比 {sector_share:.1%}"


def score_review_urgency(days_past_due: int, remaining_maturity_years: float) -> tuple[float, str]:
    if days_past_due > 0:
        return 100, f"已逾期 {days_past_due} 天"
    if remaining_maturity_years <= 1.0:
        return 75, f"剩余期限 {remaining_maturity_years} 年"
    if remaining_maturity_years <= 2.0:
        return 50, f"剩余期限 {remaining_maturity_years} 年"
    return 25, f"剩余期限 {remaining_maturity_years} 年"
```

### 3.3 Confidence 四个子维度

```python
NACE_SCORE = {"validated_nace": 100, "broad_nace": 60, "missing_nace": 0}
ESG_COVERAGE_SCORE = {"full": 100, "partial": 70, "limited": 40, "missing": 0}

def score_sector_classification(quality: str) -> float:
    return NACE_SCORE.get(quality, 0)

def score_esg_data_availability(coverage: str) -> float:
    return ESG_COVERAGE_SCORE.get(coverage, 0)

def score_geography(operating_country: str | None) -> float:
    return 100 if operating_country else 0

def score_freshness(assessment_date: str | None, as_of: date) -> float:
    if not assessment_date:
        return 0
    age_days = (as_of - date.fromisoformat(assessment_date)).days
    return 100 if age_days <= 365 else 50
```

### 3.4 缺失维度——AI 尝试推断，推断不了就生成具体问题

**这是本规格里唯一在打分环节之外，仍然允许AI介入的地方，且严格限定它只能"推断"或"提问"，绝不允许它直接给出替代分数。**

```python
def attempt_infer(record: dict, missing_dimension: str, related_records: list[dict]) -> dict:
    """先尝试从同一借款人的其他记录里，推断缺失字段的合理取值"""
    if not related_records:
        return {"status": "no_related_records"}

    prompt = INFER_PROMPT.format(  # 完整prompt见附录B
        missing_dimension=missing_dimension,
        record_json=json.dumps(record, ensure_ascii=False),
        related_records_json=json.dumps(related_records, ensure_ascii=False),
    )
    response = call_llm(prompt)
    if response["status"] == "cannot_infer":
        return {"status": "cannot_infer"}
    return {
        "status": "inferred", "inferred_value": response["value"],
        "source_record_id": response["source_record_id"],
        "requires_human_confirmation": True,   # 推断结果不直接采用，仍需人确认
    }

def generate_specific_question(record: dict, missing_dimension: str) -> str:
    """推断失败，生成一个具体、可直接回答的问题，而不是笼统喊"数据缺失""""
    prompt = QUESTION_PROMPT.format(  # 完整prompt见附录B
        missing_dimension=missing_dimension,
        record_json=json.dumps(record, ensure_ascii=False),
    )
    return call_llm(prompt)
```

### 3.5 汇总、区间处理、Data Debt

```python
def compute_exposure_with_gaps(known_dims: dict, unresolved_dims: list[str],
                                 weights: dict) -> dict:
    base = sum(known_dims[k] * weights[k] for k in known_dims)
    if not unresolved_dims:
        return {"exposure_score": round(base, 1), "exposure_range": [round(base,1)]*2,
                "indeterminate": False}
    lower = base + sum(20 * weights[d] for d in unresolved_dims)
    upper = base + sum(100 * weights[d] for d in unresolved_dims)
    return {"exposure_score": None, "exposure_range": [round(lower,1), round(upper,1)],
            "indeterminate": True, "unresolved_dimensions": unresolved_dims}


def score_data_debt(balance: float, book_total: float,
                     confidence_score: float, urgency_score: float) -> float:
    """衡量"补数据这件事有多急"，不是"这个客户风险有多高"；用几何平均避免分数被压缩失效"""
    exposure_weight = min(balance / book_total / 0.15, 1.0)
    missing_severity = (100 - confidence_score) / 100
    urgency = urgency_score / 100
    product = exposure_weight * missing_severity * urgency
    return round((product ** (1/3)) * 100, 1) if product > 0 else 0.0


BANDS = {"high": 70, "medium": 40}
def band_of(score: float | None) -> str:
    if score is None: return "indeterminate"
    if score >= BANDS["high"]: return "high"
    if score >= BANDS["medium"]: return "medium"
    return "low"
```

---

## 四、最终输出

```json
{
  "record_id": "PORT-SME-008",
  "product_id": "PRD-SME-WORKING-CAPITAL",
  "requirement_id": "REQ-ESG-001",
  "rule_version": "esg-exposure-v4.0",
  "calculation_timestamp": "2026-09-08",

  "exposure_score": null,
  "exposure_range": [25.0, 57.0],
  "exposure_band": "indeterminate",
  "exposure_indeterminate": true,
  "unresolved_dimensions": ["transition_risk", "physical_risk"],

  "confidence_score": 30.0,
  "confidence_band": "low",

  "data_debt_score": 48.1,

  "gap_resolution_log": [
    {"dimension": "transition_risk", "status": "cannot_infer_need_to_ask",
     "generated_question": "该记录缺少行业分类。请确认借款人主营业务是否属于金属加工或类似高转型风险行业？"}
  ],

  "human_review_status": "needs_input"
}
```

**交给 Part C 的关键字段是 `exposure_score`，可能为 `null`，Part C 不得默认当0分处理。**

---

## 五、完整主流程（把一到四节串起来）

```python
def run_part_b(requirement_id: str, in_scope_products: set[str],
                lending_csv: str, esg_csv: str, registry: dict, as_of: date) -> list[dict]:

    # 第一步：查表或生成（第二节）——没有确认过的表，函数会中止并等待人工审核
    exposure_dims = ["materiality", "transition_risk", "physical_risk",
                      "sector_concentration", "review_urgency"]
    confidence_dims = ["sector_classification", "esg_data_availability",
                         "geography_coverage", "assessment_freshness"]

    confirmed = ensure_confirmed_matrices(
        requirement_id, [("exposure", exposure_dims), ("confidence", confidence_dims)], registry)
    exp_matrix = confirmed["exposure"]
    conf_matrix = confirmed["confidence"]

    exp_weights, exp_cr = ahp_weights(matrix_from_pairs(exp_matrix["pairs"], exposure_dims), exposure_dims)
    conf_weights, conf_cr = ahp_weights(matrix_from_pairs(conf_matrix["pairs"], confidence_dims), confidence_dims)

    # 第二步：读数据、过滤（第三节）
    records, esg = [], {}
    with open(lending_csv) as f:
        for r in csv.DictReader(f):
            if r["product_id"] in in_scope_products:
                records.append(r)
    with open(esg_csv) as f:
        for r in csv.DictReader(f):
            esg[r["portfolio_record_id"]] = r

    book_total = sum(float(r["outstanding_balance_eur_millions"]) for r in records)
    sector_total = defaultdict(float)
    for r in records:
        sector_total[r["sector_name"]] += float(r["outstanding_balance_eur_millions"])

    # 第三步：逐条打分（第三、四节）
    results = []
    for r in records:
        rid = r["portfolio_record_id"]
        e = esg.get(rid, {})
        balance = float(r["outstanding_balance_eur_millions"])
        sector_share = sector_total[r["sector_name"]] / book_total

        known, unresolved = {}, []
        known["materiality"], _ = score_materiality(balance, book_total)
        known["sector_concentration"], _ = score_sector_concentration(sector_share)
        known["review_urgency"], _ = score_review_urgency(
            int(r["days_past_due"]), float(r["remaining_maturity_years"]))

        for dim_key, csv_field in [("transition_risk", "transition_risk_band"),
                                     ("physical_risk", "physical_risk_band")]:
            score, _ = score_risk_band(r.get(csv_field))
            if score is None:
                unresolved.append(dim_key)
            else:
                known[dim_key] = score

        exposure = compute_exposure_with_gaps(known, unresolved, exp_weights)

        confidence = round(
            score_sector_classification(e.get("sector_data_quality", "missing_nace")) * conf_weights["sector_classification"]
            + score_esg_data_availability(r.get("esg_data_coverage", "missing")) * conf_weights["esg_data_availability"]
            + score_geography(r.get("operating_country")) * conf_weights["geography_coverage"]
            + score_freshness(e.get("assessment_as_of_date"), as_of) * conf_weights["assessment_freshness"], 1)

        gap_log = []
        for dim in unresolved:
            related = [x for x in records if x["borrower_id"] == r["borrower_id"] and x["portfolio_record_id"] != rid]
            infer = attempt_infer(r, dim, related)
            if infer["status"] != "inferred":
                infer["generated_question"] = generate_specific_question(r, dim)
            gap_log.append({"dimension": dim, **infer})

        urgency_raw = score_review_urgency(int(r["days_past_due"]), float(r["remaining_maturity_years"]))[0]
        debt = score_data_debt(balance, book_total, confidence, urgency_raw)

        results.append({
            "record_id": rid, "product_id": r["product_id"], "requirement_id": requirement_id,
            "calculation_timestamp": as_of.isoformat(),
            "exposure_score": exposure["exposure_score"],
            "exposure_range": exposure["exposure_range"],
            "exposure_band": band_of(exposure["exposure_score"]),
            "exposure_indeterminate": exposure["indeterminate"],
            "unresolved_dimensions": exposure.get("unresolved_dimensions", []),
            "confidence_score": confidence,
            "confidence_band": band_of(confidence),
            "data_debt_score": debt,
            "gap_resolution_log": gap_log,
            "human_review_status": "needs_input" if gap_log else "not_reviewed",
        })

    return results
```

---

## 六、适用范围与代价——这套方法不是无限扩展的通用方案

**这一节必须写清楚，否则容易被误解成"接入任意新监管都能自动搞定"。**

第二节那套"AI起草+人工签字"的流程，本质是用**人力**换**可审计性**——每接入一条新的监管要求，如果它关心的维度跟已有的表不一样（比如 VoP 关心渠道覆盖率而不是行业转型风险），就需要重新走一遍"AI起草、人工审核签字"的完整流程，产生一张新的两两比较表。**这个人工审核的工作量，不会随着监管数量增加而消失，只会跟着线性增加。**

**这套设计适合的场景：** 团队自己精心挑选、少数几条（本项目demo范围是3-4条）需要深入分析的监管要求，每条都值得花时间让专业人士坐下来审核一遍两两比较表。

**这套设计不适合的场景：** 如果未来想做成"系统自动监控成百上千条监管、每条来了都能立刻给出分数"这种全自动化产品，本设计不支持——因为那意味着人工审核这道关卡要么被跳过（回到"AI自己定权重"的老问题），要么审核人力会成为瓶颈。

**如果以后真的要往这个方向扩展，需要在权衡表上做取舍，而不是简单加人力：** 比如可以考虑对"低影响、低金额"的监管要求放宽到不强制人工签字（只需AI起草+抽样复核），把最严格的全流程人工签字留给"高金额、强制性义务"这类监管——但这已经超出两周原型的范围，本规格不覆盖这个扩展设计，只是提前说明这条路径存在、以及它需要额外的取舍决策。

## 附录A：为什么材料性和行业集中度不用原始阈值

在9条SME记录的实测数据上验证过：十分位法（materiality）只能让1条记录拿到满分，其余8条同分，无区分度；20%集中度阈值在实测数据上最高行业占比19.57%，一分不到未触发，权重完全失效。第3.2节的分档规则已经过实测修正。

## 附录B：第3.4节两个prompt的完整文本

```python
INFER_PROMPT = """
下面这条信贷记录缺少"{missing_dimension}"这个字段。
同一借款人在系统里还有其他记录，请判断能不能从中推断出这个缺失字段的合理取值。

严格规则：
1. 只有当关联记录里有明确、直接相关的信息时才给出推断值，模糊或间接的线索不算。
2. 必须输出你依据的是哪条关联记录的哪个字段。
3. 如果无法推断，直接返回 cannot_infer，不要编造。
4. 你的输出只是"建议"，不会自动生效，会转交人工确认。

缺失字段：{missing_dimension}
本记录：{record_json}
同借款人的其他关联记录：{related_records_json}
"""

QUESTION_PROMPT = """
下面这条信贷记录缺少"{missing_dimension}"这个字段，且无法从关联记录推断。
请为负责这个客户的信贷经理生成一个具体、可以直接回答的问题，
帮助他们尽快补上这个信息。不要写空泛的"请补充数据"，要具体到这条记录本身。

记录：{record_json}
"""
```
## 附录C：本规格已用真实数据完整跑通，两个需要知道的实测发现

**验证方式：** 用 `03_exposure/lending_portfolio.csv`（9条SME记录）和 `03_exposure/esg_assessment_snapshot.csv` 真实跑完第二到第五节的完整代码，`call_llm` 用可预测的模拟函数代替真实模型调用（仅用于验证流程走向，不代表真实模型输出质量）。

**跑出来的权重：**

```
Exposure   : 材料性40.8% / 转型风险25.1% / 物理风险14.5% / 集中度13.2% / 紧迫度6.4%  CR=0.0098
Confidence : 行业码35.4% / ESG数据35.4% / 地理13.1% / 新鲜度16.1%              CR=0.0076
```

两个一致性比率都远低于0.10阈值，矩阵有效；额外用一组故意矛盾的两两比较（A比B重要5倍、B比C重要5倍、但C又比A重要5倍）验证过，一致性检验确实会拦下这种矛盾矩阵并抛出异常，不会带着错误权重继续往下算。

**发现一：`ensure_confirmed_matrices`（2.3节）的批量检查逻辑，是跑出来之后才发现原设计有问题，已改正。** 最初按"发现一张表缺失就立刻中止"来写，实测发现这样跑一次只能补全一张表，要运行三次才能真正开始算分，体验很差。现在的版本改成一次性检查 exposure 和 confidence 两张表，缺哪张都一起生成草稿，一次性交给人确认。

**发现二：当前数据下，"从关联记录推断"这条路径永远走不到。** 实测发现这9条SME记录，每个 `borrower_id` 只对应一笔贷款，没有任何借款人有第二笔记录。这意味着第3.4节 `attempt_infer` 函数，现在跑起来100%会返回 `no_related_records`，直接落到"生成具体问题"这条路。**这不是代码逻辑的缺陷，是当前demo数据的特征**——如果想在demo里真正演示"AI成功从关联记录推断出缺失值"这个场景，需要在数据里补至少一位有两笔以上贷款记录的借款人，这属于数据侧的工作，不是本规格要改的地方。

