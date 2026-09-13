"""Version-bound durable tool progress, not private model reasoning."""
import copy
from case_store import digest,encode

PROTOCOL='task-checkpoint-v1'


class TaskCheckpoint:
    def __init__(self,store,case_id,identity,payload,service,cached=None):
        self.store=store;self.case_id=case_id;self.identity=identity
        self.payload=payload;self.service=service
        self.state=dict(messages=[dict(role='user',content=encode(dict(task=payload['task'],case_id=case_id,
            case_revision=payload['case_revision'],instruction='Inspect current context only when needed. Use tools to produce a bounded, persisted result. Return through finish.')))],
            turns=0,pending=None,repeated={},no_tool_turns=0,completion=None,produced_ids=[],observed={},fact_lookups=[])
        self.restored=False
        if cached and cached['payload'].get('checkpoint'):
            checkpoint=cached['payload']['checkpoint']
            expected=cached['payload'].get('checkpoint_hash')
            events=store.audit_events(case_id)
            bound=next((e['payload'] for e in reversed(events) if e['event_type']=='checkpoint_saved'
                        and e['payload'].get('task_id')==identity and e['payload'].get('version')==cached['version']),None)
            if not store.verify_audit(case_id) or digest(checkpoint)!=expected or not bound or bound.get('checkpoint_hash')!=expected:
                raise ValueError('Task checkpoint integrity check failed')
            if checkpoint['protocol']!=PROTOCOL or checkpoint['case_revision']!=payload['case_revision'] or checkpoint['input_digest']!=store.case(case_id)['dataset_digest']:
                raise ValueError('Task checkpoint input version does not match')
            self.state=copy.deepcopy(checkpoint['state']);self.restored=True
            service.observed=copy.deepcopy(self.state['observed'])
            service.fact_lookups=set(self.state['fact_lookups'])

    def save(self,status='running',**extra):
        self.state['observed']=copy.deepcopy(self.service.observed)
        self.state['fact_lookups']=sorted(self.service.fact_lookups)
        checkpoint=dict(protocol=PROTOCOL,case_revision=self.payload['case_revision'],
            input_digest=self.store.case(self.case_id)['dataset_digest'],state=copy.deepcopy(self.state))
        checksum=digest(checkpoint)
        with self.store.transaction():
            row=self.store.put(self.case_id,'Task',self.identity,dict(self.payload,
                checkpoint=checkpoint,checkpoint_hash=checksum,**extra),status=status)
            self.store.audit(self.case_id,'checkpoint_saved',dict(task_id=self.identity,version=row['version'],
                checkpoint_hash=checksum,turns=self.state['turns'],pending=bool(self.state['pending'])),actor=self.payload['role'])
        return row
