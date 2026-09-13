#!/usr/bin/env python3
"""Rebuild the calibrated v0.2 fixture from immutable Person 1–4 inputs.

This is a dataset migration, not a legal interpretation or an LLM training job.
Run from any directory. Default output is the canonical project dataset root.
Rebuilds are staged and backed up before replacement; unmanaged files are retained.
"""
from __future__ import annotations

import argparse
import copy
import shutil
import tempfile
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from project_paths import PROJECT_ROOT, RAW_DATA_ROOT, DATASET_ROOT
from m1_contracts import migrate_governance, CONTRACT_VERSION
from dataset_build import write_build_manifest, assert_no_unmerged_edits

ROOT = PROJECT_ROOT
DATA = RAW_DATA_ROOT
OUT = DATASET_ROOT
ASOF = '2026-09-08'
STAMP = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
VERSION = CONTRACT_VERSION
LEDGER = []


def read(path):
    p = DATA / path
    if p.suffix == '.csv':
        with p.open(newline='', encoding='utf-8') as f:
            return list(csv.DictReader(f))
    return json.loads(p.read_text())


def write(path, value):
    p = OUT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.suffix == '.csv':
        with p.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(value[0]))
            w.writeheader()
            w.writerows(value)
    else:
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def change(path, record, field, before, after, reason):
    if before != after:
        LEDGER.append(dict(path=path, record_id=record, field=field,
                           before=before, after=after, reason=reason))


def provenance(path, note='Preserved synthetic scenario fact; not a fact about bunq.'):
    return dict(origin='synthetic_bank_design', source_file=path,
                calibration_version=VERSION, notes=[note])


def stamp(r, path):
    r['synthetic'] = True
    r['provenance'] = provenance(path)
    return r


def missing(field, reason, scope='legal_reviewer', blocking=True):
    return dict(field=field, reason=reason, required_input=reason,
                responsible_scope=scope, blocking=blocking)


ALIASES = {
    'REG-EBA-ESG-2024': 'REG-ESG-EBA-GL-2025-01',
    'REG-DORA-2024': 'REG-DORA-2022-2554',
    'REG-FRTB-2024': 'REG-FRTB-CRR3-MKT-RISK',
    'REQ-ESG-RISK-GOVERNANCE': 'REQ-ESG-RISK-APPETITE-001',
    'REQ-ESG-RISK-INTEGRATION': 'REQ-ESG-RISK-INTEGRATION-001',
    'REQ-ESG-RISK-DATA': 'REQ-ESG-DATA-GAPS-001',
    'REQ-IPS-VOP-MOBILE': 'REQ-IPS-VOP-001',
    'REQ-DORA-ICT-DEPENDENCY-MAPPING': 'REQ-DORA-DEPENDENCY-MAP-001',
    'REQ-FRTB-TRADING-BOOK-APPLICABILITY': 'REQ-FRTB-SMALL-BOOK-001',
    'PROC-CREDIT-RISK-ASSESSMENT': 'PROC-CREDIT-RISK-MONITORING',
    'PROC-SME-UNDERWRITING': 'PROC-CREDIT-ORIGINATION',
    'PROC-ICT-THIRD-PARTY-RISK-MANAGEMENT': 'PROC-ICT-RESILIENCE',
    'PROC-MARKET-RISK-MONITORING': 'PROC-LIQUIDITY-MANAGEMENT',
    'SYS-CREDIT-RISK-ENGINE': 'SYS-RISK-ENGINE',
    'SYS-DATA-LAKE': 'SYS-DATA-PLATFORM',
    'SYS-MOBILE-BANKING': 'SYS-MOBILE-APP',
    'SYS-CMDB': 'SYS-ICT-REGISTER',
    'SYS-VENDOR-RISK-PORTAL': 'SYS-ICT-REGISTER',
    'DATA-SME-CREDIT-EXPOSURE': 'DATA-LOANS-EXPOSURES',
    'DATA-ESG-CUSTOMER-ATTRIBUTES': 'DATA-ESG-CLIMATE-RISK',
    'DATA-PAYMENT-TRANSACTIONS': 'DATA-PAYMENT-OPERATIONS',
    'DATA-CRITICAL-SERVICE-REGISTER': 'DATA-ICT-ASSETS-THIRD-PARTIES',
    'DATA-TRADING-BOOK': 'DATA-TREASURY-LIQUIDITY',
    'CTRL-ICT-THIRD-PARTY-RISK': 'CTRL-DORA-DEPENDENCY-MAP',
}


def remap(x):
    if isinstance(x, str):
        return ALIASES.get(x, x)
    if isinstance(x, list):
        v = [remap(y) for y in x]
        return list(dict.fromkeys(v)) if all(isinstance(y, str) for y in v) else v
    if isinstance(x, dict):
        return {k: remap(v) for k, v in x.items()}
    return x


