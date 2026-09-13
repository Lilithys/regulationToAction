# Bank Context: Northstar Digital Bank (Fictional)

## Purpose

This is a synthetic company profile for testing the Regulatory Change-to-Action Agent. It represents a medium-sized, online-only European bank. All figures, systems, people, and names are fictional.

## Bank At A Glance

| Field | Value |
| --- | --- |
| Legal name | Northstar Digital Bank plc (NDB) |
| Type | EU credit institution; online-only retail, mortgage, and SME bank |
| Headquarters | Dublin, Ireland |
| Primary regulator | Central Bank of Ireland |
| Operating model | Mobile app and web banking only; no physical branches |
| Employees | 1,150 FTEs |
| Active customers | 1.4 million retail; 85,000 SME |
| Total assets | EUR 12.5 billion |
| Customer deposits | EUR 9.8 billion |
| Loan book | EUR 9.2 billion |
| Financial year | Calendar year |
| Reporting currency | EUR |

## Geographic Footprint

NDB is licensed in Ireland and provides cross-border digital services within the EU/EEA. Its main customer markets are Ireland, Germany, Netherlands, Belgium, Spain, and France.

| Geography | Activity | Approximate share of customers |
| --- | --- | ---: |
| Ireland | Home market; legal entity, risk, finance, and core operations | 35% |
| Germany | Major retail deposit and consumer-credit market | 25% |
| Netherlands and Belgium | Retail banking and SME accounts | 18% |
| Spain and France | Retail deposits and consumer credit | 17% |
| Other EEA | Limited passported services | 5% |

The bank does not serve customers outside the EEA and does not operate UK or US branches.

## Business Lines

| Business line | Main customers | Products | Materiality |
| --- | --- | --- |
| Retail Banking | Individuals | Current accounts, savings, debit cards, consumer loans | High |
| Mortgage Banking | Individuals | Digital residential mortgages and mortgage arrears support | Medium |
| SME Banking | Small and medium enterprises | Business accounts, payment cards, working-capital loans | Medium |
| Lending | Retail and SMEs | Unsecured personal loans, residential mortgages, green home-improvement loans, SME working-capital loans | High |
| Payments | Retail and SMEs | SEPA transfers, card payments, open-banking payment initiation | High |
| Treasury | Bank balance sheet | Liquidity portfolio, deposit pricing, wholesale funding | Medium |

NDB does not provide investment banking, wealth management, client trading, insurance underwriting, or crypto-asset services. Treasury maintains a small liquidity portfolio, but NDB has no material trading desk or internal market-risk model.

## Lending And Portfolio Context

| Portfolio | Outstanding balance | Key characteristics |
| --- | ---: | --- |
| Unsecured consumer loans | EUR 4.7bn | Automated underwriting; mostly Ireland and Germany |
| Residential mortgages | EUR 1.1bn | Ireland only; originated digitally and serviced by a specialist third-party provider |
| Green home-improvement loans | EUR 1.1bn | Energy-efficiency upgrades; voluntary green-product proposition |
| SME working-capital loans | EUR 2.3bn | Smaller businesses; exposure concentrated in services, retail, and light manufacturing |

For a first ESG-risk use case, the SME portfolio is the most useful starting point because borrower sector, turnover, location, and loan purpose are already recorded but environmental-risk data is incomplete.

## Key Processes And Capabilities

