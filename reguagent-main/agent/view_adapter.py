"""Read-only projection of CaseStore state into frontend-facing shapes (T21), plus
the server-side dispatch/validation for resolving one pending item (T22). No
business logic lives here -- every write goes through the same InvestigationTools/
CaseStore entry points already used by the CLI and tested elsewhere; this module
only shapes data for display and routes a request to the right one of them.

No frontend_app exists in this workspace (T21 explicitly anticipates that case).
The old Integration-Guide.md queue/section contract predates the M1-M4 case model
(Case/Finding/Question/GapAssessment/PlanVersion/Action/Evidence, four collaborative
roles, not a five-stage A/B/C/D pipeline) and cannot be reused field-for-field; the
'section'-tagged pending-queue pattern and server-revalidates-on-resolve rule are
kept because they still fit, everything else is grounded in the real object model.
"""
from __future__ import annotations
from case_store import digest
from evidence_intake import evaluate_closure, submit_evidence as _submit_evidence
from investigation_tools import InvestigationTools, FACT_ID, ANSWER_SCHEMA
from tool_contracts import validate


def _current(store, case_id, kind):
    return store.objects(case_id, kind)


def case_overview(store, case_id):
    case = store.case(case_id)
    objects = store.objects(case_id)
    counts = {}
    for o in objects:counts[o['kind']] = counts.get(o['kind'], 0) + 1
    return dict(case_id=case_id, goal=case['goal'], mode=case['mode'], status=case['status'],
        as_of_date=case['as_of_date'], snapshot_dates=case['snapshot_dates'], revision=case['revision'],
        created_at=case['created_at'], updated_at=case['updated_at'], object_counts=counts,
        audit_chain_valid=store.verify_audit(case_id))


def case_list(store):
    grouped={}
    for c in store.cases():
        source=next(iter(store.objects(c['case_id'],'SourceVersion')),None)
        payload=source['payload'] if source else {}
        change=payload.get('change',{})
        requirement=next(iter(store.inputs(c['case_id']).get('regulatory_sources/requirements.json',{}).get('requirements',[])),{})
        title=change.get('title') or requirement.get('title') or 'Regulatory change'
        findings=store.objects(c['case_id'],'Finding')
        summary=(findings[0]['payload'].get('summary') if findings else None) or requirement.get('requirement_text') or c['goal']
        item=dict(case_id=c['case_id'], title=title, summary=summary, goal=c['goal'], mode=c['mode'], status=c['status'],
                  as_of_date=c['as_of_date'], snapshot_dates=c['snapshot_dates'], revision=c['revision'], updated_at=c['updated_at'])
        previous=grouped.get(title)
        if previous is None or item['updated_at'] > previous['updated_at']:
            grouped[title]=item
    return list(grouped.values())