def business():
    bank = read('person2/01_entity/bank_profile.json')
    stamp(bank, 'person2/01_entity/bank_profile.json')
    bank['as_of_date'] = ASOF
    bank['entity_classification'] = 'credit_institution'
    bank['euro_area_established'] = True
    bank['snci_status'] = False
    bank['snci_status_basis'] = 'Explicit synthetic scenario classification, not inferred from one balance sheet.'
    bank['esg_context']['scope_for_first_assessment'] = 'SME working-capital lending'
    bank['source_basis'] = {'scenario': '../data/Bank_Context_Fictional_Digital_Bank.md',
                            'reference_registry': 'reference_only/bunq_reference_registry.json'}
    write('01_entity/bank_profile.json', bank)
    bl = read('person2/02_business/business_lines.json')
    for r in bl:
        r.pop('esg_risk_assessment_priority', None)
        stamp(r, 'person2/02_business/business_lines.json')
        r['aggregation_note'] = 'Business lines overlap; do not sum customers or balances across them.'
    write('02_business/business_lines.json', bl)
    products = read('person2/02_business/products.json')
    for r in products:
        stamp(r, 'person2/02_business/products.json')
        if 'verification_of_payee' in r:
            r['verification_of_payee']['api'] = 'unknown'
        if r['product_id'] == 'PRD-SEPA-CREDIT-TRANSFER':
            r['verification_of_payee'] = {'web': 'unknown', 'mobile_app': 'unknown', 'api': 'unknown'}
    write('02_business/products.json', products)

    loans = read('person2/03_exposure/lending_portfolio.csv')
    legacy_labels = []
    sme_counts = [1800, 1600, 600, 600, 1400, 1800, 500, 300, 1400]
    si = 0
    for r in loans:
        legacy_labels.append({k:r[k] for k in ['portfolio_record_id', 'transition_risk_band', 'physical_risk_band']})
        for k in ['borrower_id', 'days_past_due', 'transition_risk_band', 'physical_risk_band']:
            r.pop(k)
        r['record_grain'] = 'portfolio_cohort'
        r['snapshot_date'] = '2026-06-30'
        r['synthetic'] = 'true'
        if r['borrower_type'] == 'sme':
            r['borrower_count'] = sme_counts[si]
            si += 1
        else:
            r['borrower_count'] = int(float(r['outstanding_balance_eur_millions']) * 100)
        r['remaining_maturity_years'] = float(r['remaining_maturity_years'])
        r['pd_12_month_pct'] = float(r['pd_12_month_pct'])
        r['lgd_pct'] = float(r['lgd_pct'])
    write('03_exposure/lending_portfolio.csv', loans)
    write('evaluation_ground_truth/legacy_risk_annotations.json', legacy_labels)
    snap = read('person2/03_exposure/esg_assessment_snapshot.csv')
    write('evaluation_ground_truth/legacy_esg_assessments.json', snap)
    fact_fields = ['portfolio_record_id', 'assessment_as_of_date', 'sector_data_quality',
                   'ghg_emissions_data_status', 'transition_plan_evidence', 'physical_risk_data_source']
    write('03_exposure/esg_assessment_snapshot.csv', [{**{k:r[k] for k in fact_fields}, 'synthetic':'true'} for r in snap])
    write('03_exposure/mortgage_book.csv', [{**r, 'record_grain':'illustrative_case_sample',
           'sampling_weight':'', 'synthetic':'true'} for r in read('person2/03_exposure/mortgage_book.csv')])
    payments = read('person2/03_exposure/payments.csv')
    for r in payments:
        r['sanctions_screening_status'] = 'method_and_cadence_not_evidenced'
        r['record_grain'] = 'selected_month_segment_channel_aggregate'
        r['population_complete'] = 'false'
        r['synthetic'] = 'true'
    write('03_exposure/payments.csv', payments)
    trading = read('person2/03_exposure/trading_book.csv')
    for r, amount in zip(trading, [1700, 800, 500]):
        change('03_exposure/trading_book.csv', r['position_id'], 'market_value_eur_millions',
               r['market_value_eur_millions'], amount,
               'Reconcile fictional bank assets: loans 9200 + liquidity 3000 + other assets 300 = 12500 million EUR.')
        r['market_value_eur_millions'] = amount
        r.pop('frtb_applicability_assessment')
        r['synthetic'] = 'true'
    write('03_exposure/trading_book.csv', trading)
    write('03_exposure/portfolio_summary.json', {
        'synthetic':True, 'as_of_date':'2026-06-30', 'currency':'EUR', 'unit':'EUR_million',
        'non_overlapping_balances':{'consumer_loans':4700,'home_improvement_loans':1100,
                                  'sme_working_capital':2300,'mortgages':1100,'liquidity':3000,'other_assets':300},
        'loan_book_total':9200, 'total_assets':12500,
        'sme_borrowers':10000, 'annual_sme_applications':32000,
        'annual_instant_payment_volume':8600000,
        'direct_channel_mobile_share_pct':71,
        'direct_channel_share_denominator':'mobile_app + web payment instructions; API share is not supplied',
        'mortgage_accounts_in_arrears':3800, 'mortgage_accounts_active_ara':650,
        'missing_or_broad_nace_borrower_pct':20,
        'provenance':provenance('Bank_Context_Fictional_Digital_Bank.md',
            'Amounts preserve the agreed bank scale. Borrower counts and asset reconciliation are explicit calibration assumptions.')})
    write('03_exposure/missing_facts.json', [
        dict(fact_id='FACT-ESG-ENERGY-COVERAGE', field='sme_energy_cost_data_coverage_pct', value=None,
             question='For the existing SME borrower population, what percentage has usable energy-cost data?',
             owner_role_id='ROLE-HEAD-LENDING', reason='Changes ESG data completeness and confidence.', synthetic=True),
        dict(fact_id='FACT-FRTB-CURRENT-EXPOSURE', field='current_complete_market_risk_position_inventory', value=None,
             question='Provide the latest month-end trading and off-balance-sheet inventory, including banking-book FX and commodity positions.',
             owner_role_id='ROLE-HEAD-TREASURY', reason='June snapshot cannot establish current Article 94 eligibility or all market-risk scope.', synthetic=True),
        dict(fact_id='FACT-IPS-OTHER-CHANNELS', field='standard_sct_and_api_vop_evidence', value=None,
             question='Provide VoP capability and execution evidence for standard SCT and API initiation.',
             owner_role_id='ROLE-HEAD-PAYMENTS', reason='Demo scope exclusion is not a legal exemption.', synthetic=True)])


def operations():
    keys = {'processes':'processes','systems':'systems','data_assets':'data_assets','vendors':'vendors',
            'critical_services':'critical_or_important_functions','dependencies':'dependency_mappings'}
    result = {}
    for filename, key in keys.items():
        d = read(f'person3/{filename}.json')
        d['_meta']['as_of_date'] = ASOF
        d['_meta']['calibration_version'] = VERSION
        d['_meta']['purpose'] = 'Fictional Northstar current-state records; peer reports inform design only.'
        for r in d[key]:
            stamp(r, f'person3/{filename}.json')
            if filename == 'dependencies':
                r['dependency_mapping_id'] = 'DEP-' + r['function_id'][4:]
            if filename == 'systems' and r['system_id'] == 'SYS-FRAUD-ENGINE':
                r['purpose'] = 'Transaction fraud detection; instant-payment timing and intervention behaviour require review.'
                r['notes'] = 'Synthetic in-house design. Peer delayed-release features do not establish a lawful SCT Inst workflow.'
            if filename == 'systems' and r['system_id'] in ['SYS-MOBILE-APP','SYS-WEB-BANKING']:
                r['share_denominator'] = 'mobile_app + web instructions only; not all API traffic'
            if filename == 'systems' and r['system_id'] == 'SYS-VOP':
                r['channel_integration']['api'] = 'unknown'
            if filename == 'systems' and r['system_id'] == 'SYS-TREASURY-LIQUIDITY':
                r['important_data'] = 'position, instrument type, issuer, market value, accounting book, trading-book flag'
                r['notes'] = 'June 2026 snapshot is stale for a current monthly threshold decision. Non-trading-book FX/commodity completeness is unknown.'
            if filename == 'processes' and r['process_id'] == 'PROC-OPEN-BANKING-PIS':
                r['notes'] = 'API is outside the selected demo remediation, but its legal coverage remains unresolved.'
            if filename == 'processes' and r['process_id'] == 'PROC-THIRD-PARTY-MGMT':
                r['business_line_ids'] = ['BL-RETAIL','BL-MORTGAGE','BL-SME','BL-LENDING','BL-PAYMENTS','BL-TREASURY']
            if filename == 'vendors':
                if r['vendor_id'] == 'VND-CLOUD-INFRA':
                    r['name'] = 'Fictional EEA cloud infrastructure provider'
                    r['notes'] = 'EEA cloud concentration is a synthetic design assumption. bunq cloud disclosures do not prove Northstar hosting or subcontractors.'
                if not r['subcontractors_identified_by_vendor'] and r['subcontractors_mapped_in_ict_register']:
                    change(f'05_operations/{filename}.json',r['vendor_id'],'subcontractors_mapped_in_ict_register',True,None,
                           'Cannot assert a mapped subcontractor population when that population is not identified; use unknown.')
                    r['subcontractors_mapped_in_ict_register'] = None
                for field in ['exit_plan_tested','legal_entity_identifier_present']:
                    if r.get(field):
                        r.setdefault('evidence_notes',[]).append(f'{field} is a supplied synthetic assertion; no artefact is attached.')
            if filename == 'data_assets' and r['data_asset_id'] == 'DATA-LOANS-EXPOSURES':
                r['notes'] = 'lending_portfolio.csv contains cohorts, not individual loan accounts.'
            if filename == 'data_assets' and r['data_asset_id'] == 'DATA-SME-SECTOR-CLASSIFICATION':
                r['known_limitation'] = '20% of borrowers have broad/missing NACE, weighted by borrower_count; exposure-weighted rate differs.'
                r['notes'] = 'Join cohort borrower_count to sector_data_quality; do not use row count as customer count.'
        result[filename] = d
    # Reconcile vendor reverse edges with declared systems, without completing missing subcontractor edges.
    systems = result['systems']['systems']
    for v in result['vendors']['vendors']:
        direct = [s['system_id'] for s in systems if s.get('vendor_id') == v['vendor_id']]
        if v['vendor_id'] == 'VND-CLOUD-INFRA':
            direct = [s['system_id'] for s in systems if s['hosting'] == 'cloud_hosted_eea']
        v['supports_systems'] = sorted(set(v['supports_systems']) | set(direct))
    for filename, d in result.items():
        write(f'05_operations/{filename}.json', d)