| Process / capability | Current state | Primary owner |
| --- | --- | --- |
| Digital customer onboarding and KYC | Automated with manual exception handling | Financial Crime Operations |
| Credit origination | Automated scorecards with policy rules | Retail and SME Lending |
| Credit risk monitoring | Monthly portfolio monitoring; limited ESG-risk indicators | Risk Management |
| Mortgage arrears management | Third-party servicing with NDB case approval and monthly oversight | Mortgage Operations |
| Alternative repayment arrangements (ARA) | Standard affordability assessment and documented approval hierarchy | Mortgage Operations and Credit Risk |
| Regulatory reporting | Central reporting team, manual reconciliation for some reports | Finance Regulatory Reporting |
| Data governance | Enterprise data catalogue and data-quality controls | Chief Data Office |
| Model risk management | Formal validation for material credit-risk models | Model Risk |
| Third-party management | Vendor due diligence and annual reassessment | Procurement and Operational Risk |
| Change delivery | Agile product and technology teams | Technology Delivery |
| Instant payments | Receive and send SEPA Instant; Verification of Payee is available on web, not mobile | Payments Operations |
| ICT resilience | Critical-service register and annual disaster-recovery tests; vendor dependency mapping is incomplete | Technology Risk |

## Technology And Data Landscape

| Asset | Purpose | Important data / dependency |
| --- | --- | --- |
| Core banking platform | Accounts, deposits, loan servicing | Customer, account, transaction, loan data |
| Digital onboarding platform | Identity verification and KYC | Identity, sanctions, customer-risk data |
| CRM and customer-profile service | Customer circumstances, product holdings, communications, and servicing cases | KYC refresh, suitability, and material-change history |
| Loan origination system | Applications, affordability, approvals | Income, employment, loan purpose, borrower sector |
| Mortgage servicing platform | Mortgage balances, arrears, ARA cases, repayment history | Servicer case records and affordability evidence |
| Enterprise data platform | Regulatory, risk, finance, and analytics datasets | Data lineage, quality rules, reporting datasets |
| Risk engine | Credit-risk scores and portfolio monitoring | PD/LGD inputs, exposures, arrears, sector data |
| GRC platform | Obligations, policies, controls, issues, evidence | Control owners and testing results |
| Payments hub | SEPA Credit Transfer and SEPA Instant processing | Payment status, latency, beneficiary, channel, and failure data |
| Verification of Payee service | Payee-name verification before payment execution | External provider; web integration is live, mobile integration is pending |
| ICT service register | Maps critical services to applications, infrastructure, and vendors | Criticality, RTO/RPO, test results, and incomplete subcontractor mapping |

Most core systems are cloud-hosted within the EEA. NDB relies on three material external technology providers: its core banking platform provider, cloud infrastructure provider, and identity-verification provider.

## Data Available For Regulatory Assessment

| Data domain | Coverage | Known limitations |
| --- | --- | --- |
| Customer and legal entity | High | SME ownership structures may require manual verification |
| Loans and exposures | High | Loan-purpose codes are inconsistent for older loans |
| Mortgage arrears and ARA cases | High | Third-party servicer sends a monthly extract; some supporting documents are held outside NDB systems |
| SME sector classification | Medium | NACE code missing or broad for approximately 20% of SMEs |
| Geography | High | Customer domicile and borrower operating country available |
| Consumer circumstances and material changes | Medium | Customer profile exists, but a structured re-confirmation event is not captured before every further sale |
| Payment operations | High | Volumes, channel, latency, failures, beneficiary data, pricing, and sanctions outcomes available |
| ICT assets and third parties | Medium | Application and vendor inventories exist; end-to-end dependencies and subcontractors are incomplete |
| Financial performance | High | Product-level profitability refreshed monthly |
| ESG / climate-risk data | Low | No complete borrower emissions or physical-risk dataset |
| Controls and policies | Medium | Existing control inventory is current; evidence links vary in quality |

## Governance, Controls, And Policies