def decision_view(store, case_id, artifact_root=None):
    """Return a decision-oriented projection for the primary case screen.

    This keeps database object shapes out of the UI while preserving provenance
    and the distinction between provisional analysis and human decisions.
    """
    case = store.case(case_id)
    source = next(iter(_current(store, case_id, 'SourceVersion')), None)
    source_payload = source['payload'] if source else {}
    change = source_payload.get('change', {})
    requirement = next(iter(store.inputs(case_id).get('regulatory_sources/requirements.json', {}).get('requirements', [])), {})
    findings = _current(store, case_id, 'Finding')
    gaps = _current(store, case_id, 'GapAssessment')
    plans = _current(store, case_id, 'PlanVersion')
    actions = _current(store, case_id, 'Action')
    questions = _current(store, case_id, 'Question')
    queue = pending_queue(store, case_id, artifact_root)

    impact = {}
    for finding in findings:
        payload = finding['payload']
        if isinstance(payload.get('part_b'), dict):
            impact.update(payload['part_b'])
    gap_items = [dict(key=o['object_key'], status=o['status'],
                      requirement_id=o['payload'].get('requirement_id'),
                      control_id=o['payload'].get('candidate_control_id'),
                      mapping_support=o['payload'].get('mapping_support'),
                      design_coverage=o['payload'].get('design_coverage'),
                      operating_evidence=o['payload'].get('operating_evidence'),
                      rationale=o['payload'].get('rationale'),
                      review_status=o['payload'].get('review_status')) for o in gaps]
    action_items = [_action_view(store, case_id, o) for o in actions]
    open_questions = [dict(key=o['object_key'], question=o['payload'].get('question'),
                           owner_role_id=o['payload'].get('owner_role_id'), version=o['version'])
                      for o in questions if o['status'] == 'open']
    if open_questions:
        next_step = dict(type='human_input', title='Human input required',
                         message='Answer the open business question before continuing the investigation.')
    elif queue:
        next_step = dict(type='human_decision', title='Human decision required',
                         message='Review the first pending item in the queue.')
    elif case['status'] in ('failed', 'running'):
        next_step = dict(type='continue', title='Continue investigation',
                         message='Resume the coordinator from the saved checkpoint.')
    else:
        next_step = dict(type='review', title='Review provisional results',
                         message='Review the evidence and provisional conclusions before approval.')
    completed = sum(1 for obj in (findings + gaps + plans + actions) if obj['status'] not in ('draft', 'stale'))
    total = len(findings) + len(gaps) + len(plans) + len(actions)
    stage_states = [
        ('Regulatory change', bool(source)),
        ('Business impact', bool(impact)),
        ('Control gaps', bool(gaps)),
        ('Recommended action', bool(actions)),
        ('Human review', not bool(open_questions) and not bool(queue)),
    ]
    return dict(
        case=dict(case_id=case_id, goal=case['goal'], mode=case['mode'], status=case['status'],
                  as_of_date=case['as_of_date'], revision=case['revision']),
        regulatory_change=dict(title=change.get('title') or source_payload.get('title') or requirement.get('title') or 'Registered regulatory change',
                       legal_status=change.get('legal_status') or requirement.get('legal_force'), source_id=source_payload.get('source_id'),
                               requirement_ids=change.get('requirement_ids', []),
                       effective_date=(change.get('application_events') or [{}])[0].get('date') or
                       (requirement.get('compliance_events') or [{}])[0].get('date'),
                               intake_mode=source_payload.get('intake_mode'), limitations=source_payload.get('note'),
                               review_status=source_payload.get('review_status'), reviewed_by=source_payload.get('reviewed_by')),
        impact=impact,
        findings=[dict(key=o['object_key'], summary=o['payload'].get('summary'), category=o['payload'].get('category'),
                       status=o['status'], review_status=o['payload'].get('review_status'),
                       reference_ids=o['payload'].get('reference_ids', [])) for o in findings],
        gaps=gap_items, actions=action_items, open_questions=open_questions,
        pending_count=len(queue), pending=queue,
        progress=dict(completed=completed, total=total),
        stages=[dict(name=name, state='done' if done else ('active' if index == completed else 'pending'))
            for index,(name,done) in enumerate(stage_states)],
        next_step=next_step)


def investigation_summary(store, case_id):
    tasks = [dict(key=o['object_key'], role=o['payload']['role'], task=o['payload']['task'],
        status=o['status'], version=o['version']) for o in _current(store, case_id, 'Task')]
    findings = [dict(key=o['object_key'], version=o['version'], status=o['status'],
        summary=o['payload']['summary'], category=o['payload']['category'],
        author_role=o['payload']['author_role'], review_status=o['payload']['review_status'],
        reference_ids=o['payload']['reference_ids']) for o in _current(store, case_id, 'Finding')]
    gaps = [dict(key=o['object_key'], version=o['version'], status=o['status'],
        requirement_id=o['payload']['requirement_id'], candidate_control_id=o['payload']['candidate_control_id'],
        mapping_support=o['payload']['mapping_support'], design_coverage=o['payload']['design_coverage'],
        operating_evidence=o['payload']['operating_evidence'], rationale=o['payload']['rationale'],
        author_role=o['payload']['author_role'], review_status=o['payload']['review_status'])
        for o in _current(store, case_id, 'GapAssessment')]
    open_questions = [dict(key=o['object_key'], version=o['version'], owner_role_id=o['payload']['owner_role_id'],
        question=o['payload']['question'], decision_reason=o['payload']['decision_reason'])
        for o in _current(store, case_id, 'Question') if o['status'] == 'open']
    return dict(tasks=tasks, findings=findings, gap_assessments=gaps, open_questions=open_questions)


def _plan_view(o):
    calc = o['payload']['calculation']
    return dict(key=o['object_key'], version=o['version'], status=o['status'], option_id=o['payload']['option_id'],
        addresses_requirement_ids=o['payload']['addresses_requirement_ids'],
        deferred_requirement_ids=o['payload']['deferred_requirement_ids'],
        rationale=o['payload']['rationale'], recommendation_status=o['payload']['recommendation_status'],
        author_role=o['payload'].get('author_role'),
        three_year_tco_eur=calc['scenarios']['base']['three_year_tco_eur'],
        setup_total_eur=calc['setup_total_eur'], capacity_sufficient=calc['capacity_sufficient'],
        regulatory_deadline_feasible=calc['regulatory_deadline_feasible'],
        selected_regulatory_due_date=calc['selected_regulatory_due_date'])