def organisation():
    costs = [('CC-100','Lending',42000000,416),('CC-200','Risk',18000000,544),
             ('CC-300','Data-IT',76000000,850),('CC-400','Finance',14000000,544),
             ('CC-500','Compliance',16000000,544),('CC-600','Payments',13000000,416),
             ('CC-700','Mortgage',9000000,416)]
    write('06_organisation/cost_centres.json', [dict(cost_centre_id=i,name=n,annual_run_cost_eur=v,
           synthetic=True,provenance=provenance('Bank_Context_Fictional_Digital_Bank.md')) for i,n,v,_ in costs])
    roles = read('person4/06_organisation/roles.json')
    role_cc = {'ROLE-CHIEF-RISK':'CC-200','ROLE-HEAD-CREDIT-RISK':'CC-200','ROLE-HEAD-PAYMENTS':'CC-600',
               'ROLE-HEAD-DIGITAL':'CC-300','ROLE-CISO':'CC-200','ROLE-CIO':'CC-300','ROLE-TPRM-LEAD':'CC-200',
               'ROLE-HEAD-COMPLIANCE':'CC-500','ROLE-COO':'CC-100','ROLE-HEAD-TREASURY':'CC-400',
               'ROLE-HEAD-INTERNAL-AUDIT':None,'ROLE-BCO':'CC-200'}
    known = {r['role_id'] for r in roles}
    for r in roles:
        change('06_organisation/roles.json',r['role_id'],'cost_centre_id',r['cost_centre_id'],role_cc[r['role_id']],
               'Project bank context has precedence over independently invented Person 4 cost-centre meanings.')
        r['cost_centre_id'] = role_cc[r['role_id']]
        r['missing_evidence'] = []
        if r['backup_role_id'] not in known or r['role_id'] == 'ROLE-HEAD-INTERNAL-AUDIT':
            r['backup_role_id'] = None
            r['missing_evidence'].append({'field':'backup_role_id','reason':'No valid independent backup supplied.'})
        if r['cost_centre_id'] is None:
            r['missing_evidence'].append({'field':'cost_centre_id','reason':'Internal Audit budget not supplied; outside demo costing.'})
        r['source_basis'] = 'Synthetic role allocation. No actual bunq role, owner or budget is asserted.'
        stamp(r, 'person4/06_organisation/roles.json')
    roles.append(stamp(dict(role_id='ROLE-HEAD-LENDING', title='Head of Lending', function='Lending',
                           line_of_defence=1, seniority='Senior management', cost_centre_id='CC-100',
                           email_alias='lending@northstar.example', backup_role_id='ROLE-COO',
                           missing_evidence=[]), 'Bank_Context_Fictional_Digital_Bank.md'))
    write('06_organisation/roles.json', sorted(roles,key=lambda r:r['role_id']))
    write('07_economics/operational_costs.csv', [dict(cost_centre_id=i,cost_centre_name=n,cost_type='delivery_day',
           unit='person_day',unit_cost_eur=rate,effective_from=ASOF,synthetic='true',
           calculation_basis=('technology change day rate from bank context' if i=='CC-300' else
                              '8 hours x scenario hourly rate; Finance/Payments/Mortgage use explicit peer-function assumptions'))
           for i,n,_,rate in costs])
    capacity = read('person4/07_economics/change_capacity.csv')
    for r in capacity:
        r['period'] = '2026-Q4'
        r['data_classification'] = 'synthetic_scenario'
        r['capacity_scope'] = 'named_role_allocation_not_full_delivery_team'
        r['source'] = 'Rebased scenario allocation; not actual availability and not evidence of delivery-team capacity.'
        r['remaining_days'] = int(r['available_days']) - int(r['committed_days'])
    write('07_economics/change_capacity.csv', capacity)
    write('reference_only/legacy_operational_costs.csv',read('person4/07_economics/operational_costs.csv'))


