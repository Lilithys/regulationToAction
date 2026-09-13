# Regulatory Change-to-Action Agent — Brief Design

## Product idea

**Regulation → Exposure → Business impact → Costed action → Evidence**

Hero scenario: a fictional EU bank preparing for one narrowly defined ESG-risk requirement. The product is not a legal-summary chatbot; it identifies where the organisation must change and supports a defensible response decision.

## Core logic

| Stage | Question | Agent logic | Main output |
|---|---|---|---|
| 1. Regulatory intelligence | What changed? | Monitor authoritative sources; compare versions; extract obligations, scope, dates and citations | Traceable change alert |
| 2. Exposure intelligence | Should/where/how much should we care? | Match legal scope to entity; map obligation drivers to portfolio/business facts; compare requirement with current capability | Exposure map, confidence, missing facts |
| 3. Business impact intelligence | What must change? | Traverse the Business Digital Twin: business line → capability → process → people/data/system/control | Impact graph and control gaps |
| 4. Response intelligence | What should we do? | Generate options; calculate cost, operating/revenue/risk effects; test deadline feasibility; assign owners | Recommended programme and evidence plan |

## Key design distinction

- **Applicability:** direct / indirect / out of scope / uncertain.
- **Business exposure:** relevance and materiality by business line.
- **Change exposure:** regulatory requirement minus current capability.

Do not let the LLM invent a single “high impact” label. Use transparent factors:

`Exposure = f(applicability, business relevance, materiality, capability gap, time pressure)`

Report **exposure and confidence separately**. Low confidence triggers targeted questions, then recalculation.

Suggested bands: `0–20 Monitor`, `21–40 Potential`, `41–60 Material`, `61–80 High`, `81–100 Critical`.

## Business model

Build a lightweight **Business Digital Twin / Context Graph** from synthetic annual reports, product lists, policies, controls, portfolio data and system inventories:

`Entity → Business line → Product → Customer/sector → Process → Data/System → Control → Owner → KPI/economics`

Every inferred node keeps its source and confidence. Optional peer data is used only to propose missing-business hypotheses, never as proof of the bank's activities.

## Quantitative response design

The LLM identifies impact drivers and proposes a calculation schema; a deterministic engine performs the maths.

`Total cost = people + technology + data/vendor + training + legal`

`Operating impact = affected volume × added handling time × labour rate`

`Revenue impact = affected exposure × activity change × margin`

`Risk cost = non-compliance probability × expected loss`

Compare manual, automated and hybrid options using 3-year cost, compliance risk, customer friction and delivery time. Allow what-if changes to volume, automation rate, rates and deadlines; show ranges and assumptions rather than false precision.

## Two-week build

Use one EU bank, one ESG-risk change, five functions (Lending, Risk, Data/IT, Finance, Compliance), and about 15 synthetic policies/controls.

1. Ingest two versions of one authoritative document and extract cited obligation changes.
2. Store a small typed graph in JSON/relational tables; use vector search only for evidence retrieval.
3. Implement exposure rules plus an LLM investigator that queries portfolio/control facts and asks for missing inputs.
4. Traverse the graph to produce affected processes, systems, data and controls.
5. Run deterministic calculations for three response options.
6. Create owner/deadline tasks and require uploaded evidence plus human compliance sign-off.

## Demo flow and success criteria

1. Change detected with exact source/version/effective date.
2. Agent investigates taxonomy → portfolio → controls, asks one material missing fact, and updates its score.
3. Heatmap shows each business line's exposure and confidence.
4. Impact graph identifies gaps and their evidence.
5. What-if simulator compares three costed responses and recommends one.
6. Action plan has owners, deadlines, evidence status and qualified human review.

Success means relevant change detection, accurate obligation/business mapping, full traceability, action ownership and verifiable completion evidence. Clearly label **source text**, **machine interpretation**, **assumptions** and **human-approved advice**.
