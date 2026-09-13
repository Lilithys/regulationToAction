#!/usr/bin/env python3
"""Compressed SME ESG demo: one reviewed request, deterministic Part B/C, one optional LLM interpretation.

Writes the normal CaseStore objects so view_adapter.py and api_server.py expose the
same frontend API as the multi-agent runner. It intentionally does not invoke the
Coordinator or tool loop.
"""
from __future__ import annotations
import argparse,json,os,sys
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent));sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from case_store import CaseStore
from source_intake import open_reviewed_request_case
from exposure_esg import portfolio_fact_report
from dataset_runtime import evaluate_option
from project_paths import PROJECT_ROOT,RUNS_ROOT

REQ='REQ-ESG-CREDIT-MONITORING-001';PRODUCT='PRD-SME-WORKING-CAPITAL';CONTROL='CTRL-ESG-ONBOARD-SCREEN'

def _llm_text(mode, requirement, control, process, part_b, max_output_tokens):
    if mode=='replay':
        return ('The supplied control is performed per new credit application and its stated coverage excludes the existing portfolio. '
                'It therefore does not evidence recurring ESG monitoring for Northstar\'s existing SME book. The 65% attributed energy-data coverage also leaves 3,500 borrowers unresolved.')
    from llm import complete
    prompt=json.dumps(dict(requirement=requirement['requirement_text'],part_b=part_b,
        control=dict(title=control['title'],objective=control['objective'],frequency=control['frequency'],coverage=control['coverage']),
        process=dict(name=process['name'],current_state_as_documented=process['current_state_as_documented'])),ensure_ascii=False)
    return complete('You are the Bank Investigator. Return exactly 2 concise sentences in English, even if the supplied material is in another language. Assess only whether the supplied control evidences recurring ESG monitoring for the existing SME lending book. Cite the supplied control frequency/coverage and Part B facts. Do not make a legal approval.',prompt,max_tokens=max_output_tokens)

def run(store, request_file, mode='replay', answer_file=PROJECT_ROOT/'materials/esg_demo/energy_answer.synthetic.json', max_output_tokens=1600, model=None):
    if model:os.environ['LLM_MODEL']=model
    case_id,_=open_reviewed_request_case(store,request_file,'replay' if mode=='replay' else 'live',nonce='compressed-demo')
    files=store.inputs(case_id);requirement=files['regulatory_sources/requirements.json']['requirements'][0]
    answer=json.loads(Path(answer_file).read_text());report=portfolio_fact_report(files,[PRODUCT],date.fromisoformat(store.case(case_id)['as_of_date']))
    part_b=dict(exposure_eur_millions=report['exposure_eur_millions'],borrower_count=report['borrower_count'],
        energy_coverage_pct=answer['value'],covered_borrowers=answer['numerator'],missing_borrowers=answer['denominator']-answer['numerator'],
        source='attributed synthetic owner answer; not operating evidence')
    controls=files['04_governance/controls.json']['controls'];control=next(c for c in controls if c['control_id']==CONTROL)
    process=next(p for p in files['05_operations/processes.json']['processes'] if p['process_id']=='PROC-CREDIT-RISK-MONITORING')
    interpretation=_llm_text(mode,requirement,control,process,part_b,max_output_tokens)
    store.put(case_id,'Finding','part-b-exposure',dict(summary=f"Existing SME lending: EUR {part_b['exposure_eur_millions']}m across {part_b['borrower_count']} borrowers; energy data coverage {part_b['energy_coverage_pct']}% ({part_b['missing_borrowers']} unresolved).",category='data_quality',reference_ids=['CALC-PORTFOLIO-COMPRESSED','CALC-ENERGY-COMPRESSED'],review_status='provisional',author_role='bank_investigator',part_b=part_b),['file:03_exposure/lending_portfolio.csv','fact:FACT-ESG-ENERGY-COVERAGE'],'draft')
    store.put(case_id,'GapAssessment',REQ+'::'+CONTROL,dict(requirement_id=REQ,candidate_control_id=CONTROL,mapping_support='related_not_supporting',design_coverage='partial',operating_evidence='unverified',review_status='provisional',rationale=interpretation,author_role='bank_investigator'),['file:regulatory_sources/requirements.json','file:04_governance/controls.json','file:05_operations/processes.json'],'draft')
    store.put(case_id,'Finding','part-c-monitoring-gap',dict(summary=interpretation,category='control_gap',reference_ids=['CTRL-ESG-ONBOARD-SCREEN','PROC-CREDIT-RISK-MONITORING','CALC-ENERGY-COMPRESSED'],review_status='provisional',author_role='bank_investigator'),['file:04_governance/controls.json','file:05_operations/processes.json','fact:FACT-ESG-ENERGY-COVERAGE'],'draft')
    option=next(o for o in files['07_economics/response_options.json'] if o['option_id']=='OPT-ESG-AUTOMATED')
    calculation=evaluate_option(files,option,scope_requirement_ids=[REQ],population_count=part_b['missing_borrowers'])
    plan=store.put(case_id,'PlanVersion','compressed-esg-plan',dict(option_id=option['option_id'],addresses_requirement_ids=[REQ],deferred_requirement_ids=[],calculation=calculation,review_status='provisional',recommendation_status='needs_human_review',rationale='Deterministic demo plan: data remediation enables recurring monitoring; cost remains an unapproved estimate.',author_role='response_planner'),['object:Finding:part-b-exposure','object:Finding:part-c-monitoring-gap','file:07_economics/response_options.json'],'draft')
    store.put(case_id,'Action','compressed-esg-data-remediation',dict(plan_key=plan['object_key'],title='Remediate SME ESG data for recurring monitoring',steps='Collect missing SME energy/ESG data; validate coverage; then enable recurring portfolio monitoring.',accountable_role_id='ROLE-CHIEF-RISK',target_date=calculation['projected_delivery_date'],internal_target_status='planned',regulatory_due_date=calculation.get('selected_regulatory_due_date'),regulatory_deadline_status='overdue_or_due',priority_score=100.0,priority_band='P1',dependency_note='Enables methodology calibration and recurring monitoring control.',required_evidence=[dict(evidence_key='design',evidence_type='control_design',title='Data remediation control design'),dict(evidence_key='test',evidence_type='control_effectiveness_test',title='Coverage validation test')],required_evidence_ids=['design','test'],acceptance_status='proposed',review_status='provisional',author_role='response_planner'),['object:PlanVersion:'+plan['object_key'],'object:Finding:part-c-monitoring-gap'],'draft')
    store.set_status(case_id,'needs_review','Compressed demo prepared; human review/acceptance remains required.')
    return case_id

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=RUNS_ROOT/'compressed_demo.sqlite3');p.add_argument('--mode',choices=['live','replay'],default='replay');p.add_argument('--request-file',type=Path,default=PROJECT_ROOT/'materials/esg_demo/request_regulation.json');p.add_argument('--answer-file',type=Path,default=PROJECT_ROOT/'materials/esg_demo/energy_answer.synthetic.json');p.add_argument('--max-output-tokens',type=int,default=1600);p.add_argument('--model',default='gpt-5-mini',help='OpenAI model for this compressed demo only; default gpt-5-mini.');a=p.parse_args()
    if a.max_output_tokens<512:raise SystemExit('--max-output-tokens must be at least 512')
    with CaseStore(a.db) as store:case_id=run(store,a.request_file,a.mode,a.answer_file,a.max_output_tokens,a.model if a.mode=='live' else None)
    print(json.dumps(dict(case_id=case_id,mode=a.mode,model=a.model if a.mode=='live' else None,status='needs_review'),indent=2))
if __name__=='__main__':main()