def regulatory():
    package = {}
    for section, filename, key in [('regulatory_sources','change_register','changes'),('regulatory_sources','requirements','requirements'),
                                  ('04_governance','policies','policies'),('04_governance','controls','controls'),('04_governance','procedures','procedures')]:
        d = read(f'person1/{section}/{filename}.json')
        d['as_of_date'] = ASOF
        d['generated_at'] = STAMP
        package[key] = d
    changes = package['changes']
    for s in changes['sources']:
        if s['source_id']=='SRC-FRTB-EURLEX-CRR-575':
            s['notes']=[n for n in s['notes'] if '5% of total assets or EUR 50 million' not in n]
            s['notes'].append('The earlier secondary-source threshold formulation is withdrawn. Current Article 94 conditions and position scope must be verified before any numeric derogation rule is enabled.')
        s.setdefault('extensions',{})['previous_verification_status'] = s['verification_status']
        s['verification_status'] = 'needs_review'
        s['notes'].append('2026-09-08 refresh: previous verification is not treated as proof of current legal state. See research/source_audit.md.')
        s['content_sha256'] = None
        if s['source_id'] == 'SRC-ESG-EBA-GL-2025-01':
            s['verification_status'] = 'verified'
            s['notes'].append('Official PDF visually inspected in browser: pages 17, 22, 23, 27, 29, 32. No local original-file snapshot available.')
            s['extensions']['verification_method'] = 'official_pdf_visual_read'
            s['extensions']['visual_audit_date'] = ASOF
    changes['sources'].append(dict(source_id='SRC-IPS-CBI-EXPLAINER',
        title='How can I send a payment from my bank instantly to another bank',publisher='Central Bank of Ireland',
        document_identifier='CBI instant payments consumer explainer',source_type='official_explanatory_page',
        authority_tier=3,official=True,url='https://www.centralbank.ie/consumer-hub/explainers/how-can-i-send-a-payment-from-my-bank',
        language='en',publication_date=None,retrieved_at=json.loads((ROOT/'config/dataset_migration_history.json').read_text())['source_retrieval_timestamps']['SRC-IPS-CBI-EXPLAINER'],content_sha256=None,verification_status='verified',
        notes=['Read in web research; corroborates 9 October 2025 and VoP for standard and instant SCT. Does not replace operative law.']))
    reqs = package['requirements']['requirements']
    byid = {r['requirement_id']:r for r in reqs}
    # Repair misleading composite quotations; text supplied in originals remains archived in Person 1.
    rewrites = {
        'REQ-ESG-CREDIT-POLICY-001':('Institutions should translate ESG-sensitive sectoral credit policies into clear origination criteria for business staff and credit decision-makers.', 'Section 5.6.1, paragraph 68; PDF page 32'),
        'REQ-ESG-DATA-GAPS-001':('Where ESG data is insufficient for risk management, institutions should assess the gaps and impacts, document remediation, and progressively reduce reliance on estimates or proxies as data improves.', 'Section 4.2.2, paragraph 27; PDF page 22'),
        'REQ-ESG-RISK-APPETITE-001':('Institutions should define their willingness to assume material ESG risks in risk appetite, including portfolio concentration and diversification objectives.', 'Section 5.3, paragraph 50; PDF page 29'),
        'REQ-ESG-RISK-INTEGRATION-001':('Institutions should embed ESG risks within regular risk-management systems and processes consistently with their business and risk strategies.', 'Section 5.1, paragraph 44; PDF page 27'),
        'REQ-DORA-DEPENDENCY-MAP-001':('Financial entities shall identify, classify and document ICT-supported business functions and supporting information and ICT assets, their roles and dependencies; critical-function and ICT-provider dependencies require the additional mapping specified in Article 8.', 'Articles 8(1), 8(4) and 8(5); pinpoint wording requires primary-text recheck'),
        'REQ-DORA-ICT-REGISTER-001':('Financial entities shall maintain and update a register of ICT third-party contractual arrangements at the relevant entity and group levels, distinguishing arrangements supporting critical or important functions.', 'Article 28(3); Article 64 for application date'),
        'REQ-DORA-TPRM-STRATEGY-001':('Financial entities other than microenterprises and entities covered by Article 16(1) shall adopt and regularly review an ICT third-party risk strategy, including a policy for ICT services supporting critical or important functions.', 'Article 28(2); Article 5(2)(h) for management-body responsibilities'),
        'REQ-FRTB-SMALL-BOOK-001':('An institution may use the small-trading-book derogation only if all conditions of CRR Article 94 are met, supported by the required position measurements and monitoring. This does not establish exemption from all market-risk requirements.', 'CRR Article 94; current consolidated wording not retrieved'),
    }
    for rid,(text,locator) in rewrites.items():
        r=byid[rid]
        change('regulatory_sources/requirements.json',rid,'requirement_text',r['requirement_text'],text,
               'Narrow obligation and distinguish source-grounded extraction from unresolved interpretation.')
        r['requirement_text']=text
        cit=r['source_citations'][0]
        cit.update(locator=locator,evidence_type='paraphrase',evidence_text=text,
                   verification_status='verified' if rid.startswith('REQ-ESG') else 'needs_review')
    extra = [
        ('REQ-ESG-CREDIT-MONITORING-001','REQ-ESG-CREDIT-POLICY-001','ESG integration in credit monitoring',
         'Institutions should embed ESG risks in credit monitoring, with environmental-risk metrics reflecting materiality, risk appetite and significant segments.', 'Section 5.6.1, paragraphs 68–69; PDF page 32'),
        ('REQ-ESG-DATA-SELECTION-001','REQ-ESG-DATA-GAPS-001','Proportionate data selection for non-large counterparties',
         'For non-large-corporate counterparties, institutions should determine necessary ESG data points, considering paragraph 28 and permitted gap-filling approaches.', 'Section 4.2.2, paragraph 29; PDF page 23'),
        ('REQ-ESG-LONG-HORIZON-001','REQ-ESG-RISK-INTEGRATION-001','Long-term ESG risk management',
         'Institutions should manage ESG risks over short, medium and at least ten-year long-term horizons.', 'Section 5.1, paragraph 45; PDF page 27'),
        ('REQ-ESG-RISK-KRI-001','REQ-ESG-RISK-APPETITE-001','ESG indicators supporting risk appetite',
         'Institutions should implement ESG risk appetite using relevant key risk indicators informed by materiality and their business model.', 'Section 5.3, paragraph 51; PDF page 29'),
    ]
    for rid,parent,title,text,loc in extra:
        r=copy.deepcopy(byid[parent]);r['requirement_id']=rid;r['title']=title;r['requirement_text']=text
        r['policy_ids']=[];r['control_ids']=[];r['procedure_ids']=[]
        r['applicability_conditions']=[]
        cid='CIT-'+rid+'-01'
        r['source_citations']=[dict(citation_id=cid,source_id='SRC-ESG-EBA-GL-2025-01',locator_type='paragraph',
                                   locator=loc,evidence_type='paraphrase',evidence_text=text,
                                   supports_fields=['requirement_text'],verification_status='verified')]
        for ev in r['compliance_events']:ev['source_citation_ids']=[cid]
        r['current_coverage']=dict(rating='unknown',assessment_basis='joined_dataset',
             rationale='No supplied operating evidence establishes coverage for this separately testable requirement.',
             control_ids=[],uncovered_dimensions=[],verification_status='needs_review')
        r.setdefault('extensions',{})['split_from_requirement_id']=parent
        reqs.append(r)
    for r in reqs:
        rid=r['requirement_id']; is_esg=rid.startswith('REQ-ESG')
        r['record_status']='needs_review'
        r['annotation']['label_status']='silver'
        r['annotation']['reviewed_by']=None;r['annotation']['reviewed_at']=None
        r['missing_evidence']=[missing('legal_review','Qualified reviewer has not approved this extraction and the selected institution-specific interpretation.')]
        if not is_esg:
            r['missing_evidence'].append(missing('source_citations','Current operative source text/version could not be fully rechecked through available retrieval; retained sources are not upgraded.'))
        r['provenance']['notes'].append('Refresh separates legal extraction, current synthetic capability, and human approval.')
        for c in r['source_citations']:
            if not is_esg:
                c['verification_status']='needs_review'
                c['evidence_type']='paraphrase'
                c['evidence_text']=r['requirement_text']
        if rid.startswith('REQ-DORA'):
            r['compliance_events']=[dict(event_type='application',date='2025-01-17',condition='In-scope credit institution; retained Article 64 date pending source recheck',
                                      source_citation_ids=[r['source_citations'][0]['citation_id']],verification_status='needs_review')]
            if rid=='REQ-DORA-ICT-REGISTER-001':
                r['interpretation_notes']=['Register maintenance and specific supervisory reporting are separate obligations. Any reporting reference date and submission deadline require a verified authority-specific source; no universal reporting date is inferred here.']
        if rid=='REQ-FRTB-APPLICATION-DATE-001':
            r['exclusions_and_exemptions']=['Article 94 derogation scope and remaining market-risk duties require separate review, including non-trading-book FX and commodity risks. Do not infer a blanket exemption from this timeline.']
            for ev in r['compliance_events']:
                ev['condition']='Retained 2025/1496 transition date; current operative status and institution-specific scope require primary-source review.'
        if rid=='REQ-FRTB-SMALL-BOOK-001':
            r['compliance_events'][0]['event_type']='review'
            r['applicability_conditions']=[]
            r['extensions']={'numeric_threshold_rule':None,
                'rule_disabled_reason':'Original OR formulation is unsafe. No automated derogation until current Article 94 text and all conditions are verified.'}
            r['required_bank_facts']=[dict(fact_ref='03_exposure/trading_book.csv',purpose='Inspect dated banking-book positions, not a complete current market-risk inventory.',evidence_status='needs_review')]
        # Entity scope must not be inferred from the existence of a vendor or a file.
        r['applicability_conditions']=[dict(condition_id='COND-'+rid+'-ENTITY',description='Confirm the legal entity classification against the cited scope.',
            condition_type='bank_fact',fact_path='01_entity/bank_profile.json#/entity_classification',operator='equals',
            expected_value=['credit_institution'],source_citation_ids=[r['source_citations'][0]['citation_id']],evidence_status='verified')]
        r.setdefault('extensions',{})['applicability_logic_status']='candidate_requires_legal_review'
        if is_esg:
            r['applicability_conditions'].append(dict(condition_id='COND-'+rid+'-SNCI',description='Determine which ESG application date is relevant.',
                condition_type='bank_fact',fact_path='01_entity/bank_profile.json#/snci_status',operator='equals',expected_value=[False],
                source_citation_ids=[r['source_citations'][0]['citation_id']],evidence_status='verified'))
            r['extensions']['date_locator']='EBA/GL/2025/01 paragraph 10, PDF page 17; separate from substantive citation'
            scope_cid='CIT-'+rid+'-SCOPE'
            date_cid='CIT-'+rid+'-DATE'
            for cid,loc,text,fields in [
                (scope_cid,'Paragraph 8; PDF page 17','Addressees include the institutions specified through the CRR definition.', ['applicability_conditions']),
                (date_cid,'Paragraph 10; PDF page 17','Application is 11 January 2026 for other institutions and at latest 11 January 2027 for SNCIs.', ['compliance_events'])]:
                r['source_citations'].append(dict(citation_id=cid,source_id='SRC-ESG-EBA-GL-2025-01',locator_type='paragraph',
                    locator=loc,evidence_type='paraphrase',evidence_text=text,supports_fields=fields,verification_status='verified'))
            r['applicability_conditions'][0]['source_citation_ids']=[scope_cid]
            r['applicability_conditions'][1]['source_citation_ids']=[date_cid]
            for ev in r['compliance_events']:ev['source_citation_ids']=[date_cid]
        paths = ['01_entity/bank_profile.json#/entity_classification']
        if is_esg:paths+=['01_entity/bank_profile.json#/snci_status','03_exposure/lending_portfolio.csv','03_exposure/esg_assessment_snapshot.csv']
        elif rid.startswith('REQ-DORA'):paths+=['05_operations/critical_services.json','05_operations/dependencies.json','05_operations/vendors.json']
        elif rid.startswith('REQ-IPS'):paths+=['02_business/products.json','03_exposure/payments.csv','05_operations/systems.json']
        else:paths+=['03_exposure/trading_book.csv','01_entity/bank_profile.json#/scale/total_assets_eur_millions']
        r['required_bank_facts']=[dict(fact_ref=p,purpose='Scenario input; file presence does not establish legal compliance or evidence completeness.',
                                    evidence_status='verified') for p in paths]
        r['extensions']['unresolved_bank_fact_register']='03_exposure/missing_facts.json'
        if rid=='REQ-ESG-RISK-APPETITE-001':
            r['missing_evidence'].append(missing('current_coverage','Risk-appetite statement and approved ESG limits/KRIs are not supplied.','person_1'))
        r['current_coverage']['assessment_basis']='joined_dataset'
        r['current_coverage']['verification_status']='needs_review'
        r['current_coverage']['rationale']='Mapping describes supplied synthetic design only; operating effectiveness remains unproven.'
        if rid=='REQ-IPS-VOP-001':
            r['requirement_text']='The payer’s PSP shall offer payee verification before credit-transfer authorisation, subject to the operative conditions and exceptions of Article 5c. It concerns both standard and instant euro credit transfers.'
            r['source_citations'][0]['evidence_text']=r['requirement_text']
            r['interpretation_notes']=['Mobile is a synthetic implementation gap. Standard SCT and API coverage are unknown; outside demo does not mean legally exempt.','Free-of-charge duty is separately located at Article 5b(2); include it in an expanded scope.']
            r['source_citations'].append(dict(citation_id='CIT-REQ-IPS-VOP-001-CBI',source_id='SRC-IPS-CBI-EXPLAINER',
                locator_type='section',locator='Verification of Payee',evidence_type='paraphrase',
                evidence_text='The CBI explains that VoP applies from 9 October 2025 to both standard and instant SEPA credit transfers.',
                supports_fields=['requirement_text','compliance_events'],verification_status='verified'))
            r['provenance']['source_ids'].append('SRC-IPS-CBI-EXPLAINER')
        if rid.startswith('REQ-FRTB'):
            r['missing_evidence'].append(missing('required_bank_facts','Current complete on/off-balance-sheet trading inventory and non-trading-book FX/commodity exposure are absent.','person_2'))
    for r in changes['changes']:
        r['record_status']='needs_review'
        r['missing_evidence']=[missing('current_status','Human review and a complete amendment/consolidation audit are pending; see source_audit.md.')]
        r['requirement_ids']=sorted(x['requirement_id'] for x in reqs if x['change_id']==r['change_id'])
        if r['topic_key']=='frtb':
            r['application_events'][-1]['applies_to']='C(2026)3647 adopted 4 June 2026; OJ publication and in-force status at 2026-09-08 remain unresolved. Do not treat proposed relief as operative.'
    package['requirements']['requirements']=sorted(reqs,key=lambda r:r['requirement_id'])
    return package


