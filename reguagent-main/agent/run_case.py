#!/usr/bin/env python3
"""Persisted investigation CLI. Live mode calls the configured model; replay is explicit."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from project_paths import RUNS_ROOT,PROJECT_ROOT
from case_store import CaseStore,digest,uid
from source_intake import open_registered_case,register_local_snapshot
from investigation_tools import InvestigationTools,FACT_ID
from tool_runtime import ToolRunner,RunBudget
from replay_client import ReplayClient
import evidence_intake

GOAL='Investigate the SME ESG credit-monitoring change, source limitations, governance gaps and missing energy-data facts. Compare conditional economics when useful; resume affected findings after an owner answer. No final legal approval or action closure.'


def client_for(mode):
    if mode=='replay':return ReplayClient()
    if mode=='live':
        from llm import live_client
        return live_client()
    raise ValueError('Test cases cannot run through the public CLI')


def run(store,case_id,budget=None):return ToolRunner(store,case_id,client_for(store.case(case_id)['mode']),budget).run()


def view(store,case_id,include_audit=False):
    result=dict(case=store.case(case_id),objects=store.objects(case_id),audit_chain_valid=store.verify_audit(case_id))
    if include_audit:result['audit_events']=store.audit_events(case_id)
    return result


def answer(store,case_id,path,request_key=None,question_version=1):
    payload=json.loads(Path(path).read_text())
    return InvestigationTools(store,case_id,'human_input').answer_question(FACT_ID,payload,
        request_key or 'answer-'+digest(payload),question_version)


def accept(store,case_id,action_key,accepted_by_role_id,action_version,request_key=None):
    """Human-only; deliberately not reachable through InvestigationTools/PERMISSIONS."""
    return store.accept_action(case_id,action_key,accepted_by_role_id,
        request_key or 'accept-'+digest(dict(action_key=action_key,role=accepted_by_role_id,version=action_version)),action_version)


def evidence_artifact_root(store):return store.path.parent/'evidence_artifacts'


def submit_evidence(store,case_id,action_key,evidence_slot,evidence_type,artifact,submitted_by_role_id):
    """Local CLI/service only, mirrors import-source; not an LLM tool."""
    return evidence_intake.submit_evidence(store,case_id,action_key,evidence_slot,evidence_type,artifact,
        evidence_artifact_root(store),submitted_by_role_id)


def decide_evidence(store,case_id,evidence_key,decision,decided_by_role_id,evidence_version,request_key=None):
    """Human-only; deliberately not reachable through InvestigationTools/PERMISSIONS."""
    return store.decide_evidence(case_id,evidence_key,decision,decided_by_role_id,evidence_version,
        request_key or 'decide-'+digest(dict(evidence_key=evidence_key,decision=decision,role=decided_by_role_id,version=evidence_version)))


def close_action(store,case_id,action_key,decided_by_role_id,action_version,request_key=None):
    """Human-only; deliberately not reachable through InvestigationTools/PERMISSIONS. Refuses
    unless the fresh deterministic evidence gate already reports can_close."""
    return store.close_action(case_id,action_key,decided_by_role_id,action_version,
        request_key or 'close-'+digest(dict(action_key=action_key,role=decided_by_role_id,version=action_version)),
        evidence_artifact_root(store))


def demo_replay(store,answer_fixture=None):
    case_id,_=open_registered_case(store,GOAL,'replay',nonce=uid('DEMO'))
    before=run(store,case_id)
    result=dict(case_id=case_id,mode='explicit_scripted_replay',before_answer=before)
    if answer_fixture and before['outcome']['status']=='waiting':
        result['answer_result']=answer(store,case_id,answer_fixture)
        result['after_answer']=run(store,case_id)
        result['energy_coverage']=InvestigationTools(store,case_id,'bank_investigator').energy_coverage()
        actions=store.objects(case_id,'Action')
        if actions:
            action=actions[0];action_key=action['object_key'];role=action['payload']['accountable_role_id']
            demo=PROJECT_ROOT/'materials/esg_demo'
            result['accept_result']=accept(store,case_id,action_key,role,action['version'])

            submit_evidence(store,case_id,action_key,'design','control_design',demo/'unrelated_policy.synthetic.txt',role)
            result['evidence_review_bad_design']=run(store,case_id)
            design=store.get(case_id,'Evidence',action_key+'::design')
            result['reject_bad_design']=decide_evidence(store,case_id,action_key+'::design','rejected',role,design['version'])

            submit_evidence(store,case_id,action_key,'design','control_design',demo/'control_design.synthetic.txt',role)
            result['evidence_review_good_design']=run(store,case_id)
            design=store.get(case_id,'Evidence',action_key+'::design')
            result['verify_good_design']=decide_evidence(store,case_id,action_key+'::design','verified',role,design['version'])

            submit_evidence(store,case_id,action_key,'test','control_effectiveness_test',demo/'control_effectiveness_test.synthetic.txt',role)
            result['evidence_review_test']=run(store,case_id)
            test=store.get(case_id,'Evidence',action_key+'::test')
            result['verify_test']=decide_evidence(store,case_id,action_key+'::test','verified',role,test['version'])

            result['closure_check']=InvestigationTools(store,case_id,'coordinator').check_closure(action_key)
            action=store.get(case_id,'Action',action_key)
            result['close_result']=close_action(store,case_id,action_key,role,action['version'])
    result['case_status']=store.case(case_id)['status']
    result['audit_chain_valid']=store.verify_audit(case_id)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=RUNS_ROOT/'cases.sqlite3')
    parser.add_argument('--max-request-tokens',type=int,default=16000,help='Local estimated input + output cap; not a provider limit')
    parser.add_argument('--max-output-tokens',type=int,default=2400)
    parser.add_argument('--max-model-calls',type=int,default=36)
    parser.add_argument('--max-seconds',type=float,default=180)
    parser.add_argument('--min-request-interval',type=float,default=0,help='Seconds between live request starts across all roles')
    parser.add_argument('--tokens-per-minute',type=int,default=0,help='Conservative 60-second request reservations for this case; 0 disables local TPM pacing')
    sub=parser.add_subparsers(dest='command',required=True)
    start=sub.add_parser('start');start.add_argument('--mode',choices=['live','replay'],default='live')
    start.add_argument('--goal',default=GOAL);start.add_argument('--new',action='store_true')
    resume=sub.add_parser('resume');resume.add_argument('case_id')
    show=sub.add_parser('show');show.add_argument('case_id');show.add_argument('--audit',action='store_true')
    respond=sub.add_parser('answer');respond.add_argument('case_id');respond.add_argument('--file',type=Path,required=True)
    respond.add_argument('--request-key');respond.add_argument('--question-version',type=int,default=1)
    accept_cmd=sub.add_parser('accept');accept_cmd.add_argument('case_id');accept_cmd.add_argument('--action-key',required=True)
    accept_cmd.add_argument('--role',required=True,help='accepted_by_role_id; must match the action\'s own proposed accountable_role_id')
    accept_cmd.add_argument('--action-version',type=int,required=True);accept_cmd.add_argument('--request-key')
    submit_cmd=sub.add_parser('submit-evidence');submit_cmd.add_argument('case_id');submit_cmd.add_argument('--action-key',required=True)
    submit_cmd.add_argument('--evidence-slot',required=True,help="short id from the action's own required_evidence, e.g. 'design'")
    submit_cmd.add_argument('--evidence-type',required=True);submit_cmd.add_argument('--file',type=Path,required=True)
    submit_cmd.add_argument('--role',required=True,help='submitted_by_role_id')
    decide_cmd=sub.add_parser('decide-evidence');decide_cmd.add_argument('case_id');decide_cmd.add_argument('--evidence-key',required=True)
    decide_cmd.add_argument('--decision',choices=['verified','rejected'],required=True)
    decide_cmd.add_argument('--role',required=True,help='decided_by_role_id')
    decide_cmd.add_argument('--evidence-version',type=int,required=True);decide_cmd.add_argument('--request-key')
    close_cmd=sub.add_parser('close-action');close_cmd.add_argument('case_id');close_cmd.add_argument('--action-key',required=True)
    close_cmd.add_argument('--role',required=True,help='decided_by_role_id');close_cmd.add_argument('--action-version',type=int,required=True)
    close_cmd.add_argument('--request-key')
    demo=sub.add_parser('demo-replay');demo.add_argument('--answer-fixture',type=Path)
    source=sub.add_parser('import-source');source.add_argument('case_id');source.add_argument('--identifier',required=True);source.add_argument('--file',type=Path,required=True)
    args=parser.parse_args()
    budget=RunBudget(max_request_tokens=args.max_request_tokens,max_output_tokens=args.max_output_tokens,
        max_model_calls=args.max_model_calls,max_seconds=args.max_seconds,min_request_interval=args.min_request_interval,
        tokens_per_minute=args.tokens_per_minute)
    with CaseStore(args.db) as store:
        if args.command=='start':
            case_id,created=open_registered_case(store,args.goal,args.mode,nonce=uid('CASE') if args.new else None)
            result=dict(created=created,**run(store,case_id,budget))
        elif args.command=='resume':result=run(store,args.case_id,budget)
        elif args.command=='show':result=view(store,args.case_id,args.audit)
        elif args.command=='answer':result=answer(store,args.case_id,args.file,args.request_key,args.question_version)
        elif args.command=='accept':result=accept(store,args.case_id,args.action_key,args.role,args.action_version,args.request_key)
        elif args.command=='submit-evidence':result=submit_evidence(store,args.case_id,args.action_key,args.evidence_slot,args.evidence_type,args.file,args.role)
        elif args.command=='decide-evidence':result=decide_evidence(store,args.case_id,args.evidence_key,args.decision,args.role,args.evidence_version,args.request_key)
        elif args.command=='close-action':result=close_action(store,args.case_id,args.action_key,args.role,args.action_version,args.request_key)
        elif args.command=='import-source':result=register_local_snapshot(store,args.case_id,args.identifier,args.file,store.path.parent/'source_artifacts')
        else:result=demo_replay(store,args.answer_fixture)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result.get('outcome',{}).get('status')=='failed' or result.get('case_status')=='failed':return 1
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,KeyError) as exc:
        print(json.dumps(dict(status='input_error',message=str(exc)),ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)
