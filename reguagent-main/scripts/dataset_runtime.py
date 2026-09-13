#!/usr/bin/env python3
"""Deterministic fixture reader, cost calculator and evidence closure gate.

No model call, no network, no reading of evaluation labels.
"""
from __future__ import annotations

import argparse
import calendar
import copy
import csv
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from project_paths import DATASET_ROOT
from regulatory_dates import select_event

DEFAULT_ROOT = DATASET_ROOT
APPROVED_DIRS = {'01_entity','02_business','03_exposure','04_governance','05_operations',
                 '06_organisation','07_economics','08_evidence','regulatory_sources'}


def load_runtime(root=DEFAULT_ROOT, profile='assessment'):
    root=Path(root).resolve()
    manifest=json.loads((root/'dataset_manifest.json').read_text())
    files={}
    for relative in manifest['operational_files']:
        p=(root/relative).resolve()
        if not p.is_relative_to(root) or Path(relative).parts[0] not in APPROVED_DIRS:
            raise ValueError(f'Unapproved input path: {relative}')
        if p.suffix=='.json':
            files[relative]=json.loads(p.read_text())
        elif p.suffix=='.csv':
            with p.open(newline='') as f:files[relative]=list(csv.DictReader(f))
        else:raise ValueError(f'Unsupported input: {p}')
    if profile not in ['assessment','extraction','mapping']:
        raise ValueError('Unknown input profile')
    # An extraction/mapping evaluation must not read the curated output it is scored against.
    if profile=='extraction':
        files.pop('regulatory_sources/requirements.json',None)
        for p in list(files):
            if p.startswith('04_governance/'):files.pop(p)
        for c in files['regulatory_sources/change_register.json']['changes']:
            c.pop('requirement_ids',None)
    if profile=='mapping':
        remove={'requirement_ids','policy_ids','control_ids','procedure_ids','current_coverage','gap_flags',
                'extensions','missing_evidence','provenance','annotation','interpretation_notes',
                'requirement_mappings','coverage_criteria'}
        def stripped(x):
            if isinstance(x,dict):return {k:stripped(v) for k,v in x.items() if k not in remove}
            if isinstance(x,list):return [stripped(v) for v in x]
            return x
        for p in list(files):
            if p.startswith('04_governance/') or p=='regulatory_sources/requirements.json':
                files[p]=stripped(files[p])
        # Suggested options already name obligations; withhold these in blind mapping mode.
        files.pop('07_economics/response_options.json',None)
    return files


def D(value):
    return Decimal(str(value))


def money(value):
    return float(value.quantize(Decimal('0.01')))


def portfolio_metrics(files):
    loans=files['03_exposure/lending_portfolio.csv']
    sme=[r for r in loans if r['borrower_type']=='sme']
    quality={r['portfolio_record_id']:r['sector_data_quality'] for r in files['03_exposure/esg_assessment_snapshot.csv']}
    count=sum(int(r['borrower_count']) for r in sme)
    exposure=sum(D(r['outstanding_balance_eur_millions']) for r in sme)
    if not count or not exposure:raise ValueError('SME population and exposure must be positive')
    bad=[r for r in sme if quality.get(r['portfolio_record_id']) in ['missing_nace','broad_nace']]
    pmts=files['03_exposure/payments.csv']
    observed=sum(int(r['transaction_count']) for r in pmts)
    mobile=sum(int(r['transaction_count']) for r in pmts if r['initiation_channel']=='mobile_app')
    return dict(sme_borrower_count=count,sme_exposure_eur_millions=float(exposure),
        missing_or_broad_nace_borrower_pct=100*sum(int(r['borrower_count']) for r in bad)/count,
        missing_or_broad_nace_exposure_pct=float(100*sum(D(r['outstanding_balance_eur_millions']) for r in bad)/exposure),
        observed_payment_transaction_count=observed,observed_mobile_share_pct=100*mobile/observed,
        payments_population_complete=False,
        note='Observed sample share must not replace the full direct-channel 71% scenario baseline.')


def _selected_due_date(files, bank):
    events=next(c for c in files['regulatory_sources/change_register.json']['changes']
                if c['topic_key']=='esg_risk_management')['application_events']
    selected_event=select_event(events,bank)
    return selected_event['date'] if selected_event else None


