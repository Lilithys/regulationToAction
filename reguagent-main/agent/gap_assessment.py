"""Requirement-specific design assessment, separate from operating evidence.

Pre-filled links are investigation leads. Only scoped supported mapping rows can
contribute coverage; no-link is unknown until a documented absence review exists.
"""
from __future__ import annotations
import hashlib
from datetime import date
from pathlib import Path


def _key(row):
    return row.get('dimension_type'), row.get('dimension_ref')


def _valid_reviewed_artifact(e, root, as_of):
    if (not root or as_of is None or e.get('status') != 'accepted'
            or e.get('human_review_status') != 'approved'
            or not e.get('reviewed_by') or not e.get('reviewed_at')
            or not e.get('collected_at') or not e.get('valid_through')
            or e.get('content_review_status') != 'supported'):
        return False
    try:
        collected = date.fromisoformat(e['collected_at'][:10])
        reviewed = date.fromisoformat(e['reviewed_at'][:10])
        valid = date.fromisoformat(e['valid_through'])
        if not collected <= reviewed <= as_of <= valid:
            return False
        base = Path(root).resolve()
        path = (base / e.get('artifact_path', '')).resolve()
        return (path.is_relative_to(base) and path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == e.get('content_sha256')
                and e.get('reviewed_content_sha256') == e.get('content_sha256'))
    except (ValueError, TypeError, OSError):
        return False


def _accepted_evidence(evidence, ctrl, rid, criterion, root, as_of):
    if ctrl.get('operating_status') != 'operating':
        return False
    return any(e.get('evidence_id') in ctrl.get('evidence_item_ids', [])
        and e.get('control_id') == ctrl['control_id']
        and rid in e.get('requirement_ids', [])
        and criterion in {_key(c) for c in e.get('tested_criteria', [])}
        and e.get('test_result') == 'passed'
        and _valid_reviewed_artifact(e, root, as_of) for e in evidence)