def governance(package):
    # Replace obsolete hand-off notes after integration, without asserting completeness.
    joined_notes = {
        "Materiality and composition of the underlying SME portfolio are owned by Person 2/3 and are not asserted here.":
            "The joined cohort and ESG data describe the SME portfolio; materiality conclusions still require assessment.",
        "Completeness depends on Person 3's critical-service, system, vendor and dependency records, which are not yet available.":
            "The joined operations records identify five critical functions and known mapping gaps; a complete underlying inventory and operating evidence are still required.",
        "but Person 1 cannot itself confirm this without Person 2/3 trading-book and total-assets data.":
            "while the joined June position sample cannot establish current Article 94 eligibility or complete FX/commodity exposure.",
        "remain not_assessed pending Person 2/3 facts.":
            "remain not_assessed pending the relevant charges and screening evidence; supplied payment volumes alone are insufficient.",
        "full critical-service inventory is not yet confirmed by Person 3.":
            "five critical functions are listed in the joined scenario, but inventory completeness and mapping effectiveness are unproven.",
        "full population is not confirmed by Person 3.":
            "the joined vendor inventory does not establish that all contractual arrangements and subcontractors are captured.",
        "its output depends on Person 2/3 trading-book and total-assets data (03_exposure/trading_book.csv) that is not yet available, so actual coverage/effectiveness cannot be verified.":
            "the joined June banking-book position sample and asset total do not provide a complete current market-risk scope assessment, so actual coverage/effectiveness cannot be verified.",
        "pending Person 3 data, not assumed absent.":
            "pending confirmation against the complete underlying function inventory, not assumed absent.",
        "pending Person 3 vendor data.":
            "pending reconciliation against the complete contractual and vendor population.",
        "until Person 3's full vendor population is available.":
            "until the full contractual population, including relevant subcontractors, is reconciled and reviewed.",
    }
    def refresh_notes(value):
        if isinstance(value, str):
            for old, new in joined_notes.items():
                value = value.replace(old, new)
            return value
        if isinstance(value, list):
            return [refresh_notes(v) for v in value]
        if isinstance(value, dict):
            return {k: refresh_notes(v) for k, v in value.items()}
        return value
    for key in ['policies', 'controls', 'procedures']:
        package[key] = refresh_notes(package[key])
    scopes = {
        'ESG':dict(owner='ROLE-HEAD-CREDIT-RISK',business_line_ids=['BL-LENDING','BL-SME'],product_ids=['PRD-SME-WORKING-CAPITAL'],
                   process_ids=['PROC-CREDIT-ORIGINATION','PROC-CREDIT-RISK-MONITORING','PROC-DATA-GOVERNANCE'],
                   system_ids=['SYS-LOAN-ORIG','SYS-RISK-ENGINE','SYS-DATA-PLATFORM','SYS-GRC'],
                   data_asset_ids=['DATA-LOANS-EXPOSURES','DATA-SME-SECTOR-CLASSIFICATION','DATA-ESG-CLIMATE-RISK'],vendor_ids=[],critical_service_ids=['CIF-LOAN-ORIGINATION']),
        'DORA':dict(owner='ROLE-CIO',business_line_ids=['BL-RETAIL','BL-SME','BL-MORTGAGE','BL-LENDING','BL-PAYMENTS','BL-TREASURY'],product_ids=[],
                    process_ids=['PROC-ICT-RESILIENCE','PROC-THIRD-PARTY-MGMT'],system_ids=['SYS-ICT-REGISTER','SYS-GRC'],
                    data_asset_ids=['DATA-ICT-ASSETS-THIRD-PARTIES'],vendor_ids=['VND-CLOUD-INFRA','VND-CORE-BANKING','VND-MORTGAGE-SERVICER','VND-IDENTITY-VERIFICATION'],
                    critical_service_ids=['CIF-LOGIN-ACCESS','CIF-ONBOARDING','CIF-LOAN-ORIGINATION','CIF-MORTGAGE-SERVICING','CIF-PAYMENTS']),
        'IPS':dict(owner='ROLE-HEAD-PAYMENTS',business_line_ids=['BL-PAYMENTS'],product_ids=['PRD-SEPA-INSTANT'],
                   process_ids=['PROC-PAYMENT-INITIATION'],system_ids=['SYS-WEB-BANKING','SYS-VOP','SYS-PAYMENTS-HUB'],
                   data_asset_ids=['DATA-PAYMENT-OPERATIONS'],vendor_ids=['VND-VOP-PROVIDER'],critical_service_ids=['CIF-PAYMENTS']),
        'FRTB':dict(owner='ROLE-HEAD-TREASURY',business_line_ids=['BL-TREASURY'],product_ids=['PRD-LIQUIDITY-PORTFOLIO'],
                    process_ids=['PROC-LIQUIDITY-MANAGEMENT'],system_ids=['SYS-TREASURY-LIQUIDITY'],
                    data_asset_ids=['DATA-TREASURY-LIQUIDITY'],vendor_ids=[],critical_service_ids=[]),
    }
    for key in ['policies','controls','procedures']:
        for r in package[key][key]:
            topic = r['requirement_ids'][0].split('-')[1]
            sc=scopes[topic]
            r['owner_role_id']=sc['owner']
            target=r if key=='controls' else r['scope']
            for f,v in sc.items():
                if f!='owner':target[f]=sorted(v)
            r['missing_evidence']=[missing('human_approval','Synthetic allocation has not been approved by a human reviewer.','user',False)]
            r['record_status']='needs_review'
            r['provenance']['notes'].append('Joined with canonical Persons 2–4 IDs; owners are synthetic scenario assignments.')
            if key=='controls':
                r['operating_status']='unknown';r['evidence_item_ids']=[]
                r['missing_evidence'].append(missing('evidence_item_ids','No collected control-operation artefact exists; expected evidence is not proof.','person_4'))
                if topic=='ESG':r['owner_role_id']='ROLE-HEAD-LENDING'
            if key=='procedures':
                if topic=='ESG':r['owner_role_id']='ROLE-HEAD-LENDING'
                r['evidence_item_ids']=[]
                for step in r['steps']:
                    step['performer_role_id']=r['owner_role_id']
                    step['system_ids']=sorted(sc['system_ids']);step['data_asset_ids']=sorted(sc['data_asset_ids'])
                    if topic=='ESG' and step['step_number']==3:
                        step['performer_role_id']='ROLE-HEAD-CREDIT-RISK'
                    if topic=='FRTB' and step['step_number']==2:
                        step['action']='After the current legal rule, measurement scope and complete monthly inventory are reviewed, compare the documented positions with all applicable Article 94 conditions.'
                        step['output_description']='Conditional comparison, or insufficient_evidence when the legal rule or current population is unverified.'
                        step['exception_handling']='The current fixture lacks a verified rule and complete current scope: record insufficient_evidence and do not execute an automatic derogation decision.'
                    if topic=='FRTB' and step['step_number']==3:
                        step['exception_handling']='Escalate missing scope evidence or a confirmed breach to the designated Treasury and Risk roles; their synthetic allocation still requires human approval.'
    before_m1 = copy.deepcopy(package)
    migrate_governance(package)
    for key, id_field in [('requirements', 'requirement_id'), ('controls', 'control_id'), ('changes', 'change_id')]:
        previous = {r[id_field]: r for r in before_m1[key][key]}
        for row in package[key][key]:
            for field, value in row.items():
                change(key, row[id_field], field, previous[row[id_field]].get(field), value,
                       'M1 integrity migration: scoped semantic mappings and shared SNCI dates; provisional, not legal approval.')
    for key,section,filename in [('changes','regulatory_sources','change_register'),('requirements','regulatory_sources','requirements'),
                                  ('policies','04_governance','policies'),('controls','04_governance','controls'),('procedures','04_governance','procedures')]:
        write(f'{section}/{filename}.json',package[key])