def _action_view(store, case_id, o):
    p = o['payload']
    required_evidence = [dict(slot, submitted=store.get(case_id, 'Evidence', o['object_key']+'::'+slot['evidence_key']) is not None)
        for slot in p['required_evidence']]
    return dict(key=o['object_key'], version=o['version'], status=o['status'], plan_key=p['plan_key'],
        title=p['title'], steps=p['steps'], accountable_role_id=p['accountable_role_id'],
        author_role=p.get('author_role'),
        target_date=p['target_date'], internal_target_status=p['internal_target_status'],
        regulatory_due_date=p['regulatory_due_date'], regulatory_deadline_status=p['regulatory_deadline_status'],
        acceptance_status=p['acceptance_status'], accepted_by_role_id=p.get('accepted_by_role_id'),
        required_evidence=required_evidence, closure_status=p.get('closure_status'),
        closure_scope_note=p.get('closure_scope_note'))


def plan_and_action_view(store, case_id):
    return dict(plans=[_plan_view(o) for o in _current(store, case_id, 'PlanVersion')],
                actions=[_action_view(store, case_id, o) for o in _current(store, case_id, 'Action')])


def _evidence_view(o):
    p = o['payload']
    return dict(key=o['object_key'], version=o['version'], status=o['status'], action_key=p['action_key'],
        evidence_key=p['evidence_key'], evidence_type=p['evidence_type'], title=p['title'],
        submitted_by_role_id=p['submitted_by_role_id'], collected_at=p['collected_at'],
        content_assessment=p.get('content_assessment'), content_rationale=p.get('content_rationale'),
        human_decision=p.get('human_decision'), decided_by_role_id=p.get('decided_by_role_id'))


def evidence_view(store, case_id):
    current = [_evidence_view(o) for o in _current(store, case_id, 'Evidence')]
    history = {}
    for o in store.objects(case_id, 'Evidence', current=False):
        history.setdefault(o['object_key'], []).append(_evidence_view(o))
    for versions in history.values():versions.sort(key=lambda v: v['version'])
    return dict(current=current, history=history)


def audit_log(store, case_id):
    return [dict(seq=e['seq'], at=e['created_at'], actor_type='human' if e['actor'] in ('human_input', 'replay_fixture') else
                 ('application' if e['actor'] == 'application' else 'agent'), actor=e['actor'],
                 event_type=e['event_type'], detail=e['payload']) for e in store.audit_events(case_id)]


def pending_queue(store, case_id, artifact_root=None):
    """Every item a human still needs to act on, tagged with a queue 'section' so a
    client can render/branch consistently. Purely a read; resolving one goes through
    resolve_queue_item, which re-validates against live state regardless of what this
    snapshot showed (state can move between a GET and the following POST)."""
    items = []
    for o in _current(store, case_id, 'Question'):
        if o['status'] != 'open':continue
        items.append(dict(section='fact', id='fact:'+o['object_key'], key=o['object_key'], version=o['version'],
            who=o['payload']['owner_role_id'], text=o['payload']['question'],
            payload=dict(unit=o['payload']['unit'], denominator=o['payload']['denominator'],
                population_product_id=o['payload']['population_product_id'], snapshot_dates=o['payload']['snapshot_dates'])))
    for o in _current(store, case_id, 'Action'):
        p = o['payload']
        if o['status'] == 'draft':
            plan = store.get(case_id, 'PlanVersion', p['plan_key'])
            calc = plan['payload']['calculation'] if plan else {}
            items.append(dict(section='response', id='response:'+o['object_key'], key=o['object_key'], version=o['version'],
                who=p['accountable_role_id'], text=p['title'],
                payload=dict(steps=p['steps'], target_date=p['target_date'], regulatory_due_date=p['regulatory_due_date'],
                    regulatory_deadline_status=p['regulatory_deadline_status'], required_evidence=p['required_evidence'],
                    capacity_sufficient=calc.get('capacity_sufficient'),
                    regulatory_deadline_feasible=calc.get('regulatory_deadline_feasible'))))
            continue
        if o['status'] != 'accepted':continue
        for slot in p.get('required_evidence_ids', []):
            evidence_key = o['object_key']+'::'+slot
            e = store.get(case_id, 'Evidence', evidence_key)
            if e is None or e['status'] != 'submitted':continue
            items.append(dict(section='evidence', id='evidence:'+evidence_key, key=evidence_key, version=e['version'],
                who=e['payload']['submitted_by_role_id'], text=f"{e['payload']['title']} needs a verify/reject decision",
                payload=dict(action_key=o['object_key'], evidence_slot=slot,
                    content_assessment=e['payload'].get('content_assessment'), content_rationale=e['payload'].get('content_rationale'))))
        gate = evaluate_closure(store, case_id, o['object_key'], artifact_root)
        if gate['can_close']:
            items.append(dict(section='closure', id='closure:'+o['object_key'], key=o['object_key'], version=o['version'],
                who=p['accountable_role_id'], text=f"All required evidence verified for {p['title']}; ready to close",
                payload=dict(gate=gate)))
    return items


