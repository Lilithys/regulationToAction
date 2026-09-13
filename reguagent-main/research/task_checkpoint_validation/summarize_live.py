"""Read-only audit export for this bounded live validation; no provider/config access."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

FOLDER=Path(__file__).resolve().parent
ROOT=FOLDER.parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def summarize():
    boundary=json.loads((FOLDER/'live_boundary.json').read_text())
    cid=boundary['case_id']
    db=sqlite3.connect((ROOT/'runs/esg_live.sqlite3').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:
        case=dict(db.execute('SELECT case_id,status,revision FROM cases WHERE case_id=?',(cid,)).fetchone())
        events=[];previous='';valid=True
        for row in db.execute('SELECT * FROM audit_events WHERE case_id=? ORDER BY seq',(cid,)):
            event=dict(row);event['payload']=json.loads(event.pop('payload_json'))
            body={k:event[k] for k in ('case_id','event_type','actor','payload','created_at','previous_hash')}
            valid=valid and event['previous_hash']==previous and digest(body)==event['event_hash']
            previous=event['event_hash'];events.append(event)
        fresh=[e for e in events if e['seq']>boundary['start_audit_seq']]
        def of(kind):return [e for e in fresh if e['event_type']==kind]
        objects=[]
        for row in db.execute('SELECT o.* FROM objects o WHERE o.case_id=? AND o.version=(SELECT MAX(n.version) FROM objects n WHERE n.case_id=o.case_id AND n.kind=o.kind AND n.object_key=o.object_key)',(cid,)):
            obj=dict(row);obj['payload']=json.loads(obj.pop('payload_json'));objects.append(obj)
        tasks=[];checkpoint_refs={}
        for obj in objects:
            if obj['kind']!='Task' or not obj['payload'].get('checkpoint'):continue
            payload=obj['payload'];checkpoint=payload['checkpoint'];state=checkpoint['state']
            binding=next((e['payload'] for e in reversed(events) if e['event_type']=='checkpoint_saved'
                and e['payload'].get('task_id')==obj['object_key'] and e['payload'].get('version')==obj['version']),{})
            integrity=valid and digest(checkpoint)==payload['checkpoint_hash']==binding.get('checkpoint_hash')
            tasks.append(dict(task_id=obj['object_key'],role=payload['role'],status=obj['status'],
                turns=state['turns'],observations=len(state['observed']),pending=state['pending'] is not None,
                task=payload['task'],checkpoint_integrity_valid=integrity))
            checkpoint_refs[obj['object_key']]=set(state['observed'])
        tool_results=[dict(e['payload'],seq=e['seq']) for e in of('tool_result')]
        signatures=Counter((p.get('task_id'),p['tool'],json.dumps(p['arguments'],sort_keys=True)) for p in tool_results)
        duplicate=[dict(task_id=t,tool=n,arguments=json.loads(a),count=count)
            for (t,n,a),count in signatures.items() if count>1]
        findings=[]
        for p in tool_results:
            if p['tool']!='record_finding' or p['is_error']:continue
            obj=p['output'];payload=obj['payload']
            findings.append(dict(key=obj['object_key'],version=obj['version'],role=p['role'],
                **payload,references_in_task_checkpoint=all(r in checkpoint_refs.get(p['task_id'],set()) for r in payload['reference_ids'])))
        runs=[e['payload'] for e in of('run_finished')]
        requests=of('model_request');responses=of('model_response');errors=of('model_error');waits=of('request_wait')
        summary=dict(case=case,audit_chain_valid=valid,last_audit_seq=events[-1]['seq'],
            new_audit_events=len(fresh),new_api_requests=len(requests),successful_model_responses=len(responses),
            provider_reported_tokens=sum(e['payload']['tokens'] for e in responses),
            elapsed_run_seconds=round(sum(r['budget']['elapsed_seconds'] for r in runs),3),
            authorized_budget=dict(api_attempts=12,seconds=480),runs=runs,
            provider_errors=[e['payload'] for e in errors],
            waits_by_reason=dict(Counter(e['payload']['reason'] for e in waits)),
            requested_wait_seconds=round(sum(e['payload']['seconds'] for e in waits),3),
            completed_tool_counts=dict(Counter(p['tool'] for p in tool_results)),
            tool_errors=[dict(tool=p['tool'],output=p['output']) for p in tool_results if p['is_error']],
            repeated_identical_tools=duplicate,task_resumes=[e['payload'] for e in of('task_resumed')],
            current_tasks=tasks,findings=findings,object_counts=dict(Counter(o['kind'] for o in objects)))
        (FOLDER/'live_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        (FOLDER/'live_tool_results.json').write_text(json.dumps(tool_results,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('findings','current_tasks','runs')},ensure_ascii=False,indent=2))
    finally:db.close()


if __name__=='__main__':summarize()