def actions():
    actions = remap(read('person4/08_evidence/actions.json'))
    role_cc={r['role_id']:r['cost_centre_id'] for r in json.loads((OUT/'06_organisation/roles.json').read_text())}
    rates={r['cost_centre_id']:float(r['unit_cost_eur']) for r in csv.DictReader((OUT/'07_economics/operational_costs.csv').open())}
    deadlines={'ESG':'2026-01-11','IPS':'2025-10-09','DORA':'2025-01-17','FRTB':None}
    target={'ACT-ESG-PORTFOLIO-CONTROL':'2026-12-31','ACT-ESG-DATA-REMEDIATION':'2027-03-31',
            'ACT-IPS-MOBILE-VOP':'2026-10-31','ACT-DORA-DEPENDENCY-MAP':'2026-12-31','ACT-FRTB-APPLICABILITY-MONITOR':'2026-09-30'}
    for a in actions:
        topic=a['action_id'].split('-')[1]
        if topic=='ESG' and a['action_id']=='ACT-ESG-PORTFOLIO-CONTROL':
            a['owner_role_id']='ROLE-HEAD-LENDING'
            a['affected_control_ids']=['CTRL-ESG-ONBOARD-SCREEN']
            a['requirement_ids']+=['REQ-ESG-CREDIT-MONITORING-001','REQ-ESG-RISK-KRI-001','REQ-ESG-LONG-HORIZON-001']
        if topic=='DORA':
            a['owner_role_id']='ROLE-CIO';a['accountable_role_id']='ROLE-COO'
        if topic=='FRTB':
            a['title']='Refresh market-risk scope evidence and document conditional applicability'
            a['assumptions']=['Current full position inventory, FX/commodity exposure and legal review remain outstanding.']
            a['affected_control_ids']=['CTRL-FRTB-THRESHOLD-MONITOR']
            a['closure_criteria']='Current monthly facts and qualified interpretation are documented; do not assert exemption based solely on absence of trading desk.'
        a['cost_centre_id']=role_cc[a['owner_role_id']]
        a['estimated_internal_cost_eur']=int(a['estimated_internal_days']*rates[a['cost_centre_id']])
        a['estimated_total_cost_eur']=a['estimated_internal_cost_eur']+a['estimated_external_cost_eur']
        a['target_date']=target[a['action_id']]
        a['regulatory_due_date']=deadlines[topic]
        a['deadline_status']='past_application_date' if deadlines[topic] else 'scope_review_pending'
        a['target_date_basis']='Unapproved internal remediation target; does not extend the regulatory due date.'
        a['source_basis']='Synthetic reference plan; amounts are scenario estimates, not bunq costs or vendor quotes.'
        a['human_review_status']='pending';a['reviewed_by']=None;a['reviewed_at']=None
        a['planning_status']='needs_capacity_confirmation'
        stamp(a,'person4/08_evidence/actions.json')
    evidence=read('person4/08_evidence/evidence_register.json')
    amap={a['action_id']:a for a in actions}
    for e in evidence:
        e['expected_by']=amap[e['action_id']]['target_date']
        e['owner_role_id']=amap[e['action_id']]['owner_role_id']
        e.update(status='required',artifact_path=None,content_sha256=None,collected_at=None,
                 reviewed_at=None,reviewed_by=None,human_review_status='pending',synthetic=True,
                 retention_basis='Synthetic project retention assumption; not a verified statutory period.')
    write('evaluation_ground_truth/reference_actions.json',actions)
    write('evaluation_ground_truth/reference_evidence.json',evidence)
    write('08_evidence/actions.json',[])
    write('08_evidence/evidence_register.json',[])
    raci=[]
    for a in actions:
        for role,letter in [(a['owner_role_id'],'R'),(a['accountable_role_id'],'A'),('ROLE-HEAD-COMPLIANCE','C')]:
            raci.append(dict(action_id=a['action_id'],activity=a['title'],role_id=role,raci=letter,
                             notes='Synthetic proposed allocation; pending qualified review.'))
    write('evaluation_ground_truth/reference_raci.csv',raci)
    # Operational RACI describes standing responsibilities, never the answer plan.
    write('06_organisation/raci.csv',[
        dict(process_id='PROC-CREDIT-ORIGINATION',role_id='ROLE-HEAD-LENDING',raci='A',notes='First-line implementation'),
        dict(process_id='PROC-CREDIT-RISK-MONITORING',role_id='ROLE-CHIEF-RISK',raci='A',notes='Risk framework and independent challenge'),
        dict(process_id='PROC-DATA-GOVERNANCE',role_id='ROLE-CIO',raci='A',notes='Data and technology delivery'),
        dict(process_id='PROC-PAYMENT-INITIATION',role_id='ROLE-HEAD-PAYMENTS',raci='A',notes='Payment-service outcome'),
        dict(process_id='PROC-ICT-RESILIENCE',role_id='ROLE-COO',raci='A',notes='Operational implementation; Risk and Compliance challenge'),
        dict(process_id='PROC-LIQUIDITY-MANAGEMENT',role_id='ROLE-HEAD-TREASURY',raci='A',notes='Monthly position facts')])


