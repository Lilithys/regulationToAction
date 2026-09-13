# Generated Business And Customer Exposure Package

## Contents

This folder contains the seven files assigned to "2. Business and customer exposure" in `Synthetic_Bank_Dataset_Work_Allocation.md`.

```text
01_entity/bank_profile.json
02_business/business_lines.json
02_business/products.json
03_exposure/lending_portfolio.csv
03_exposure/esg_assessment_snapshot.csv
03_exposure/mortgage_book.csv
03_exposure/payments.csv
03_exposure/trading_book.csv
```

## Reference Basis

The schema and digital-bank operating model were informed by the public bunq reference files in `Regulation_reference/`:

- `bunq-report-annual-2025-en.pdf`
- `bunq-report-pillar-3-disclosures-2025-en.pdf`
- `bunq-report-esg-2025-en.pdf`
- `bunq-policy-tax-en.pdf`
- `bunq-report-tax-2025-en.pdf`

Northstar Digital Bank, every identifier, every customer/borrower record, every financial amount, and every operational metric in this folder are fictional. The files do not reproduce bunq data.

## Deliberate Test Conditions

- The SME sample has incomplete NACE and ESG data to create a credible ESG-risk capability gap.
- The ESG assessment snapshot separates data availability, screening outcome, transition-plan evidence, and follow-up needs from the core lending data.
- Payment records show Verification of Payee available on web but unavailable on mobile.
- Mortgage records include arrears and active alternative repayment arrangements.
- The trading-book file contains only liquidity-book holdings, making FRTB a limited-applicability test.

## Reference Gaps

The bunq reports do not provide public mortgage-arrears case records, loan-level ESG data, or payment-event data. Those three datasets are therefore scenario fixtures based on `Bank_Context_Fictional_Digital_Bank.md`, rather than factual reconstructions of bunq.

For a more realistic mortgage portfolio later, add public Permanent TSB annual-report/Pillar 3 references and Central Bank of Ireland mortgage-arrears guidance. No further reference is required for this first synthetic prototype.