def evaluate_option(files, option, *, scope_requirement_ids=None, population_count=None, budget=None):
    """Parameterized per-option evaluation -- T17: scope/workload/budget become
    explicit arguments instead of always reading the full SME population and the
    option's own template requirement_ids. calculate_options() below is now a thin
    wrapper calling this for the three fixed templates, so it stays the regression
    baseline (same numbers as before T17) rather than a second calculation path.

    scope_requirement_ids documents which requirements THIS evaluation addresses --
    defaults to the option's own declared template scope, but a caller composing a
    narrower/wider task (T15/T18) can override it; this evaluation never claims to
    cover requirements it wasn't told to. population_count overrides the full SME
    borrower count when a plan only covers part of the book (e.g. just a missing-
    NACE cohort), so a narrower scope isn't silently billed at full volume -- and,
    symmetrically, is available for a caller composing multiple non-overlapping-
    scope evaluations to sum without double-counting the whole population's cost
    into each phase (see T17's "分阶段方案重新计算，不直接叠加整套TCO").
    """
    rates={r['cost_centre_id']:D(r['unit_cost_eur']) for r in files['07_economics/operational_costs.csv']}
    hourly=rates['CC-100']/8  # eight-hour day is an explicit scenario convention in the data contract
    bank=files['01_entity/bank_profile.json']
    start=date.fromisoformat(bank['as_of_date'])
    selected_due=_selected_due_date(files,bank)
    count=portfolio_metrics(files)['sme_borrower_count'] if population_count is None else population_count
    if type(count) is not int or count<0:raise ValueError('population_count must be a non-negative integer')
    scope=list(option.get('requirement_ids',[])) if scope_requirement_ids is None else list(scope_requirement_ids)

    o=option
    if not 0 <= o['automation_rate'] <= 1:raise ValueError('Automation rate must be between 0 and 1')
    if any(D(v)<0 for v in o['effort_days_by_cost_centre'].values()):raise ValueError('Negative effort')
    people=sum(D(days)*rates[cc] for cc,days in o['effort_days_by_cost_centre'].items())
    setup=people+sum(D(o[k]) for k in ['technology_setup_eur','data_vendor_setup_eur','training_setup_eur','legal_setup_eur'])
    scenarios={}
    for band in ['low','base','high']:
        minutes=D(o['review_minutes_'+band])
        if minutes<0:raise ValueError('Negative handling time')
        annual_manual=D(count)*(1-D(o['automation_rate']))*minutes/60*hourly
        run=annual_manual+D(o['annual_fixed_run_eur'])
        scenarios[band]=dict(review_minutes=float(minutes),annual_manual_operating_cost_eur=money(annual_manual),
                             annual_run_cost_eur=money(run),three_year_tco_eur=money(setup+3*run))
    effort=sum(D(x) for x in o['effort_days_by_cost_centre'].values())
    capacity=o['delivery_team_capacity_days']
    capacity_ok=None if capacity is None else D(capacity)>=effort
    month_index=start.year*12+start.month-1+o['delivery_months']
    year,month0=divmod(month_index,12)
    projected=date(year,month0+1,min(start.day,calendar.monthrange(year,month0+1)[1]))
    setup_total_eur=money(setup)
    result=dict(option_id=o['option_id'],currency='EUR',addresses_requirement_ids=scope,
        population_count=count,population_basis='override' if population_count is not None else 'full_sme_book',
        people_setup_cost_eur=money(people),setup_total_eur=setup_total_eur,scenarios=scenarios,
        tco_horizon='one setup plus three full steady-state operating years; undiscounted, not a dated cash-flow forecast',
        delivery_months=o['delivery_months'],effort_days=float(effort),capacity_sufficient=capacity_ok,
        projected_delivery_date=projected.isoformat(),selected_regulatory_due_date=selected_due,
        regulatory_deadline_feasible=None if selected_due is None else projected<=date.fromisoformat(selected_due),
        deadline_basis='Scenario date, explicit SNCI class, sourced application events and assumed calendar delivery months; excludes unmodelled capacity delays.',
        human_review_status=o['compliance_review_status'],
        expected_risk_cost_eur=None if o['risk_probability'] is None or o['expected_loss_eur'] is None
            else money(D(o['risk_probability'])*D(o['expected_loss_eur'])),
        revenue_impact_eur=None,
        no_double_count_note='Annual manual work already enters annual run and TCO; do not add operating impact a second time.')
    if budget is not None:
        cap=budget.get('construction_budget_eur')
        if cap is not None:
            if D(cap)<0:raise ValueError('construction_budget_eur must not be negative')
            over=max(D(0),D(setup_total_eur)-D(cap))
            result.update(construction_budget_eur=cap,budget_status='within_budget' if over==0 else 'over_budget',
                over_budget_eur=money(over) if over else 0.0,
                budget_note='Checks setup_total_eur (construction) only; annual run-cost and TCO are separate figures, not part of this constraint.')
    return result