def response_options():
    options=[]
    for oid, title, automation, months, effort, tech, vendor, training, legal, annual_fixed in [
        ('OPT-ESG-MANUAL','Manual review',0.0,2,{'CC-100':20,'CC-200':12,'CC-300':5,'CC-400':2,'CC-500':3},0,0,2000,3000,0),
        ('OPT-ESG-AUTOMATED','Automated data and workflow',0.85,6,{'CC-100':10,'CC-200':20,'CC-300':90,'CC-400':4,'CC-500':5},30000,20000,3000,5000,60000),
        ('OPT-ESG-HYBRID','Hybrid review',0.60,4,{'CC-100':15,'CC-200':16,'CC-300':35,'CC-400':3,'CC-500':4},12000,12000,2500,4000,30000)]:
        options.append(dict(option_id=oid,title=title,synthetic=True,
             requirement_ids=['REQ-ESG-DATA-GAPS-001','REQ-ESG-CREDIT-MONITORING-001'],
             effort_days_by_cost_centre=effort,technology_setup_eur=tech,data_vendor_setup_eur=vendor,
             training_setup_eur=training,legal_setup_eur=legal,annual_fixed_run_eur=annual_fixed,
             automation_rate=automation,delivery_months=months,review_minutes_low=20,review_minutes_base=30,review_minutes_high=45,
             scope='Existing SME borrower population, one review annually; excludes new applications',
             implementation_assumptions=['All prices and effort are synthetic, unapproved estimates.',
                 'Automation rate describes reduced manual handling, not legal compliance or control effectiveness.'],
             risk_probability=None,expected_loss_eur=None,revenue_activity_change_pct=None,
             compliance_review_status='pending',delivery_team_capacity_days=None))
    write('07_economics/response_options.json',options)


def evaluation():
    cases=[
        ('CASE-ESG-BASE','esg','assess','Assess the SME ESG-risk change and identify what evidence is missing.',
         {'applicability':'direct_under_synthetic_entity_classification','exposure':'report_portfolio_facts','risk_assessment_status':'unverified',
          'required_question_fact_ids':['FACT-ESG-ENERGY-COVERAGE'],'must_not':['claim_human_approval','treat_proxy_as_measured_emissions']}),
        ('CASE-IPS-BASE','instant_payments','assess','Assess VoP coverage across the bank’s credit-transfer services.',
         {'known_gap':'mobile_instant_payment_vop','unresolved_scope':['standard_sct','api'],'deadline_status':'past_due',
          'must_not':['declare_api_legally_exempt','treat_standard_sct_as_out_of_scope']}),
        ('CASE-DORA-BASE','dora','assess','Assess the evidence for ICT and third-party dependency mapping.',
         {'confirmed_synthetic_gap_vendors':['VND-CLOUD-INFRA','VND-MORTGAGE-SERVICER'],
          'unknown_subcontractor_population_must_remain_unknown':True,'must_not':['assert_all_dora_compliance']}),
        ('CASE-FRTB-BASE','frtb','assess','Does the June banking-book snapshot prove that all FRTB requirements are inapplicable now?',
         {'business_relevance':'limited','applicability':'uncertain','allowed_action':'refresh_scope_evidence_and_monitor',
          'must_not':['blanket_market_risk_exemption','invent_frtb_remediation_programme','evaluate_unverified_numeric_rule']}),
        ('CASE-NACE-WEIGHT','esg','arithmetic','Measure missing/broad NACE coverage using customers and exposure separately.',
         {'borrower_weighted_pct':20.0,'exposure_weighted_pct':39.56521739130435,'tolerance':1e-8}),
        ('CASE-PAYMENT-SAMPLE','instant_payments','arithmetic','Can the selected payment rows establish the annual mobile percentage?',
         {'observed_sample_pct':75.1052483861914,'full_direct_channel_scenario_pct':71,'can_extrapolate_sample':False}),
        ('CASE-EVIDENCE-REQUIRED','evidence','closure','Can an action close when all evidence items have status required?',
         {'can_close':False}),
        ('CASE-EVIDENCE-HASH','evidence','closure','Can an approved-looking record close an action when its artefact hash fails?',
         {'can_close':False}),
        ('CASE-CAPACITY-UNKNOWN','economics','cost','Choose the cheapest response and assess feasibility with unknown team capacity.',
         {'lowest_base_tco_option_id':'OPT-ESG-AUTOMATED','recommended_option_id':None,'capacity_sufficient':None}),
        ('CASE-RISK-COST-UNKNOWN','economics','cost','Calculate non-compliance expected loss when probability and severity are absent.',
         {'expected_risk_cost_eur':None,'must_not':['treat_unknown_as_zero']}),
        ('CASE-PEER-SEPARATION','provenance','assess','Can bunq personnel expenses or cloud disclosures prove Northstar costs and suppliers?',
         {'peer_is_enterprise_evidence':False}),
        ('CASE-VERSION-PAIR','regulation','change_detection','Run a reproducible ESG draft-to-final text difference.',
         {'expected_status':'insufficient_source_snapshots','must_not':['invent_old_text','claim_consultation_was_binding']}),
    ]
    write('evaluation_ground_truth/expected_assessments.json',[
        dict(case_id=i,topic=t,task=task,question=q,expected=expected,label_status='silver',
             split='development',reviewed_by=None,reviewed_at=None) for i,t,task,q,expected in cases])
    write('evaluation_ground_truth/interview_fixture.json',dict(
        fixture_id='INTERVIEW-ESG-ENERGY',synthetic=True,fact_id='FACT-ESG-ENERGY-COVERAGE',
        initial_value=None,simulated_user_answer={'value':65,'unit':'percent_of_existing_sme_borrowers',
        'as_of_date':'2026-06-30','evidence_kind':'synthetic_owner_response'},
        expected_effect='Update this one completeness input; retain legal-review and evidence limitations.',
        must_not='Treat an interview answer as verified source law or operating-control evidence.'))


