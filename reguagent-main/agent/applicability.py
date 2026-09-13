"""Provisional scope assessment; dates, demo priority and legal review are separate.

Legacy applicability labels remain for existing views. Consumers making decisions
must use legal_scope/temporal_status/review_status and unresolved_product_ids.
"""
from __future__ import annotations
from datetime import date
from urllib.parse import unquote
from regulatory_dates import select_event, event_applies as _event_applies_to_snci

RULE_VERSION = 'applicability-v0.2'
EU_COUNTRIES = frozenset('AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE'.split())
EEA_COUNTRIES = EU_COUNTRIES | {'IS', 'LI', 'NO'}
CREDIT_PRODUCT_CLASSIFICATION = {
    'sme_term_loan': 'direct', 'unsecured_consumer_credit': 'indirect',
    'owner_occupied_residential_mortgage': 'indirect', 'internal_liquidity_management': 'limited',
}
PAYMENT_INITIATION_PRODUCT_TYPES = {'euro_instant_payment_transfer', 'euro_payment_transfer', 'payment_initiation_service'}
KNOWN_NON_CREDIT = {'current_account', 'instant_access_savings', 'debit_card',
                    'business_current_account', 'business_debit_card'} | PAYMENT_INITIATION_PRODUCT_TYPES
KNOWN_PRODUCT_TYPES = set(CREDIT_PRODUCT_CLASSIFICATION) | KNOWN_NON_CREDIT
BINDING_DATE_EVENT_TYPES = {'application', 'institution_deadline', 'transition'}


