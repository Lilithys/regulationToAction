"""Idempotent integrity migration of existing source-backed/synthetic records.

No new law or bank controls. Criteria and mapping annotations are provisional
interpretations of already supplied text, never qualified sign-off.
"""
from copy import deepcopy
import json
from project_paths import PROJECT_ROOT

CONTRACT_VERSION = '0.2.1'

def migrate_governance(package):
    history = json.loads((PROJECT_ROOT/'config/dataset_migration_history.json').read_text())['superseded_mapping_notes']
    requirements = package['requirements']['requirements']
    controls = package['controls']['controls']
    change = next(c for c in package['changes']['changes'] if c['topic_key'] == 'esg_risk_management')
    events = [e for e in change['application_events'] if e['event_type'] == 'application']
    for event in events:
        selector = 'other than' not in event.get('applies_to', '').lower()
        event.setdefault('extensions', {})['snci_selector'] = selector
    for req in requirements:
        rid = req['requirement_id']
        ext = req.setdefault('extensions', {})
        ext['assessment_contract_version'] = CONTRACT_VERSION
        ext['jurisdiction_basis'] = 'product' if rid.startswith('REQ-IPS') else 'institution'
        if rid.startswith('REQ-ESG'):
            req['applicability_conditions'] = [c for c in req['applicability_conditions']
                                                if not c.get('fact_path', '').endswith('#/snci_status')]
            date_cid = 'CIT-' + rid + '-DATE'
            req['compliance_events'] = [dict(event_type='application', date=e['date'], condition=e['applies_to'],
                 source_citation_ids=[date_cid], verification_status=e['verification_status'],
                 extensions=deepcopy(e['extensions'])) for e in events]
    byid = {r['requirement_id']: r for r in requirements}
    ctrl = next(c for c in controls if c['control_id'] == 'CTRL-ESG-ONBOARD-SCREEN')
    supported = ['REQ-ESG-CREDIT-POLICY-001', 'REQ-ESG-RISK-INTEGRATION-001']
    removed = ['REQ-ESG-CREDIT-MONITORING-001', 'REQ-ESG-LONG-HORIZON-001']
    ctrl['requirement_ids'] = supported
    for rid in removed:
        req = byid[rid]
        req['control_ids'] = [cid for cid in req['control_ids'] if cid != ctrl['control_id']]
        req['current_coverage'].update(control_ids=list(req['control_ids']), rating='unknown', uncovered_dimensions=[],
            rationale='Prior onboarding link withdrawn after semantic review; investigate requirement-specific design and operating evidence.')
        req['extensions']['mapping_review'] = dict(
            method_version='semantic-mapping-v1', review_status='provisional',
            candidate_control_id=ctrl['control_id'], relationship='related_not_supporting',
            rationale=('Per-application sector screening does not establish ongoing existing-book monitoring.'
                       if 'MONITORING' in rid else 'No ten-year horizon or long-term analysis appears in the control objective/frequency.'),
            evidence_fields=['objective', 'frequency', 'coverage'],
            note='Requirement split lineage is not evidence of substantive coverage.')
    criteria = {
        'REQ-ESG-CREDIT-POLICY-001': [('population', 'new_lending_applications'), ('design', 'esg_origination_criteria')],
        'REQ-ESG-CREDIT-MONITORING-001': [('population', 'existing_portfolio'), ('frequency', 'ongoing_monitoring'), ('design', 'environmental_risk_metrics')],
        'REQ-ESG-RISK-INTEGRATION-001': [('process', 'credit_origination'), ('process', 'ongoing_risk_management')],
        'REQ-ESG-LONG-HORIZON-001': [('horizon', 'at_least_ten_years'), ('horizon', 'short_and_medium_term')],
    }
    for rid, dims in criteria.items():
        req = byid[rid]
        req['extensions']['coverage_criteria'] = [dict(dimension_type=t, dimension_ref=r) for t, r in dims]
        req['extensions']['criteria_basis'] = dict(review_status='provisional', source_citation_ids=[req['source_citations'][0]['citation_id']],
            scope='Selected credit-risk investigation criteria; not a claim of exhaustive bank-wide compliance.')
    def coverage(kind, ref, status, reason):
        return dict(dimension_type=kind, dimension_ref=ref, coverage_status=status, rationale=reason)
    mappings = [
        dict(requirement_id=supported[0], support='partial', review_status='provisional',
             rationale='Sector screen supports origination only; it does not establish the complete sectoral credit criteria.',
             evidence_fields=['objective', 'frequency', 'coverage'], coverage=[
                 coverage('population','new_lending_applications','covered','Explicit control objective and per-application frequency.'),
                 coverage('design','esg_origination_criteria','partially_covered','Sector screening alone does not demonstrate the complete credit policy criteria.')]),
        dict(requirement_id=supported[1], support='partial', review_status='provisional',
             rationale='One origination activity contributes to regular risk management; ongoing integration remains unproven.',
             evidence_fields=['objective', 'frequency', 'coverage'], coverage=[
                 coverage('process','credit_origination','covered','Sector-level ESG screen before credit approval.'),
                 coverage('process','ongoing_risk_management','not_covered','Control is per application; existing-book monitoring is explicitly excluded.')])]
    ctrl.setdefault('extensions', {})['requirement_mappings'] = mappings
    # Existing non-ESG design coverage is scoped to its own explicit requirement,
    # not copied from all controls into every requirement.
    for control in controls:
        if control is ctrl:
            continue
        control.setdefault('extensions', {})['requirement_mappings'] = [dict(
            requirement_id=rid, support='partial', review_status='provisional',
            rationale='Supplied control objective and declared coverage; operating effectiveness unverified.',
            evidence_fields=['objective','frequency','coverage'], coverage=deepcopy(control.get('coverage', [])))
            for rid in control.get('requirement_ids', [])]
        for rid in control.get('requirement_ids', []):
            byid[rid]['extensions']['coverage_criteria'] = [
                {k: c[k] for k in ('dimension_type', 'dimension_ref')} for c in control.get('coverage', [])]
    for row in requirements + controls:
        rid = row.get('requirement_id', row.get('control_id'))
        if rid in history:
            row['provenance']['notes'] = [n for n in row['provenance']['notes'] if not n.startswith('2026-09-11:')]
            row.setdefault('extensions', {})['superseded_mapping_annotations'] = history[rid]
            note = 'M1 semantic review supersedes the archived 2026-09-11 lineage-based mapping; see extensions.'
            if note not in row['provenance']['notes']:row['provenance']['notes'].append(note)
    return package