def manifests():
    raw=[]
    for pattern in ['person*/**/*.json','person*/**/*.csv','*.md','regulatory-governance-dataset/**/*.md']:
        for p in sorted(DATA.glob(pattern)):
            raw.append(dict(path=str(p.relative_to(DATA)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    write('calibration/input_inventory.json',raw)
    write('calibration/id_crosswalk.json',[
        dict(legacy_id=k,canonical_id=v,scope='Person 4 references only',
             mapping_kind='explicit_integration_mapping_not_proof_of_semantic_identity') for k,v in sorted(ALIASES.items())])
    write('calibration/change_log.json',LEDGER)
    ref=[]
    for p in sorted((DATA/'bunq_reference bank').glob('*.pdf')):
        ref.append(dict(reference_id='REF-'+p.stem.upper(),entity='bunq',path='../../data/bunq_reference bank/'+p.name,
             sha256=hashlib.sha256(p.read_bytes()).hexdigest(),synthetic=False,
             allowed_use='Public peer-design reference only; not Northstar activity, budget, vendor, control or compliance evidence.',
             authenticity_status='User-provided report; relevant pages inspected locally; publisher download identity not independently checked.'))
    write('reference_only/bunq_reference_registry.json',ref)
    write('regulatory_sources/version_pairs.json',[
        dict(version_pair_id='VER-ESG-CONSULTATION-FINAL',topic='esg_risk',
             older={'identifier':'EBA/CP/2024/02','status':'consultation','published_on':'2024-01-18',
                    'url':'https://www.eba.europa.eu/sites/default/files/2024-01/c94fd865-6990-4ba8-b74e-6d8ef73d8ea5/Consultation%20papaer%20on%20draft%20Guidelines%20on%20ESG%20risks%20management.pdf',
                    'local_artifact':None,'sha256':None},
             newer={'identifier':'EBA/GL/2025/01','status':'final_guideline','published_on':'2025-01-09',
                    'url':'https://www.eba.europa.eu/sites/default/files/2025-01/fb22982a-d69d-42cc-9d62-1023497ad58a/Final%20Guidelines%20on%20the%20management%20of%20ESG%20risks.pdf',
                    'local_artifact':None,'sha256':None},
             comparison_kind='consultation_to_final_not_change_between_two_binding_acts',
             diff_status='not_computed',missing_evidence=['Two locally preserved official full-text versions with integrity hashes are required for reproducible text-diff evaluation.'])])
    files=[]
    for prefix in ['01_entity','02_business','03_exposure','04_governance','05_operations','06_organisation','07_economics','08_evidence','regulatory_sources']:
        files += [str(p.relative_to(OUT)) for p in sorted((OUT/prefix).glob('*')) if p.suffix in ['.json','.csv'] and p.name != 'pairwise_matrix_registry.json']
    write('dataset_manifest.json',dict(dataset_id='NORTHSTAR-REGCHANGE',dataset_version=VERSION,
         scenario_as_of_date=ASOF,research_cutoff=ASOF,bank_entity_id='ENT-NDB-PLC',
         maturity='silver_synthetic_prototype',primary_scenario='SME ESG risk management',
         primary_requirement_id='REQ-ESG-CREDIT-MONITORING-001',
         auxiliary_scenarios=['instant_payments','dora','frtb'],
         operational_files=files,excluded_from_agent_inputs=['evaluation_ground_truth/','reference_only/','calibration/'],
         annotation_policy='Gold requires named qualified human review. No record in this release is human-approved.',
         source_readiness='ESG selected paragraphs visually verified; other operative sources and full version diff remain needs_review.',
         runtime_projection='Use scripts/dataset_runtime.py; do not recursively index the workspace or narrative design documents.',
         synthetic_generation_authority='User requested recalibration of all four teams’ fictional-bank data.',
         time_policy='Historical bank snapshots retain their actual dates. Future internal remediation dates never replace regulatory due dates.'))


def main():
    global OUT, STAMP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DATASET_ROOT)
    parser.add_argument('--build-timestamp', help='Explicit ISO timestamp for byte-reproducible builds')
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination == DATA or DATA in destination.parents:
        raise ValueError('Output inside raw data is forbidden; use the canonical root or a scratch directory.')
    if destination == ROOT or destination in ROOT.parents:
        raise ValueError('Output must be a dedicated dataset directory.')
    if args.build_timestamp:
        datetime.fromisoformat(args.build_timestamp.replace('Z', '+00:00'))
        STAMP = args.build_timestamp
    LEDGER.clear()
    with tempfile.TemporaryDirectory(prefix='reguagent-build-') as tmp:
        OUT = Path(tmp)
        business();operations();organisation();governance(regulatory());actions();response_options();evaluation();manifests()
        from validate_dataset import validate
        report = validate(OUT)
        if report['errors']:
            raise ValueError(f"Staged build failed validation: {report['errors']}")
        write_build_manifest(OUT)
        assert_no_unmerged_edits(destination, OUT)
        if destination.exists():
            backup = ROOT / 'backups' / ('dataset-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            shutil.copytree(destination, backup)
            print(f'Preserved existing dataset at {backup}')
        destination.mkdir(parents=True, exist_ok=True)
        # Only generated paths are replaced. Human method records and documents
        # are unmanaged; neither their data nor their approval state is discarded.
        for path in sorted(OUT.rglob('*')):
            if path.is_file():
                target = destination / path.relative_to(OUT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        OUT = destination
    print(f'Built {OUT}; {len(LEDGER)} logged changes; original Person 1–4 inputs unchanged.')


if __name__=='__main__':
    main()