def resolve_queue_item(store, case_id, item_id, body, artifact_root=None):
    """Server-side re-validation happens by construction: every branch calls the
    same InvestigationTools/CaseStore method the CLI uses, which repeats every check
    (schema, status, version, role match, idempotency) regardless of what a client's
    own UI already checked -- a button cannot skip these by only changing the request."""
    if ':' not in item_id:raise ValueError('Malformed queue item id')
    section, key = item_id.split(':', 1)
    if not isinstance(body, dict):raise ValueError('Request body must be a JSON object')
    request_key = body.get('request_key')
    if section == 'fact':
        answer = {k: v for k, v in body.items() if k != 'request_key'}
        validate(answer, ANSWER_SCHEMA)
        question = store.get(case_id, 'Question', key)
        if not question:raise ValueError('Unknown question')
        result = InvestigationTools(store, case_id, 'human_input').answer_question(
            FACT_ID, answer, request_key or 'api-answer-'+digest(dict(key=key, answer=answer)), question['version'])
        return dict(kind='answer_question', result=result)
    if section == 'response':
        decision = body.get('decision', 'accept')
        if decision not in ('accept', 'reject'):raise ValueError('decision must be accept or reject')
        action = store.get(case_id, 'Action', key)
        if not action:raise ValueError('Unknown action')
        if decision == 'reject':
            role = body.get('rejected_by_role_id')
            if not role:raise ValueError('rejected_by_role_id is required')
            reason = body.get('reason')
            if not reason:raise ValueError('reason is required to reject an action')
            result = store.reject_action(case_id, key, role, reason,
                request_key or 'api-reject-'+digest(dict(key=key, role=role, reason=reason)), action['version'])
            return dict(kind='reject_action', result=result)
        role = body.get('accepted_by_role_id')
        if not role:raise ValueError('accepted_by_role_id is required')
        overrides = body.get('overrides') or {}
        if not isinstance(overrides, dict):raise ValueError('overrides must be a JSON object')
        result = store.accept_action(case_id, key, role,
            request_key or 'api-accept-'+digest(dict(key=key, role=role, overrides=overrides)), action['version'], overrides)
        return dict(kind='accept_action', result=result)
    if section == 'evidence':
        decision = body.get('decision');role = body.get('decided_by_role_id')
        if decision not in ('verified', 'rejected'):raise ValueError('decision must be verified or rejected')
        if not role:raise ValueError('decided_by_role_id is required')
        evidence = store.get(case_id, 'Evidence', key)
        if not evidence:raise ValueError('Unknown evidence')
        result = store.decide_evidence(case_id, key, decision, role, evidence['version'],
            request_key or 'api-decide-'+digest(dict(key=key, decision=decision, role=role)))
        return dict(kind='decide_evidence', result=result)
    if section == 'closure':
        role = body.get('decided_by_role_id')
        if not role:raise ValueError('decided_by_role_id is required')
        action = store.get(case_id, 'Action', key)
        if not action:raise ValueError('Unknown action')
        result = store.close_action(case_id, key, role,
            action['version'], request_key or 'api-close-'+digest(dict(key=key, role=role)), artifact_root)
        return dict(kind='close_action', result=result)
    raise ValueError(f'Unknown queue section: {section!r}')


def submit_evidence_item(store, case_id, action_key, evidence_slot, evidence_type, artifact_path, submitted_by_role_id, artifact_root):
    """Evidence submission carries a real file and so is not a queue-resolve item
    (its payload isn't the JSON {section, key, body} shape the rest of the queue uses)."""
    return _submit_evidence(store, case_id, action_key, evidence_slot, evidence_type, artifact_path, artifact_root, submitted_by_role_id)
