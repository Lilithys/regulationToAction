# First-Demo Design

This reference translates the work-allocation brief into four research and data-design tracks. The identifiers and URLs below are **research starting points, not permission to copy facts without runtime verification**. Recheck every title, version, status, date, provision, and related measure against official sources as of the requested cut-off.

## Shared demo principle

The four topics test different reasoning paths:

| Topic | Intended reasoning test | Expected joined-dataset outcome |
| --- | --- | --- |
| EBA ESG-risk management | Portfolio exposure + governance/data/control gap | High exposure |
| Instant Payments Regulation | Product/channel/process/system gap | High exposure; web covered, mobile missing |
| DORA | Critical-service/system/vendor/dependency traversal | High exposure; dependency mapping incomplete |
| FRTB change | Evidence-based restraint / negative case | Limited applicability; monitor rather than force remediation |

These expected outcomes belong to evaluation ground truth. Do not place them as answer labels in the five Person 1 operational files. Encode only the real external requirements and the agreed underlying synthetic governance facts.

## 1. EBA ESG-risk management guidelines

### Research starting point

- Suspected final reference: **EBA/GL/2025/01, Guidelines on the management of environmental, social and governance (ESG) risks**.
- Official EBA publication page: <https://www.eba.europa.eu/publications-and-media/press-releases/eba-publishes-its-final-guidelines-management-esg-risks>
- The final EBA document, its legal basis, exact application dates, institution classes, and any later corrections/translations must be verified at runtime.
- Check relevant CRD/CRR provisions on EUR-Lex when the guideline derives its scope or mandate from them.

### Requirement families to inspect

Select material, independently testable obligations/expectations from the final text, potentially covering:

- governance and allocation of responsibilities;
- integration of ESG risks into strategies, risk appetite, policies, and risk management;
- identification, measurement, management, and monitoring methods;
- data processes and assessment of counterparties/exposures;
- institution plans and time horizons;
- proportionality and any differentiated application for small/non-complex institutions.

This is a research checklist, not a prewritten set of requirements. Include only provisions actually located and supported.

### Synthetic governance design

The work-allocation scenario supplies these intended underlying facts:

- the joined bank dataset contains a material SME credit portfolio;
- ESG data is incomplete;
- no formal portfolio-wide ESG-risk control exists.

Person 1 may design a coherent partial current state, for example a risk policy that acknowledges ESG and a narrowly scoped onboarding or sector-screening control. Do not create a portfolio-wide monitoring control or complete-data procedure, because that would erase the intended gap. Do not claim the material SME exposure or specific missing data fields unless Person 2/3 files contain them.

Required handoffs may include:

- Person 2: portfolio IDs, materiality facts, customer/exposure classes;
- Person 3: ESG data-asset and risk-system IDs, lineage/completeness facts;
- Person 4: accountable role, cost centre, action, cost, and closure-evidence IDs.

## 2. Instant Payments Regulation

### Research starting point

- Suspected primary instrument: **Regulation (EU) 2024/886** on instant credit transfers in euro.
- Suspected CELEX: **32024R0886**.
- Official EUR-Lex ELI page: <https://eur-lex.europa.eu/eli/reg/2024/886/oj>
- Treat the regulation as an amending act. Inspect the amended provisions in their legal context and verify whether a current consolidated base act is available.
- Application dates may differ by obligation, PSP type, euro-area status, and service; encode each relevant date separately after verification.

### Requirement families to inspect

Potential material families include:

- sending and receiving instant credit transfers;
- charges;
- verification of payee/payee verification service;
- sanctions-screening arrangements;
- customer/channel availability, where supported by the actual provision;
- reporting, transition, or institution-specific dates.

Do not infer that the legal text literally says `mobile` merely because the demo gap is mobile. The external requirement should remain channel-neutral if the source is channel-neutral. Channel coverage belongs to internal control scope.

### Synthetic governance design

The agreed scenario fact is:

```text
Verification of Payee works for the web channel and is missing from mobile banking.
```

Represent it through:

- a payment-security policy with relevant intent;
- `CTRL-VOP-WEB` or an established equivalent whose coverage explicitly includes `web` and excludes/does not cover `mobile`;
- a web operating procedure mapped to the control;
- no invented mobile control or procedure.

Use `operating_status: "operating"` only if an existing synthetic evidence record explicitly authorizes that assertion. Otherwise distinguish `designed` current capability from proven operating effectiveness.

Required handoffs may include:

- Person 2: `BL-PAYMENTS`, `PRD-SEPA-INSTANT`, payment/channel exposure facts;
- Person 3: payment-initiation process, mobile/web systems, payments hub, VoP data/vendor dependencies;
- Person 4: approved owners, costs, actions, and required evidence.

## 3. DORA

### Research starting point

- Primary instrument: **Regulation (EU) 2022/2554** on digital operational resilience for the financial sector.
- Suspected CELEX: **32022R2554**.
- Official EUR-Lex ELI page: <https://eur-lex.europa.eu/eli/reg/2022/2554/oj>
- Research related amending Directive (EU) 2022/2556 and only those delegated/implementing measures necessary for selected requirements.
- Verify the current consolidated text, application date, covered entity definition, proportionality, and any material current technical standards as of the cut-off.