def calculate_options(files, budget=None):
    # population_count is left None so evaluate_option reports population_basis
    # 'full_sme_book' for this baseline, not 'override' (which means a caller
    # explicitly narrowed/widened scope away from the template's own population).
    result=[evaluate_option(files,o,scope_requirement_ids=o.get('requirement_ids',[]),budget=budget)
            for o in files['07_economics/response_options.json']]
    cheapest=min(result,key=lambda r:r['scenarios']['base']['three_year_tco_eur'])['option_id']
    return dict(options=result,lowest_base_tco_option_id=cheapest,recommended_option_id=None,
                recommendation_status='needs_legal_review_and_delivery_team_capacity',
                note='Lowest modelled TCO is not an approved compliance recommendation. Risk/revenue unknowns are not zero.')


def deadline_status(due,as_of):
    if due is None:return 'unknown'
    a=date.fromisoformat(as_of);d=date.fromisoformat(due)
    return 'past_due' if d<a else ('due_today' if d==a else 'future')


def closure_gate(action,evidence,root=DEFAULT_ROOT):
    """Required plans never establish collected evidence or approval."""
    reasons=[];root=Path(root).resolve();byid={e['evidence_id']:e for e in evidence}
    if action.get('human_review_status')!='approved' or not action.get('reviewed_by') or not action.get('reviewed_at'):
        reasons.append('Action lacks qualified human approval metadata.')
    if not action.get('required_evidence_ids'):reasons.append('No evidence requirements have been defined.')
    for eid in action.get('required_evidence_ids',[]):
        e=byid.get(eid)
        if not e:
            reasons.append(f'{eid}: missing evidence record');continue
        if e.get('status') not in ['collected','accepted']:
            reasons.append(f'{eid}: required/planned evidence is not collected')
        if e.get('human_review_status')!='approved' or not e.get('reviewed_by') or not e.get('reviewed_at'):
            reasons.append(f'{eid}: human review is incomplete')
        if not e.get('collected_at'):reasons.append(f'{eid}: collection timestamp missing')
        if e.get('action_id')!=action['action_id']:reasons.append(f'{eid}: evidence belongs to another action')
        path=e.get('artifact_path');digest=e.get('content_sha256')
        if not path or not digest:
            reasons.append(f'{eid}: artefact path or hash missing');continue
        p=(root/path).resolve()
        if not p.is_relative_to(root) or not p.is_file():
            reasons.append(f'{eid}: artefact absent or outside dataset root');continue
        if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            reasons.append(f'{eid}: artefact hash mismatch')
    return {'can_close':not reasons,'reasons':reasons,
            'limit':'Metadata and integrity gate only; a qualified reviewer must assess substantive evidence sufficiency.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    ap.add_argument('--output',type=Path);ap.add_argument('--export-inputs',choices=['assessment','extraction','mapping'])
    args=ap.parse_args();files=load_runtime(args.root,args.export_inputs or 'assessment')
    result=files if args.export_inputs else dict(metrics=portfolio_metrics(files),response_comparison=calculate_options(files),
        interview_questions=[r for r in files['03_exposure/missing_facts.json'] if r['value'] is None])
    s=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(s)
        print(args.output)
    else:print(s)


if __name__=='__main__':main()
