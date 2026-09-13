"""Read-only review probes: no LLM calls, no changes to bank data or approvals.

Run with: .venv/bin/python research/review_probes_2026-09-11.py
Output describes current behavior, not approved behavior or legal conclusions.
"""
import copy
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'agent'))
sys.path.insert(0, str(ROOT / 'scripts'))

import review_matrix_cli as review
import run_demo
from applicability import assess_product_applicability, assess_requirement_applicability
from dataset_runtime import load_runtime
from exposure_esg import (EXPOSURE_DIMENSIONS, CONFIDENCE_DIMENSIONS, ahp_weights,
                          matrix_from_pairs, compute_portfolio_exposure, score_freshness)
from gap_assessment import assess_capability_gap
from response_design import compare_response_options, package_chosen_option


def main():
    files = load_runtime()
    bank = files['01_entity/bank_profile.json']
    products = files['02_business/products.json']
    req = next(r for r in files['regulatory_sources/requirements.json']['requirements']
               if r['requirement_id'] == 'REQ-ESG-CREDIT-MONITORING-001')
    sme = next(p for p in products if p['product_id'] == 'PRD-SME-WORKING-CAPITAL')
    as_of = date(2026, 9, 8)
    out = {}
    for label, p in [('missing_markets', dict(sme, markets=[])),
                     ('us_only_markets', dict(sme, markets=['US']))]:
        r = assess_product_applicability(req, bank, p, as_of)
        out[label] = {k: r[k] for k in ['applicability', 'rationale']}
    r = assess_product_applicability(req, dict(bank, entity_classification=None), sme, as_of)
    out['null_entity_type'] = {k: r[k] for k in ['applicability', 'rationale']}
    r = assess_product_applicability(req, dict(bank, entity_classification='not_a_credit_institution'),
                                    sme, date(2025, 1, 1))
    out['future_date_bypasses_entity_check'] = {k: r[k] for k in ['applicability', 'rationale']}
    unknown = dict(sme, product_id='PRD-PROBE-NEW', product_type='new_credit_product')
    r = assess_requirement_applicability(req, bank, products + [unknown], as_of)
    out['unknown_product_omitted'] = {
        'new_product_evaluated': any(x['product_id'] == unknown['product_id'] for x in r['product_results']),
        'overall': r['applicability']}

    weights, cr = ahp_weights(matrix_from_pairs([], EXPOSURE_DIMENSIONS), EXPOSURE_DIMENSIONS)
    out['empty_ahp_pairs_accepted'] = {'weights': weights, 'cr': cr}
    with patch('builtins.input', return_value='n'), redirect_stdout(io.StringIO()):
        r = review.run_review_session({'requirement_id': 'REQ-PROBE', 'dimension_set': 'exposure',
                                       'pairs': [], 'status': 'draft'}, 'probe_reviewer')
    out['negative_review_input'] = {'input': 'n', 'resulting_status': r['status']}

    ghost_control = dict(control_id='CTRL-PROBE', coverage=[], operating_status='operating',
                         evidence_item_ids=['EVD-DOES-NOT-EXIST'])
    r = assess_capability_gap(dict(requirement_id='REQ-PROBE', control_ids=['CTRL-PROBE']),
                              {'CTRL-PROBE': ghost_control})
    out['unresolved_evidence_id_accepted_by_gap'] = r

    exp = review.load_confirmed_weights(req['requirement_id'], 'exposure', EXPOSURE_DIMENSIONS)
    conf = review.load_confirmed_weights(req['requirement_id'], 'confidence', CONFIDENCE_DIMENSIONS)
    if exp and conf:
        baseline = compute_portfolio_exposure(files, [sme['product_id']], exp[0], conf[0], as_of)
        out['proxy_with_full_confidence'] = next(x for x in baseline if x['record_id'] == 'PORT-SME-006')
        changed = copy.deepcopy(files)
        source_row = next(x for x in changed['03_exposure/lending_portfolio.csv']
                          if x['portfolio_record_id'] == 'PORT-SME-002')
        duplicate = copy.deepcopy(source_row)
        source_row['outstanding_balance_eur_millions'] = str(float(source_row['outstanding_balance_eur_millions']) / 2)
        source_row['borrower_count'] = str(int(source_row['borrower_count']) // 2)
        duplicate.update(source_row)
        duplicate['portfolio_record_id'] = 'PORT-PROBE-SPLIT'
        changed['03_exposure/lending_portfolio.csv'].append(duplicate)
        source_snapshot = next(x for x in changed['03_exposure/esg_assessment_snapshot.csv']
                               if x['portfolio_record_id'] == source_row['portfolio_record_id'])
        changed['03_exposure/esg_assessment_snapshot.csv'].append(
            dict(source_snapshot, portfolio_record_id=duplicate['portfolio_record_id']))
        split = compute_portfolio_exposure(changed, [sme['product_id']], exp[0], conf[0], as_of)
        original = next(x for x in baseline if x['record_id'] == source_row['portfolio_record_id'])
        out['same_cohort_split_into_two_rows'] = {
            'before': {k: original[k] for k in ['record_id', 'exposure_score', 'exposure_band']},
            'after': [{k: x[k] for k in ['record_id', 'exposure_score', 'exposure_band']}
                      for x in split if x['record_id'] in [source_row['portfolio_record_id'], duplicate['portfolio_record_id']]],
            'portfolio_balance_and_borrower_count_unchanged': True}
        with patch.object(review, 'complete', side_effect=AssertionError('No live LLM allowed')) as mock_llm, \
             patch('builtins.input', side_effect=['Review probe', '']), redirect_stdout(io.StringIO()):
            run_demo.main()
        out['cached_demo_llm_calls'] = mock_llm.call_count

    out['future_assessment_date_freshness'] = score_freshness('2030-01-01', as_of)
    comparison = compare_response_options(files)
    changed = copy.deepcopy(files)
    changed['04_governance/controls.json']['controls'] = []
    changed['regulatory_sources/requirements.json']['requirements'] = []
    out['response_ignores_removed_requirements_and_controls'] = comparison == compare_response_options(changed)
    cc = {r['cost_centre_id']: r['cost_centre_name'] for r in files['07_economics/operational_costs.csv']}
    ids = [r['requirement_id'] for r in files['regulatory_sources/requirements.json']['requirements']
           if r['requirement_id'].startswith('REQ-ESG')]
    chosen = package_chosen_option(comparison, files['07_economics/response_options.json'],
        'OPT-ESG-AUTOMATED', ids, files['06_organisation/roles.json'], cc,
        ['EVD-ESG-DATA-PROFILE', 'EVD-ESG-DATA-QUALITY-REPORT'], as_of)
    raw = next(x for x in files['07_economics/response_options.json'] if x['option_id']=='OPT-ESG-AUTOMATED')
    out['option_scope_vs_action_scope'] = {'option_requirement_ids': raw['requirement_ids'],
        'action_requirement_ids': chosen['addresses_requirement_ids'],
        'owner_role_id': chosen.get('owner_role_id'), 'target_date': chosen.get('target_date'),
        'action_cost_eur': chosen['estimated_total_cost_eur'],
        'setup_cost_eur': chosen['chosen_option']['setup_total_eur']}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=float))


if __name__ == '__main__':
    main()
