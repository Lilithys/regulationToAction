"""Legacy deterministic batch preview for the four scenario topics.

This module prepares existing view shapes; it is not the planned coordinator or
LLM tool loop. SME exposure facts and optional method review live in run_demo.py.
A completed calculation never implies qualified legal approval.
"""
from __future__ import annotations

from datetime import date

from applicability import (assess_requirement_applicability, assess_bank_level_applicability,
                            classify_payment_product, PAYMENT_INITIATION_PRODUCT_TYPES)
from gap_assessment import assess_capability_gap, frtb_restraint_check

# topic_key (regulatory_sources/change_register.json) -> which phases this topic runs.
# esg_risk_management is the only one that continues past 'gap' -- see run_demo.py.
DEPTH = {
    'esg_risk_management': ('applicability', 'gap', 'exposure', 'response', 'closure'),
    'instant_payments': ('applicability', 'gap'),
    'dora': ('applicability', 'gap'),
    'frtb': ('applicability', 'restraint'),
}
STAGE_NAMES = ['适用性', '暴露度', '能力缺口', '建议行动', '响应结果']


def find_change(files: dict, topic_key: str) -> dict:
    return next(c for c in files['regulatory_sources/change_register.json']['changes'] if c['topic_key'] == topic_key)


def find_requirement(files: dict, requirement_id: str) -> dict:
    return next(r for r in files['regulatory_sources/requirements.json']['requirements']
                if r['requirement_id'] == requirement_id)


def run_applicability_for_topic(topic_key: str, requirement: dict, files: dict, as_of: date) -> dict:
    bank_profile = files['01_entity/bank_profile.json']
    if topic_key == 'esg_risk_management':
        return assess_requirement_applicability(requirement, bank_profile, files['02_business/products.json'], as_of)
    if topic_key == 'instant_payments':
        return assess_requirement_applicability(
            requirement, bank_profile, files['02_business/products.json'], as_of,
            candidate_product_types=PAYMENT_INITIATION_PRODUCT_TYPES,
            classify_fn=classify_payment_product, no_candidate_label='payment-initiation')
    return assess_bank_level_applicability(requirement, bank_profile, as_of)  # dora / frtb: bank-level, not per-product


def new_stage(name: str) -> dict:
    return dict(name=name, state='pending', summary='', detail='', evidence=[], human=None)


def assess_change(topic_key: str, files: dict, as_of: date = None) -> dict:
    """Returns the STATE.events-shaped result for one regulatory change (the 5
    fixed stages, each 'done'/'active'/'pending' -- matching the reference
    frontend's own shape) plus a per_requirement breakdown for audit."""
    as_of = as_of or date.fromisoformat(files['01_entity/bank_profile.json']['as_of_date'])
    change = find_change(files, topic_key)
    depth = DEPTH[topic_key]
    controls_by_id = {c['control_id']: c for c in files['04_governance/controls.json']['controls']}
    stages = {name: new_stage(name) for name in STAGE_NAMES}
    per_requirement = []
    applicabilities, gap_lines = [], []

    if 'restraint' in depth:
        # Restraint is a bank-wide fact (no material trading book / internal model /
        # trading activity), not something that varies per FRTB requirement -- checked
        # once here, before any per-requirement gate, rather than letting a requirement
        # whose only compliance_events are a "review" cadence with no date (see
        # BINDING_DATE_EVENT_TYPES above) fall through gate3 as a false
        # needs_human_review and never reach this check at all.
        restraint = frtb_restraint_check(files['01_entity/bank_profile.json'], files['02_business/business_lines.json'])
        if restraint:
            stages['适用性']['state'] = 'active'
            stages['适用性']['summary'] = restraint['business_relevance']
            stages['适用性']['human'] = dict(question=restraint['queue_item']['payload']['reasonText'])
            per_requirement = [dict(requirement_id=rid, restraint=restraint) for rid in change['requirement_ids']]
            return dict(change_id=change['change_id'], topic_key=topic_key, depth=depth,
                        stages=list(stages.values()), per_requirement=per_requirement)
        # else: facts don't support restraint (e.g. a future data change) -- fall
        # through to the normal per-requirement gates below, same as any other topic.

    for req_id in change['requirement_ids']:
        requirement = find_requirement(files, req_id)
        record = dict(requirement_id=req_id)

        applicability = run_applicability_for_topic(topic_key, requirement, files, as_of)
        record['applicability'] = applicability
        applicabilities.append(applicability['applicability'])
        if applicability['applicability'] == 'needs_human_review':
            stages['适用性']['state'] = 'active'
            stages['适用性']['human'] = dict(question=f"{req_id}: {applicability['rationale']}")
            per_requirement.append(record)
            continue

        if 'gap' in depth and applicability['applicability'] in ('direct', 'indirect'):
            gap = assess_capability_gap(requirement, controls_by_id)
            record['gap'] = gap
            gap_lines.append(f"{req_id}: {gap['status']} ({gap['rationale']})")

        per_requirement.append(record)

    if stages['适用性']['state'] != 'active':
        stages['适用性']['state'] = 'done'
    stages['适用性']['summary'] = ', '.join(sorted(set(applicabilities))) or 'no requirements evaluated'
    if gap_lines:
        stages['能力缺口']['state'] = 'done'
        stages['能力缺口']['summary'] = f'{len(gap_lines)} requirement(s) assessed'
        stages['能力缺口']['detail'] = ' | '.join(gap_lines)

    return dict(change_id=change['change_id'], topic_key=topic_key, depth=depth,
                stages=list(stages.values()), per_requirement=per_requirement)
