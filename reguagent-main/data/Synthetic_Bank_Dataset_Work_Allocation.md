# Synthetic Bank Dataset Work Allocation

## Goal

Create a small, internally consistent synthetic dataset that allows the Regulatory Change-to-Action Agent to reason from a regulatory requirement to applicability, exposure, capability gap, owner, costed action, and evidence.

## Team Split

| Person | Scope | Files to create |
| --- | --- | --- |
| 1. Regulatory and governance | Converts selected regulatory shocks into structured requirements and documents the bank's current policies, procedures, and controls. | `regulatory_sources/requirements.json`, `regulatory_sources/change_register.json`, `04_governance/policies.json`, `04_governance/controls.json`, `04_governance/procedures.json` |
| 2. Business and customer exposure | Defines what the bank does, its products, customers, lending, mortgages, payments, and deliberately limited trading activity. | `01_entity/bank_profile.json`, `02_business/business_lines.json`, `02_business/products.json`, `03_exposure/lending_portfolio.csv`, `03_exposure/mortgage_book.csv`, `03_exposure/payments.csv`, `03_exposure/trading_book.csv` |
| 3. Operations and technology | Builds the operational side of the Business Digital Twin: processes, systems, data assets, vendors, critical services, and dependencies. | `05_operations/processes.json`, `05_operations/systems.json`, `05_operations/data_assets.json`, `05_operations/dependencies.json`, `05_operations/vendors.json`, `05_operations/critical_services.json` |
| 4. Organisation, economics, and evidence | Makes recommended actions assignable, costable, trackable, and verifiable. | `06_organisation/roles.json`, `06_organisation/raci.csv`, `07_economics/operational_costs.csv`, `07_economics/change_capacity.csv`, `08_evidence/actions.json`, `08_evidence/evidence_register.json`, `evaluation_ground_truth/expected_assessments.json` |

## Shared ID Rules

Every team should use the same stable identifiers so records can be linked without relying on ambiguous names.

| Entity | ID example |
| --- | --- |
| Regulatory change | `REG-IPS-2024-886` |
| Requirement | `REQ-IPS-VOP-MOBILE` |
| Business line | `BL-PAYMENTS` |
| Product | `PRD-SEPA-INSTANT` |
| Portfolio / dataset record | `PORT-SME-WC-001` |
| Process | `PROC-PAYMENT-INITIATION` |
| System | `SYS-PAYMENTS-HUB` |
| Data asset | `DATA-PAYMENT-TRANSACTIONS` |
| Vendor | `VND-VOP-PROVIDER` |
| Control | `CTRL-VOP-WEB` |
| Role / owner | `ROLE-HEAD-PAYMENTS` |
| Cost centre | `CC-600` |
| Action | `ACT-IPS-MOBILE-VOP` |
| Evidence item | `EVD-IPS-MOBILE-RELEASE` |

Each record should include its own ID and references to the related IDs. For example, an action should reference the requirement, affected process, system, control, owner, cost centre, and required evidence.

## First Demo Scope

Start with four changes. They cover distinct reasoning patterns while keeping the dataset manageable.

| Change | Expected outcome | Main data packages |
| --- | --- | --- |
| EBA ESG-risk management guidelines | High exposure: material SME credit portfolio, incomplete ESG data, and no formal portfolio-wide ESG-risk control. | Requirements, lending portfolio, risk policies, systems/data, roles, economics, evidence |
| Instant Payments Regulation | High exposure: Verification of Payee works on web but is missing from mobile banking. | Requirements, payments data, payment process and systems, vendor dependency, owners, costs, evidence |
| DORA | High exposure: critical-service and third-party dependency mapping is incomplete. | Requirements, critical services, systems, vendors, controls, RACI, evidence |
| FRTB change | Limited applicability: the bank has no material trading desk, trading book, or internal market-risk model. | Requirements, business profile, minimal trading-book file, monitoring action |

## Second Demo Scope

Add these after the first four changes run end-to-end.

| Change | Expected outcome |
| --- | --- |
| Irish Consumer Protection Code 2025 and 2026 amendment | High: customer circumstances are not re-confirmed before every further sale or recommendation. |
| Mortgage arrears / ARA guidance | Medium: a mortgage portfolio, arrears cases, and third-party servicer oversight require process and control assessment. |
| EBA environmental scenario analysis guidelines | Medium: risk data exists but environmental scenario-analysis capability does not. |
| EBA ESG product-governance guidance | Low / indirect: no marketed ESG retail product, but optional governance review. |

## Definition Of Done

The first dataset is ready when the agent can produce a traceable assessment for each first-demo change:

```text
Regulatory change
  -> requirement
  -> applicability and confidence
  -> affected bank facts and exposure
  -> current policy / control / capability
  -> gap
  -> impacted process, system, data, and vendor
  -> accountable owner and cost centre
  -> action options and estimated cost
  -> evidence needed for closure
```

The agent must return `insufficient evidence` when a necessary company fact is missing. It must not invent internal capabilities, owners, controls, or costs.