### Requirement families to inspect

For the intended dependency-mapping demo, prioritize source-supported requirements concerning:

- ICT risk-management framework and governance;
- identification/classification/documentation of ICT-supported business functions, information assets, ICT assets, and dependencies;
- critical or important functions/services;
- ICT third-party risk and contractual/information-register arrangements;
- incident handling/reporting and resilience testing only when needed for coherent coverage.

Do not attempt to reproduce all of DORA. State the selected requirement scope and omitted families in notes.

### Synthetic governance design

The work-allocation scenario supplies this intended underlying condition:

```text
Critical-service and third-party dependency mapping is incomplete.
```

Create a current-state ICT/operational-resilience policy and partial mapping control/procedure only if they do not contradict Person 3 data. The control may cover some critical services or dependencies and explicitly mark the uncovered dimension. Do not invent a system, vendor, critical-service, contract, or dependency ID.

Required handoffs may include:

- Person 3: complete lists and IDs for critical services, systems, vendors, data assets, and dependencies, including which mappings are absent;
- Person 4: accountable roles, RACI, action, cost, and closure evidence.

## 4. FRTB change

### Research starting point

`FRTB change` is not a sufficient legal citation. Resolve the exact EU implementation event current at the research cut-off.

Start with:

- **Regulation (EU) 2024/1623 (CRR III)** amending Regulation (EU) No 575/2013, plus the current consolidated CRR;
- the European Commission's official CRR implementing/delegated-acts page: <https://finance.ec.europa.eu/regulation-and-supervision/financial-services-legislation/implementing-and-delegated-acts/capital-requirements-regulation_en>;
- current EUR-Lex texts for any operative delegated act, postponement, transitional relief, or targeted market-risk measure.

FRTB timing and EU implementation can change through delegated acts. Distinguish `adopted`, `published in the Official Journal`, `entered into force`, and `applicable`. A Commission adoption page or draft PDF does not by itself prove an act is in force.

### Requirement families to inspect

Depending on the exact selected change, inspect:

- scope and conditions for market-risk own-funds requirements;
- trading-book/trading-desk classification and thresholds;
- standardised versus internal-model approach conditions;
- reporting/disclosure or monitoring obligations relevant even when materiality is limited;
- application timing, transition, postponement, or temporary relief.

Select only the obligations needed to demonstrate traceable limited applicability. Do not make a broad statement that FRTB is wholly `not applicable` if monitoring, classification, or threshold evidence is still required.

### Synthetic governance design

The intended joined-dataset facts are:

- no material trading desk;
- no significant trading book;
- no internal market-risk model.

These are Person 2/3 facts, not Person 1 inventions. Person 1 should:

- encode the legal criteria and bank facts required to decide applicability;
- map a proportionate market-risk/trading-book policy or monitoring control only if supported by the synthetic scenario;
- leave the applicability result `unknown` or `not_assessed` inside Person 1 data until those facts resolve;
- avoid creating remediation merely because a regulation exists.

The expected downstream behavior is a sourced, evidence-backed limited-applicability conclusion plus a proportionate monitoring action, not a manufactured high-impact gap.

## Cross-topic design rules

### Minimal coherent governance, not document volume

Create only records that help establish current capability or an intentional gap. A useful record must link to at least one selected requirement. Avoid generic policies that add no evaluable fact.

### Preserve deliberate asymmetry

The demo needs partial capability and a negative case:

- ESG: some awareness or narrow practice may exist, but no formal portfolio-wide control.
- Instant Payments: web VoP exists, mobile VoP does not.
- DORA: some ICT/dependency governance exists, but mapping is incomplete.
- FRTB: the agent must be able to conclude limited applicability from downstream facts rather than invent a gap.

### Do not smuggle downstream truth into Person 1

Person 1 may reference a valid `BL-*`, `PRD-*`, `PROC-*`, `SYS-*`, `DATA-*`, `VND-*`, `ROLE-*`, `ACT-*`, `CC-*`, or `EVD-*` ID only when the owner file contains it. If a planned ID appears only in the work-allocation example, it is not yet a fact. Record a missing dependency until the responsible person creates it.

### Avoid evaluation leakage

Do not use fields such as:

```json
{
  "expected_outcome": "HIGH",
  "ground_truth_applicability": "LIMITED",
  "correct_answer": true
}
```

inside the five operational files. Person 4 may maintain expected assessments in `evaluation_ground_truth/`. Person 1 can provide a separate human handoff explaining the evidence path, but it must not become a retrieval input during evaluation.

## Demo-readiness check

For each topic, verify that the joined data can eventually answer:

1. What changed, in which exact official instrument?
2. Which atomic requirements were selected, and where are they located?
3. What bank facts are required for applicability?
4. Which policy statements address the requirement?
5. Which current controls cover which dimensions?
6. Which procedures operate those controls?
7. What remains uncovered or unknown?
8. Which process/system/data/vendor facts are needed next?
9. Which owner/cost/action/evidence facts are still owned elsewhere?

If Person 1 data answers questions 1–7 truthfully and hands off 8–9 without invention, its first-demo contribution is ready.