| Area | Example current control | Control maturity |
| --- | --- | --- |
| Regulatory change | Compliance logs material changes and assigns accountable owners | Medium |
| Consumer protection | Customer-information and suitability policies; periodic KYC refresh rather than event-driven re-confirmation | Medium |
| Credit risk | Credit policies define approval, affordability, and monitoring requirements | High |
| Mortgage arrears | ARA policy, case review, and monthly outcome monitoring | Medium |
| ESG risk | General sustainability policy; no portfolio-wide ESG-risk assessment control | Low |
| Product governance | Product approval and annual review process; no retail product carries an ESG claim | Medium |
| Payments | Sanctions and fraud controls operate continuously; mobile Verification of Payee control is absent | Medium |
| Data quality | Critical regulatory data elements have monthly checks and issue management | Medium |
| Model governance | Material models require validation and annual review | High |
| Outsourcing | Material vendors have risk assessments and exit plans | Medium |
| Digital operational resilience | ICT risk policy and annual recovery tests; complete critical-service dependency mapping is not evidenced | Medium |

## Organisation And Cost Centres

| Cost centre | Function | Indicative annual run cost | Typical responsibility |
| --- | --- | ---: | --- |
| CC-100 Lending | Retail and SME Lending | EUR 42m | Product policy, credit decisions, portfolio actions |
| CC-200 Risk | Enterprise and Credit Risk | EUR 18m | Risk framework, monitoring, challenge, model risk |
| CC-300 Data-IT | Data, Engineering, Security, Technology Delivery | EUR 76m | Data sourcing, systems, integrations, change delivery |
| CC-400 Finance | Finance and Regulatory Reporting | EUR 14m | Prudential reporting, financial impact, reconciliations |
| CC-500 Compliance | Compliance, Legal, Financial Crime | EUR 16m | Interpretation, obligation management, evidence, training |
| CC-600 Payments | Payments Operations and Fraud | EUR 13m | Payment operations, scheme compliance, fraud controls, customer support |
| CC-700 Mortgage | Mortgage Operations and Customer Support | EUR 9m | Mortgage servicing oversight, arrears cases, ARA approvals |

Use cost centres to allocate delivery and ongoing run costs, but retain the process, system, control, and accountable-owner links. A cost centre alone cannot show how a regulatory obligation affects the bank.

## Material KPIs And Economics

| KPI | Baseline |
| --- | ---: |
| Consumer-loan applications per year | 620,000 |
| SME loan applications per year | 32,000 |
| New loans originated per year | EUR 3.4bn |
| Net interest margin | 3.2% |
| Average lending operations labour cost | EUR 52 per hour |
| Average risk / compliance labour cost | EUR 68 per hour |
| Material technology change day rate | EUR 850 per person-day |
| Target regulatory-change delivery window | 6-12 months |
| SEPA Instant payments per year | 8.6 million |
| Mobile share of payment initiation | 71% |
| Mortgage accounts in arrears | 3,800 |
| Critical business services | 5 |

## Regulatory Shock Coverage

The following synthetic facts are intentionally included so the agent can assess a limited selection of the changes described in `11.docx`. This is not a legal interpretation of those regulations.

| Regulatory shock | Expected assessment | Why this bank context supports it |
| --- | --- | --- |
| Irish Consumer Protection Code 2025 and 2026 amendment | High | NDB sells retail products online and has a gap in recording material customer-circumstance changes before a further sale or recommendation. |
| Mortgage arrears / ARA guidance | Medium | NDB has an Irish mortgage book, arrears cases, an ARA process, and a third-party servicer. |
| EBA ESG-risk management guidelines | High | SME credit is material, but ESG portfolio data and the formal ESG-risk control are incomplete. |
| EBA environmental scenario analysis guidelines | Medium | NDB has exposure, PD/LGD, geography, and capital data, but no environmental scenario capability. |
| Instant Payments Regulation | High | NDB supports instant payments but lacks Verification of Payee in its mobile channel. |
| DORA | High | The bank relies on material cloud, core-banking, identity, and mortgage-servicing providers, while dependency mapping is incomplete. |
| EBA ESG product-governance guidance | Low / indirect | NDB has green home-improvement lending but makes no ESG retail-product claim and has no green savings or sustainability-linked retail product. |
| FRTB implementation change | Limited / monitor only | NDB has no material trading desk, trading book, or internal market-risk model. |