def resolve_pointer(obj, pointer: str):
    if pointer.startswith('#'):
        pointer = unquote(pointer[1:])
    if pointer == '':
        return obj, True
    if not pointer.startswith('/'):
        return None, False
    cur = obj
    for part in pointer[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and (part == '0' or not part.startswith('0')) and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None, False
    return cur, True


def eval_condition(condition: dict, bank_profile: dict) -> str:
    if condition.get('condition_type') != 'bank_fact' or condition.get('operator') != 'equals':
        return 'undetermined'
    path = condition.get('fact_path', '').split('#', 1)
    if len(path) != 2 or path[0] != '01_entity/bank_profile.json':
        return 'undetermined'
    value, found = resolve_pointer(bank_profile, path[1])
    if not found or value is None or value == '':
        return 'undetermined'
    expected = condition.get('expected_value', [])
    return 'met' if any(type(value) is type(v) and value == v for v in expected) else 'not_met'


def gate1_requirement_complete(requirement):
    missing = [k for k in ('addressee_types', 'jurisdictions', 'applicability_conditions') if not requirement.get(k)]
    return (not missing, f'Requirement extraction incomplete: missing {missing}.' if missing else '')


def gate3_temporal_status(requirement, bank_profile, as_of):
    """Legacy 'in_force' means application date reached, never legal sign-off."""
    event = select_event(requirement.get('compliance_events', []), bank_profile)
    if event is None:
        return 'unknown', None
    return ('in_force' if date.fromisoformat(event['date']) <= as_of else 'not_yet_effective'), event


def gate4_entity_conditions(requirement, bank_profile):
    results, reasons = [], []
    for cond in requirement.get('applicability_conditions', []):
        # Migration compatibility: SNCI selects a date, never excludes an institution.
        if cond.get('fact_path', '').endswith('#/snci_status'):
            continue
        result = eval_condition(cond, bank_profile)
        results.append(result)
        reasons.append(f"{cond.get('description', 'Entity condition')} -> {result}")
    if 'not_met' in results:
        return 'not_met', reasons
    return ('met' if results and 'undetermined' not in results else 'undetermined'), reasons


def region_match(markets, jurisdictions):
    if not markets or not jurisdictions or any(not m for m in markets):
        return None
    covered = set(jurisdictions)
    if 'EU' in covered:
        covered |= EU_COUNTRIES
    if 'EEA' in covered:
        covered |= EEA_COUNTRIES
    if any(m in covered for m in markets):
        return True
    # Unknown codes cannot establish exclusion. Valid non-EEA codes used by tests
    # and scenarios are explicitly listed; arbitrary strings stay unknown.
    known = EEA_COUNTRIES | {'US', 'GB', 'CH', 'CA', 'AU', 'JP', 'CN', 'EU', 'EEA'}
    return False if all(m in known for m in markets) else None


def gate5_region_ok(product, requirement):
    result = region_match(product.get('markets'), requirement.get('jurisdictions'))
    return result, f"Product markets={product.get('markets')}; jurisdiction overlap={result}."


def classify_credit_product(product):
    kind = product.get('product_type')
    outcome = CREDIT_PRODUCT_CLASSIFICATION.get(kind)
    if outcome:
        return outcome, f'Credit relevance={outcome}; demo priority is separate from legal scope.'
    if kind in KNOWN_NON_CREDIT:
        return 'not_applicable', 'No credit activity identified for this product in the supplied taxonomy.'
    return 'needs_human_review', f'Unclassified product type {kind!r}; investigate activity.'


def classify_payment_product(product):
    kind = product.get('product_type')
    if kind in PAYMENT_INITIATION_PRODUCT_TYPES:
        return 'direct', 'Payment-initiation activity identified; operative exceptions require review.'
    if kind in KNOWN_PRODUCT_TYPES:
        return 'not_applicable', 'No payment-initiation activity identified in the supplied taxonomy.'
    return 'needs_human_review', f'Unclassified product type {kind!r}; investigate activity.'


def _base(requirement, bank, as_of):
    temporal, event = gate3_temporal_status(requirement, bank, as_of)
    annotation = requirement.get('annotation', {})
    reviewed = (annotation.get('label_status') == 'gold' and annotation.get('reviewed_by')
                and annotation.get('reviewed_at') and requirement.get('record_status') == 'verified')
    return dict(requirement_id=requirement['requirement_id'], rule_version=RULE_VERSION,
                calculation_timestamp=as_of.isoformat(), as_of_date=as_of.isoformat(),
                requirement_review_status=annotation.get('label_status', 'unknown'),
                review_status='reviewed' if reviewed else 'provisional',
                temporal_status={'in_force': 'application_date_reached', 'not_yet_effective': 'before_application_date'}.get(temporal, 'unknown'),
                selected_event=event, legal_scope='unknown', demo_scope='investigate',
                evidence_record_ids=[], evidence_references=[])


def _entity_scope(requirement, bank):
    complete, reason = gate1_requirement_complete(requirement)
    if not complete:
        return 'unknown', reason
    status, reasons = gate4_entity_conditions(requirement, bank)
    region = region_match([bank.get('headquarters', {}).get('country_code')], requirement.get('jurisdictions'))
    if status == 'not_met' or region is False:
        return 'out_of_scope', '; '.join(reasons) + f'; entity jurisdiction overlap={region}.'
    if status != 'met' or region is None:
        return 'unknown', '; '.join(reasons) + f'; entity jurisdiction overlap={region}.'
    return 'in_scope', '; '.join(reasons) + '; entity jurisdiction matches.'


def assess_product_applicability(requirement, bank_profile, product, as_of, classify_fn=classify_credit_product):
    base = _base(requirement, bank_profile, as_of)
    base['product_id'] = product['product_id']
    entity_scope, reason = _entity_scope(requirement, bank_profile)
    relevance, class_reason = classify_fn(product)
    legal = entity_scope
    # Institution-level risk management is scoped by the entity; do not claim its
    # US exposures are geographically in the EU. Activity-level duties also inspect markets.
    basis = requirement.get('extensions', {}).get('jurisdiction_basis', 'product')
    if legal == 'in_scope':
        region, region_reason = gate5_region_ok(product, requirement)
        reason += ' ' + (region_reason if basis == 'product' else 'Jurisdiction basis: institution, not product market.')
        if basis == 'product' and region is not True:
            legal = 'out_of_scope' if region is False else 'unknown'
        if relevance == 'not_applicable':
            legal = 'out_of_scope'
        elif relevance in ('needs_human_review', 'limited') and legal != 'out_of_scope':
            legal = 'unknown'
    outcome = relevance if legal == 'in_scope' else ('not_applicable' if legal == 'out_of_scope' else 'needs_human_review')
    # Keep limited relevance visible in old views, without converting it into exemption.
    if legal == 'unknown' and relevance == 'limited' and entity_scope == 'in_scope':
        outcome = 'limited'
    base.update(legal_scope=legal, applicability=outcome,
                demo_scope='primary' if relevance == 'direct' and legal == 'in_scope' else ('deferred' if relevance in ('indirect', 'limited') else 'investigate'),
                rationale=reason + ' ' + class_reason,
                evidence_record_ids=[product['product_id']],
                evidence_references=[{'path': '01_entity/bank_profile.json', 'pointer': '/entity_classification'},
                                     {'path': '02_business/products.json', 'id_field': 'product_id', 'record_id': product['product_id']}])
    return base


def assess_requirement_applicability(requirement, bank_profile, products, as_of,
                                      candidate_product_types=None, classify_fn=classify_credit_product,
                                      no_candidate_label='credit/lending'):
    # Deliberately evaluate every product. An allowlist must not hide novel products.
    results = [assess_product_applicability(requirement, bank_profile, p, as_of, classify_fn) for p in products]
    base = _base(requirement, bank_profile, as_of)
    inside = [r['product_id'] for r in results if r['legal_scope'] == 'in_scope']
    outside = [r['product_id'] for r in results if r['legal_scope'] == 'out_of_scope']
    unresolved = [r['product_id'] for r in results if r['legal_scope'] == 'unknown']
    legal = 'in_scope' if inside else ('unknown' if unresolved or not results else 'out_of_scope')
    priority = ['direct', 'indirect', 'needs_human_review', 'limited', 'not_applicable']
    overall = min((r['applicability'] for r in results), key=priority.index) if results else 'needs_human_review'
    base.update(applicability=overall, legal_scope=legal,
                demo_scope='primary' if any(r['demo_scope'] == 'primary' for r in results) else 'investigate',
                in_scope_products=inside, out_of_scope_products=outside, unresolved_product_ids=unresolved,
                product_results=results, scope_complete=not unresolved and bool(results),
                evidence_record_ids=sorted({x for r in results for x in r['evidence_record_ids']}),
                rationale=f'Entity/activity assessment: {len(inside)} candidate in-scope, {len(unresolved)} unresolved; review={base["review_status"]}. Product counts are descriptive, not the legal basis.')
    return base


def direct_only_products(applicability_result):
    return [r['product_id'] for r in applicability_result.get('product_results', [])
            if r['legal_scope'] == 'in_scope' and r['demo_scope'] == 'primary']


def assess_bank_level_applicability(requirement, bank_profile, as_of):
    base = _base(requirement, bank_profile, as_of)
    legal, reason = _entity_scope(requirement, bank_profile)
    base.update(legal_scope=legal, applicability={'in_scope': 'direct', 'out_of_scope': 'not_applicable', 'unknown': 'needs_human_review'}[legal],
                demo_scope='auxiliary', rationale=reason,
                evidence_references=[{'path': '01_entity/bank_profile.json', 'pointer': '/entity_classification'}])
    return base
