"""Append-only case objects and atomic audit events in SQLite; baseline is frozen.

Application services own writes. LLM tools never receive a DB connection or SQL.
Human approval and closure remain separate from the investigation tool permissions.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone, date
from pathlib import Path
from contextlib import contextmanager

KINDS = {'Finding','Question','GapAssessment','PlanVersion','Action','Evidence','FactPatch','Task','SourceVersion'}
STATUSES = {'draft','open','answered','running','completed','waiting','failed','stale','superseded','unverified','recorded','accepted','submitted','verified','rejected'}

def utcnow():return datetime.now(timezone.utc).isoformat()
def encode(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(encode(value).encode()).hexdigest()
def uid(prefix):return prefix+'-'+uuid.uuid4().hex


class CaseStore:
    def __init__(self, path):
        from project_paths import DATASET_ROOT, RAW_DATA_ROOT
        self.path=Path(path).resolve()
        if any(self.path.is_relative_to(root.resolve()) for root in (DATASET_ROOT, RAW_DATA_ROOT)):
            raise ValueError('Runtime database must be outside baseline and raw data')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # check_same_thread=False: this store may be constructed in one thread and
        # served from another (e.g. api_server.py's HTTPServer running in a background
        # thread). Access is always sequential, never concurrent, so this is safe --
        # it only lifts sqlite3's default same-thread guard, not SQLite's own locking.
        self.db=sqlite3.connect(self.path,timeout=10,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self._transaction_depth=0
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS cases(
          case_id TEXT PRIMARY KEY, intake_key TEXT UNIQUE, goal TEXT NOT NULL,
          mode TEXT NOT NULL CHECK(mode IN ('live','replay','test')),
          status TEXT NOT NULL, as_of_date TEXT NOT NULL, snapshot_dates_json TEXT NOT NULL,
          dataset_version TEXT NOT NULL, dataset_digest TEXT NOT NULL, inputs_json TEXT NOT NULL,
          revision INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS objects(
          object_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(case_id),
          kind TEXT NOT NULL, object_key TEXT NOT NULL, version INTEGER NOT NULL,
          status TEXT NOT NULL, payload_json TEXT NOT NULL, deps_json TEXT NOT NULL,
          input_revision INTEGER NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(case_id,kind,object_key,version));
        CREATE TABLE IF NOT EXISTS audit_events(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(case_id),
          event_type TEXT NOT NULL, actor TEXT NOT NULL, payload_json TEXT NOT NULL,
          created_at TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests(
          case_id TEXT NOT NULL REFERENCES cases(case_id), request_key TEXT NOT NULL,
          payload_hash TEXT NOT NULL, result_json TEXT NOT NULL, PRIMARY KEY(case_id,request_key));
        ''')

    def close(self):self.db.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

    @contextmanager
    def transaction(self):
        """Nested service writes can join a tool + audit + checkpoint commit."""
        depth=self._transaction_depth
        name='case_transaction_'+str(depth)
        if depth==0:
            if not self.db.in_transaction:self.db.execute('BEGIN')
        else:self.db.execute('SAVEPOINT '+name)
        self._transaction_depth+=1
        try:
            yield
        except BaseException:
            if depth==0:self.db.rollback()
            else:
                self.db.execute('ROLLBACK TO '+name)
                self.db.execute('RELEASE '+name)
            raise
        else:
            if depth==0:self.db.commit()
            else:self.db.execute('RELEASE '+name)
        finally:self._transaction_depth-=1

    def _audit(self,case_id,event_type,payload,actor='application'):
        previous=self.db.execute('SELECT event_hash FROM audit_events WHERE case_id=? ORDER BY seq DESC LIMIT 1',(case_id,)).fetchone()
        previous_hash=previous[0] if previous else ''
        now=utcnow();body=dict(case_id=case_id,event_type=event_type,actor=actor,payload=payload,created_at=now,previous_hash=previous_hash)
        self.db.execute('INSERT INTO audit_events(case_id,event_type,actor,payload_json,created_at,previous_hash,event_hash) VALUES(?,?,?,?,?,?,?)',
            (case_id,event_type,actor,encode(payload),now,previous_hash,digest(body)))

    def audit(self,case_id,event_type,payload,actor='application'):
        self.case(case_id)
        with self.transaction():self._audit(case_id,event_type,payload,actor)

    def create_case(self,goal,inputs,dataset_version,as_of_date,mode='live',intake_key=None):
        date.fromisoformat(as_of_date)
        if mode not in ('live','replay','test') or not goal.strip():raise ValueError('Invalid case mode/goal')
        frozen=encode(inputs);input_hash=digest(inputs)
        dates=sorted({r.get('snapshot_date',r.get('as_of_date','')) for r in inputs.get('03_exposure/lending_portfolio.csv',[]) }-{''})
        with self.transaction():
            if intake_key:
                existing=self.db.execute('SELECT * FROM cases WHERE intake_key=?',(intake_key,)).fetchone()
                if existing:
                    if existing['dataset_digest']!=input_hash or existing['mode']!=mode or existing['goal']!=goal or existing['as_of_date']!=as_of_date:
                        raise ValueError('Intake key already belongs to different case inputs')
                    return existing['case_id'],False
            case_id=uid('CASE');now=utcnow()
            self.db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (case_id,intake_key,goal,mode,'open',as_of_date,encode(dates),dataset_version,input_hash,frozen,0,now,now))
            self._audit(case_id,'case_created',dict(mode=mode,dataset_digest=input_hash,as_of_date=as_of_date))
        return case_id,True

    def case(self,case_id,include_inputs=False):
        row=self.db.execute('SELECT * FROM cases WHERE case_id=?',(case_id,)).fetchone()
        if row is None:raise KeyError('Unknown case')
        result=dict(row);inputs=result.pop('inputs_json')
        result['snapshot_dates']=json.loads(result.pop('snapshot_dates_json'))
        if include_inputs:result['inputs']=json.loads(inputs)
        return result

    def cases(self):
        rows=self.db.execute('SELECT case_id,goal,mode,status,as_of_date,snapshot_dates_json,dataset_version,revision,created_at,updated_at FROM cases ORDER BY updated_at DESC').fetchall()
        return [dict(r, snapshot_dates=json.loads(r['snapshot_dates_json'])) for r in rows]

    def inputs(self,case_id):
        row=self.case(case_id,True)
        if digest(row['inputs'])!=row['dataset_digest']:raise ValueError('Frozen case input hash mismatch')
        return row['inputs']

    @staticmethod
    def _object(row):
        result=dict(row);result['payload']=json.loads(result.pop('payload_json'));result['depends_on']=json.loads(result.pop('deps_json'))
        return result

    def objects(self,case_id,kind=None,current=True):
        self.case(case_id)
        sql='SELECT o.* FROM objects o WHERE o.case_id=?';args=[case_id]
        if kind:sql+=' AND o.kind=?';args.append(kind)
        if current:sql+=' AND o.version=(SELECT MAX(n.version) FROM objects n WHERE n.case_id=o.case_id AND n.kind=o.kind AND n.object_key=o.object_key)'
        return [self._object(r) for r in self.db.execute(sql+' ORDER BY o.created_at,o.object_id',args)]

    def get(self,case_id,kind,key):
        row=self.db.execute('SELECT * FROM objects WHERE case_id=? AND kind=? AND object_key=? ORDER BY version DESC LIMIT 1',(case_id,kind,key)).fetchone()
        return self._object(row) if row else None

    def _put(self,case_id,kind,key,payload,deps,status):
        if kind not in KINDS or status not in STATUSES or not isinstance(payload,dict) or not key:
            raise ValueError('Invalid object contract')
        if kind in ('Finding','GapAssessment','PlanVersion','Action','Evidence') and (
                payload.get('human_review_status')=='approved' or payload.get('review_status') in ('approved','verified') or payload.get('can_close') is True):
            raise ValueError('Investigation services cannot approve or close work')
        current=self.get(case_id,kind,key)
        version=current['version']+1 if current else 1
        revision=self.case(case_id)['revision'];object_id=uid(kind.upper())
        self.db.execute('INSERT INTO objects VALUES(?,?,?,?,?,?,?,?,?,?)',
            (object_id,case_id,kind,key,version,status,encode(payload),encode(sorted(set(deps))),revision,utcnow()))
        self._audit(case_id,'object_version',dict(object_id=object_id,kind=kind,key=key,version=version,status=status))
        return self.get(case_id,kind,key)

    def put(self,case_id,kind,key,payload,deps=(),status='draft'):
        self.case(case_id)
        with self.transaction():
            result=self._put(case_id,kind,key,payload,deps,status)
            if kind=='SourceVersion':
                self.db.execute('UPDATE cases SET revision=revision+1,updated_at=? WHERE case_id=?',(utcnow(),case_id))
                self._invalidate(case_id,{'source:'+payload.get('source_id','unknown')})
            elif kind=='Evidence':
                self.db.execute('UPDATE cases SET revision=revision+1,updated_at=? WHERE case_id=?',(utcnow(),case_id))
            return result

    def set_status(self,case_id,status,reason):
        if status not in ('open','running','waiting_for_input','investigation_complete','needs_review','failed'):
            raise ValueError('No approval/closure state is available')
        with self.transaction():
            self.case(case_id)
            self.db.execute('UPDATE cases SET status=?,updated_at=? WHERE case_id=?',(status,utcnow(),case_id))
            self._audit(case_id,'case_status',dict(status=status,reason=reason))

    def _invalidate(self,case_id,changed):
        invalidated=[];current=self.objects(case_id)
        while True:
            affected=[o for o in current if o['kind'] in ('Finding','GapAssessment','PlanVersion','Action')
                      and o['status'] not in ('stale','superseded') and o['object_id'] not in invalidated
                      and changed.intersection(o['depends_on'])]
            if not affected:break
            for record in affected:
                self._put(case_id,record['kind'],record['object_key'],record['payload'],record['depends_on'],'stale')
                invalidated.append(record['object_id']);changed.add('object:'+record['kind']+':'+record['object_key'])
        return invalidated

    def apply_answer(self,case_id,fact_id,answer,request_key,question_version):
        """Validated service input only. Patch, answer, invalidation and audit commit together."""
        if not request_key:raise ValueError('An idempotency request key is required')
        request_hash=digest(dict(fact_id=fact_id,answer=answer,question_version=question_version))
        with self.transaction():
            prior=self.db.execute('SELECT * FROM requests WHERE case_id=? AND request_key=?',(case_id,request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=request_hash:raise ValueError('Idempotency key reused with another answer')
                return json.loads(prior['result_json'])
            question=self.get(case_id,'Question',fact_id)
            if not question or question['version']!=question_version or question['status']!='open':raise ValueError('Question is not open at the submitted version')
            self.db.execute('UPDATE cases SET revision=revision+1,status=?,updated_at=? WHERE case_id=?',('open',utcnow(),case_id))
            patch=self._put(case_id,'FactPatch',fact_id,answer,['fact:'+fact_id],'recorded')
            self._put(case_id,'Question',fact_id,dict(question['payload'],answer=answer),question['depends_on'],'answered')
            invalidated=self._invalidate(case_id,{'fact:'+fact_id})
            result=dict(fact_patch_id=patch['object_id'],revision=self.case(case_id)['revision'],invalidated_object_ids=invalidated)
            self._audit(case_id,'fact_answered',dict(fact_id=fact_id,answer=answer,**result),actor='human_input' if not answer.get('synthetic') else 'replay_fixture')
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',(case_id,request_key,request_hash,encode(result)))
            return result

    def accept_action(self,case_id,action_key,accepted_by_role_id,request_key,action_version,overrides=None):
        """Human-only endpoint, mirrors apply_answer -- never exposed through
        InvestigationTools/PERMISSIONS, so no LLM role can accept its own proposal.
        overrides, if given, may only touch target_date/steps (a human tightening or
        correcting the proposal at acceptance time, a.k.a. "modify and accept") --
        it can never touch regulatory_due_date or other sourced/computed fields."""
        if not request_key:raise ValueError('An idempotency request key is required')
        overrides=overrides or {}
        if set(overrides)-{'target_date','steps'}:raise ValueError('overrides may only set target_date and/or steps')
        request_hash=digest(dict(action_key=action_key,accepted_by=accepted_by_role_id,version=action_version,overrides=overrides))
        with self.transaction():
            prior=self.db.execute('SELECT * FROM requests WHERE case_id=? AND request_key=?',(case_id,request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=request_hash:raise ValueError('Idempotency key reused with a different acceptance')
                return json.loads(prior['result_json'])
            action=self.get(case_id,'Action',action_key)
            if not action or action['version']!=action_version or action['status']!='draft':
                raise ValueError('Action is not in draft at the submitted version')
            if accepted_by_role_id!=action['payload'].get('accountable_role_id'):
                raise ValueError('Only the proposed accountable role can accept this action')
            payload=dict(action['payload'],acceptance_status='accepted',
                accepted_by_role_id=accepted_by_role_id,accepted_at=utcnow())
            if 'target_date' in overrides:
                target_date=overrides['target_date']
                date.fromisoformat(target_date)
                if date.fromisoformat(target_date)<date.fromisoformat(self.case(case_id)['as_of_date']):
                    raise ValueError('target_date is an internal remediation goal; it cannot be dated before the case as_of_date')
                from dataset_runtime import deadline_status
                payload['target_date']=target_date
                payload['internal_target_status']=deadline_status(target_date,self.case(case_id)['as_of_date'])
            if 'steps' in overrides:
                steps=overrides['steps']
                if not isinstance(steps,list) or not steps:raise ValueError('steps override must be a non-empty list')
                payload['steps']=steps
            if overrides:payload['accepted_with_overrides']=sorted(overrides)
            updated=self._put(case_id,'Action',action_key,payload,action['depends_on'],'accepted')
            self.db.execute('UPDATE cases SET revision=revision+1,updated_at=? WHERE case_id=?',(utcnow(),case_id))
            result=dict(action_id=updated['object_id'],status='accepted')
            self._audit(case_id,'action_accepted',dict(action_key=action_key,accepted_by=accepted_by_role_id,overrides=overrides),actor='human_input')
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',(case_id,request_key,request_hash,encode(result)))
            return result

    def reject_action(self,case_id,action_key,rejected_by_role_id,reason,request_key,action_version):
        """Human-only endpoint, mirrors accept_action -- never exposed through
        InvestigationTools/PERMISSIONS. A rejected action is not deleted; it stops the
        response from being accepted as-is and records why, for the audit trail."""
        if not request_key:raise ValueError('An idempotency request key is required')
        if not reason or not reason.strip():raise ValueError('A rejection reason is required')
        request_hash=digest(dict(action_key=action_key,rejected_by=rejected_by_role_id,reason=reason,version=action_version))
        with self.transaction():
            prior=self.db.execute('SELECT * FROM requests WHERE case_id=? AND request_key=?',(case_id,request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=request_hash:raise ValueError('Idempotency key reused with a different rejection')
                return json.loads(prior['result_json'])
            action=self.get(case_id,'Action',action_key)
            if not action or action['version']!=action_version or action['status']!='draft':
                raise ValueError('Action is not in draft at the submitted version')
            updated=self._put(case_id,'Action',action_key,dict(action['payload'],acceptance_status='rejected',
                rejected_by_role_id=rejected_by_role_id,rejected_at=utcnow(),rejection_reason=reason),
                action['depends_on'],'rejected')
            self.db.execute('UPDATE cases SET revision=revision+1,updated_at=? WHERE case_id=?',(utcnow(),case_id))
            invalidated=self._invalidate(case_id,{'object:Action:'+action_key})
            result=dict(action_id=updated['object_id'],status='rejected',invalidated_object_ids=invalidated)
            self._audit(case_id,'action_rejected',dict(action_key=action_key,rejected_by=rejected_by_role_id,reason=reason,**result),actor='human_input')
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',(case_id,request_key,request_hash,encode(result)))
            return result

    def decide_evidence(self,case_id,evidence_key,decision,decided_by_role_id,evidence_version,request_key):
        """Human-only endpoint, mirrors accept_action -- never exposed through
        InvestigationTools/PERMISSIONS. A rejected item is not deleted or overwritten;
        it can be resubmitted (a new Evidence version) and re-decided later."""
        if decision not in ('verified','rejected'):raise ValueError('decision must be verified or rejected')
        if not request_key:raise ValueError('An idempotency request key is required')
        request_hash=digest(dict(evidence_key=evidence_key,decision=decision,decided_by=decided_by_role_id,version=evidence_version))
        with self.transaction():
            prior=self.db.execute('SELECT * FROM requests WHERE case_id=? AND request_key=?',(case_id,request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=request_hash:raise ValueError('Idempotency key reused with a different decision')
                return json.loads(prior['result_json'])
            evidence=self.get(case_id,'Evidence',evidence_key)
            if not evidence or evidence['version']!=evidence_version or evidence['status']!='submitted':
                raise ValueError('Evidence is not submitted and pending decision at the submitted version')
            updated=self._put(case_id,'Evidence',evidence_key,dict(evidence['payload'],human_decision=decision,
                decided_by_role_id=decided_by_role_id,decided_at=utcnow()),evidence['depends_on'],decision)
            self.db.execute('UPDATE cases SET revision=revision+1,updated_at=? WHERE case_id=?',(utcnow(),case_id))
            invalidated=self._invalidate(case_id,{'object:Evidence:'+evidence_key}) if decision=='rejected' else []
            result=dict(evidence_id=updated['object_id'],status=decision,invalidated_object_ids=invalidated)
            self._audit(case_id,'evidence_decided',dict(evidence_key=evidence_key,decision=decision,
                decided_by=decided_by_role_id,**result),actor='human_input')
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',(case_id,request_key,request_hash,encode(result)))
            return result

    def close_action(self,case_id,action_key,decided_by_role_id,action_version,request_key,artifact_root=None):
        """Human-only endpoint. Refuses unless the fresh deterministic closure gate
        (dataset_runtime.closure_gate, unmodified) already reports can_close; closing
        a narrow task here is not an ESG-requirement-wide or legal compliance approval."""
        if not request_key:raise ValueError('An idempotency request key is required')
        request_hash=digest(dict(action_key=action_key,decided_by=decided_by_role_id,version=action_version))
        with self.transaction():
            prior=self.db.execute('SELECT * FROM requests WHERE case_id=? AND request_key=?',(case_id,request_key)).fetchone()
            if prior:
                if prior['payload_hash']!=request_hash:raise ValueError('Idempotency key reused with a different closure')
                return json.loads(prior['result_json'])
            action=self.get(case_id,'Action',action_key)
            if not action or action['version']!=action_version or action['status']!='accepted':
                raise ValueError('Action must be an accepted action at the submitted version')
            from evidence_intake import evaluate_closure
            gate=evaluate_closure(self,case_id,action_key,artifact_root)
            if not gate['can_close']:raise ValueError('Evidence gate is not satisfied: '+'; '.join(gate['reasons']))
            evidence_deps={'object:Evidence:'+action_key+'::'+slot for slot in action['payload'].get('required_evidence_ids',[])}
            updated=self._put(case_id,'Action',action_key,dict(action['payload'],closure_status='verified',
                closed_by_role_id=decided_by_role_id,closed_at=utcnow(),closure_gate=gate,
                closure_scope_note='Closes only this narrow task; not an approval of the full ESG requirement or legal compliance.'),
                sorted(set(action['depends_on'])|evidence_deps),'verified')
            self.db.execute('UPDATE cases SET revision=revision+1,updated_at=? WHERE case_id=?',(utcnow(),case_id))
            result=dict(action_id=updated['object_id'],status='verified')
            self._audit(case_id,'action_closed',dict(action_key=action_key,closed_by=decided_by_role_id),actor='human_input')
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',(case_id,request_key,request_hash,encode(result)))
            return result

    def audit_events(self,case_id):
        return [dict(r, payload=json.loads(r['payload_json'])) for r in self.db.execute('SELECT * FROM audit_events WHERE case_id=? ORDER BY seq',(case_id,))]

    def verify_audit(self,case_id):
        previous=''
        for row in self.audit_events(case_id):
            body={k:row[k] for k in ('case_id','event_type','actor','payload','created_at','previous_hash')}
            if row['previous_hash']!=previous or digest(body)!=row['event_hash']:return False
            previous=row['event_hash']
        return True