## Additional Context For Shock Assessment

### Consumer Protection And Product Governance

NDB distributes all retail products through its mobile app and website. It may offer customers a further product, such as a personal loan after opening a current account, using customer-profile and affordability information collected during onboarding. The current workflow refreshes KYC information periodically, but does not force the customer or staff to re-confirm whether material circumstances have changed before every recommendation or further sale.

Relevant evidence includes the Customer Information Policy, suitability workflow, CRM field definitions, recommendation logs, customer communications, complaints data, compliance-monitoring results, and staff training records.

### Mortgage Arrears And Alternative Repayment Arrangements

Mortgage servicing is performed by a material third-party provider under NDB's policies. NDB retains responsibility for arrears strategy, vulnerable-customer outcomes, approval criteria, and oversight. Alternative repayment arrangements include term extensions, temporary interest-only periods, and split repayments. About 3,800 mortgage accounts are in arrears, of which 650 have an active ARA.

Relevant evidence includes individual affordability assessments, ARA decision records, approval logs, customer communications, complaints, outcome monitoring, servicer oversight reports, and policy exceptions.

### Payments And Instant Payments

NDB has been able to receive and send euro instant payments since 2025. Verification of Payee is available for web-initiated payments but is not implemented in the mobile app, which originates 71% of payment instructions. The payments hub, mobile app, beneficiary store, sanctions engine, fraud engine, customer-notification service, and external Verification of Payee provider form the critical payment chain.

Relevant evidence includes channel capability records, payment pricing rules, transaction and failure metrics, sanctions and fraud-control procedures, vendor contract/SLA records, customer disclosures, release records, and 24/7 incident logs.

### Digital Operational Resilience

NDB identifies five critical business services: customer login and account access, payments, customer onboarding, loan origination, and mortgage servicing. Each has an accountable business owner, application owner, and recovery target. The service register does not consistently map cloud components and vendor subcontractors to each service, making it difficult to evidence complete dependency oversight.

Relevant evidence includes the ICT asset inventory, critical-service register, vendor inventory and contracts, outsourcing risk assessments, RTO/RPO targets, disaster-recovery tests, incident records, security assessments, and remediation actions.

### Low-Exposure Boundary Cases

NDB's green home-improvement loan is priced by loan purpose and does not make a marketed environmental-performance claim. It has no green savings account, sustainable investment product, or sustainability-linked retail loan. The agent should therefore assess ESG retail-product governance as indirect and low exposure, while still flagging an optional product-governance review.

NDB's treasury liquidity portfolio is managed for liquidity rather than trading. There are no client-facing trading desks, trading-book positions, internal risk transfers, or internal market-risk models. The agent should classify FRTB-related change as limited applicability and create a monitoring action only.

## Initial Regulatory Change Scenario

Use the EBA ESG-risk management guidelines as the hero scenario. NDB must identify, assess, manage, and monitor ESG risks for material SME credit exposures, with a documented plan for the existing portfolio.

### Likely Exposure Path

```text
Requirement: ESG-risk assessment for material SME credit exposures
    -> Applies to: NDB as an EU credit institution
    -> Relevant portfolio: SME working-capital loans
    -> Capability gap: incomplete NACE and ESG-risk data; no formal control
    -> Systems affected: loan origination, data platform, risk engine, GRC
    -> Owners: Risk (accountable), Lending and Data-IT (delivery), Compliance (interpretation)
    -> Cost centres: CC-100, CC-200, CC-300, CC-500
    -> Evidence: revised policy, data-quality reports, model/change records, control-test results
```

## Boundaries For The First Prototype

Include only the SME working-capital portfolio, one legal entity, and the five cost centres above. Treat all data as synthetic. This scope is sufficient to demonstrate applicability, business exposure, capability gaps, costed actions, ownership, and evidence without building a full bank digital twin.