def assess_capability_gap(requirement, controls_by_id, evidence=None, *, root=None, as_of=None, search_context=None):
    rid = requirement['requirement_id']
    ids = requirement.get('control_ids', [])
    criteria = requirement.get('extensions', {}).get('coverage_criteria', [])
    evidence = evidence or []
    base = dict(requirement_id=rid, status='insufficient_evidence', control_ids=ids,
                mapping_support='unresolved', design_coverage='unknown', operating_evidence='unverified',
                criteria_results=[], gap_flags=[], review_status='provisional',
                assessment_version='gap-v0.2', search_status=(search_context or {}).get('status', 'not_complete'))
    if not ids:
        search = search_context or {}
        absence_records = [e for e in evidence
                           if e.get('evidence_id') in search.get('negative_evidence_references', [])
                           and e.get('evidence_type') == 'capability_absence_review'
                           and e.get('requirement_ids') == [rid] and e.get('absence_confirmed') is True
                           and set(controls_by_id).issubset(set(e.get('searched_control_ids', [])))
                           and _valid_reviewed_artifact(e, root, as_of)]
        absent = (search.get('status') == 'complete' and search.get('requirement_id') == rid
                  and bool(absence_records)
                  and set(controls_by_id).issubset(set(search.get('searched_control_ids', []))))
        base.update(status='missing' if absent else 'insufficient_evidence',
                    mapping_support='confirmed_absent' if absent else 'not_found',
                    rationale='Documented scoped absence review supplied.' if absent else
                    'No supported control mapping yet; search governance text and document absence before declaring a missing capability.')
        return base
    missing = [cid for cid in ids if cid not in controls_by_id]
    if missing:
        return dict(base, rationale=f'Unresolved control references: {missing}.')
    controls = [controls_by_id[cid] for cid in ids]
    mappings = [(c, m) for c in controls for m in c.get('extensions', {}).get('requirement_mappings', [])
                if m.get('requirement_id') == rid and m.get('support') in ('partial', 'supported')
                and m.get('rationale') and m.get('evidence_fields')]
    if not mappings or not criteria:
        return dict(base, rationale='Linked control exists, but requirement-specific mapping support or coverage criteria are absent.')
    base['mapping_support'] = 'candidate_supported'
    base['gap_flags'] = sorted({g for c in controls for g in c.get('gap_flags', []) if isinstance(g, str)})
    for criterion in criteria:
        key = _key(criterion)
        rows = [(c, row) for c, m in mappings for row in m.get('coverage', []) if _key(row) == key]
        statuses = {r.get('coverage_status') for _, r in rows}
        # Union across controls is permitted within the exact same criterion. A
        # partial subset cannot become full just by adding another partial subset.
        coverage = next((s for s in ('covered', 'partially_covered', 'unknown', 'not_covered') if s in statuses), 'unknown')
        operating = any(_accepted_evidence(evidence, c, rid, key, root, as_of)
                        for c, row in rows if row.get('coverage_status') == 'covered')
        base['criteria_results'].append(dict(criterion, coverage_status=coverage,
            control_ids=sorted({c['control_id'] for c, _ in rows}),
            operating_evidence='verified' if operating else 'unverified',
            reasons=[r.get('rationale', '') for _, r in rows]))
    rows = base['criteria_results']
    all_design = all(r['coverage_status'] == 'covered' for r in rows)
    some_design = any(r['coverage_status'] in ('covered', 'partially_covered') for r in rows)
    all_operating = all(r['operating_evidence'] == 'verified' for r in rows)
    design = 'covered' if all_design else ('partial' if some_design else 'unknown')
    status = 'evidenced' if all_design and all_operating else ('partial' if some_design else 'insufficient_evidence')
    unresolved = [r['dimension_ref'] for r in rows if r['coverage_status'] != 'covered']
    base.update(status=status, design_coverage=design,
                operating_evidence='verified' if all_operating else 'unverified',
                rationale=f'Requirement-specific design={design}; unresolved design criteria={unresolved}; operating evidence={"verified" if all_operating else "unverified"}. Assessment covers only the declared criteria, not overall legal compliance.')
    return base


def frtb_restraint_check(bank_profile: dict, business_lines: list[dict]) -> dict | None:
    """FRTB is the deliberate negative case (evaluation_ground_truth CASE-FRTB-BASE):
    must reach limited/uncertain from real bank facts, never invent a remediation
    programme just because the regulation exists. Returns None if the facts don't
    support restraint, so the caller falls through to the normal gap path instead."""
    boundaries = bank_profile.get('business_model_boundaries', {})
    treasury = next((bl for bl in business_lines if bl['business_line_id'] == 'BL-TREASURY'), None)
    no_material_book = boundaries.get('material_trading_book') is False
    no_internal_model = boundaries.get('internal_market_risk_model') is False
    no_material_activity = treasury is not None and treasury.get('material_trading_activity') is False
    if not (no_material_book and no_internal_model and no_material_activity):
        return None

    return dict(
        applicability='uncertain', business_relevance='limited',
        allowed_action='refresh_scope_evidence_and_monitor',
        rationale=('bank_profile.business_model_boundaries reports no material trading book and no internal '
                   'market-risk model; BL-TREASURY reports no material trading activity. This supports limited '
                   'business relevance, but current-position and legal-basis evidence (see missing_facts.json '
                   'FACT-FRTB-CURRENT-EXPOSURE) is still outstanding, so applicability stays uncertain rather '
                   'than a blanket exemption.'),
        queue_item=dict(section='earlyexit', payload=dict(
            reasonText=('No material trading book, no internal market-risk model, and no material trading '
                        'activity in Treasury; recommend closing this cycle as monitor-only pending current '
                        'position and legal-basis evidence, not a full remediation programme.'),
            regulationTitle='FRTB / CRR3 small-trading-book-business threshold')))
