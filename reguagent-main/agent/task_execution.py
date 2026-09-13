"""Resumable execution of one bounded role task and its chosen delegations."""
import copy
import time
from case_store import digest,encode
from investigation_tools import InvestigationTools,tool_definitions,PERMISSIONS,SCHEMAS
from roles import system_prompt
from task_checkpoint import TaskCheckpoint,PROTOCOL
from tool_contracts import validate


def execute_task(runner,role,task,task_key,depth=0):
    from tool_runtime import BudgetExceeded
    store=runner.store;case_id=runner.case_id
    revision=store.case(case_id)['revision']
    definitions=tool_definitions(role)
    contract=digest(dict(protocol=PROTOCOL,prompt=system_prompt(role),tools=definitions))
    identity=digest(dict(role=role,task=task,key=task_key,revision=revision,contract=contract))
    if identity in runner.active_tasks:raise ValueError('Duplicate active task')
    runner.active_tasks.add(identity)
    checkpoint=None
    try:
        service=InvestigationTools(store,case_id,role)
        payload=dict(role=role,task=task,task_key=task_key,run_id=runner.run_id,
            case_revision=revision,runtime_contract=contract)
        cached=store.get(case_id,'Task',identity)
        checkpoint=TaskCheckpoint(store,case_id,identity,payload,service,cached)
        state=checkpoint.state
        if checkpoint.restored:
            store.audit(case_id,'task_resumed',dict(task_id=identity,role=role,turns=state['turns'],
                pending=bool(state['pending']),observation_count=len(service.observed)),actor=role)
            if runner.client.mode=='replay' and hasattr(runner.client,'restore_observations'):
                runner.client.restore_observations(state['messages'])
        if state['completion'] and state['pending'] is None:
            status='completed' if state['completion']['status']=='completed' else 'waiting'
            checkpoint.save(status,result=state['completion'])
            return dict(state['completion'],reused=True)
        checkpoint.save()
        while True:
            if state['pending'] is None:
                if state['turns']>=12:raise BudgetExceeded('Specialist turn limit exhausted; split or revise this task')
                response=runner._invoke(role,state['messages'],definitions,
                    task_progress=dict(turns=state['turns'],persisted_deliverables=len(state['produced_ids'])))
                state['turns']+=1
                content=response.get('content')
                if not isinstance(content,list):raise ValueError('Malformed model content')
                if response.get('stop_reason') in ('refusal','max_tokens'):
                    raise ValueError('Model refused or truncated this task; state is retained')
                calls=[b for b in content if isinstance(b,dict) and b.get('type')=='tool_use']
                if not calls:
                    state['no_tool_turns']+=1
                    if state['no_tool_turns']>1:raise ValueError('No structured tool call after correction')
                    state['messages'].append(dict(role='assistant',content=content or 'No tool result supplied.'))
                    state['messages'].append(dict(role='user',content='Use an available tool or finish with a structured status.'))
                    checkpoint.save();continue
                ids=[b.get('id') for b in calls]
                if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
                    raise ValueError('Malformed/duplicate tool-use IDs')
                state['messages'].append(dict(role='assistant',content=content))
                state['pending']=dict(calls=calls,cursor=0,results=[])
                checkpoint.save()

            pending=state['pending']
            while pending['cursor']<len(pending['calls']):
                runner.budget.tool()
                call=pending['calls'][pending['cursor']]
                name=call.get('name');arguments=call.get('input');error=False
                started=time.monotonic()
                state_before=copy.deepcopy(state)
                observed_before=copy.deepcopy(service.observed);lookups_before=set(service.fact_lookups)
                try:
                    # No SQLite transaction is held during a model call or wait.
                    # Children commit independently; a cached completed child can
                    # be reused if the parent is interrupted before recording it.
                    try:
                        if state['completion']:raise ValueError('No tools may execute after finish in the same response')
                        progress=digest([(o['object_id'],o['status']) for o in store.objects(case_id) if o['kind']!='Task'])
                        signature=digest(dict(tool=name,arguments=arguments,progress=progress))
                        state['repeated'][signature]=state['repeated'].get(signature,0)+1
                        if state['repeated'][signature]>2:raise BudgetExceeded('Repeated identical tool request without progress')
                        if name not in PERMISSIONS[role]:raise PermissionError('Tool is not permitted for this role; delegate domain investigation to a specialist')
                        validate(arguments,SCHEMAS[name])
                        if name=='delegate':
                            if depth!=0:raise PermissionError('Specialists cannot delegate')
                            runner.budget.delegate()
                            output=runner._task(arguments['role'],arguments['task'],arguments['task_key'],depth+1)
                        else:output=None
                    except BudgetExceeded:raise
                    except (ValueError,KeyError,PermissionError,TypeError) as exc:
                        error=True;output=dict(status='tool_error',error_type=type(exc).__name__,message=str(exc)[:600])

                    with store.transaction():
                        if not error and name!='delegate':
                            try:
                                with store.transaction():
                                    if name=='finish':
                                        if arguments['status']=='completed':
                                            if role=='coordinator':
                                                if any(q['status']=='open' for q in store.objects(case_id,'Question')):
                                                    raise ValueError('Open questions remain: finish waiting or continue independent work')
                                                if any(o['status']=='stale' for o in store.objects(case_id) if o['kind'] in ('Finding','GapAssessment')):
                                                    raise ValueError('Affected findings are stale; recompute or return needs_review')
                                                if not any(o['kind'] in ('Finding','GapAssessment') for o in store.objects(case_id)):
                                                    raise ValueError('No investigation findings exist; delegate a concrete investigation or return needs_review')
                                            elif not state['produced_ids']:
                                                raise ValueError('Persist a supported deliverable before completing this specialist task, or return needs_review')
                                        state['completion']=dict(arguments,role=role,review_status='provisional')
                                        output=state['completion']
                                    else:output=getattr(service,name)(**arguments)
                            except (ValueError,KeyError,PermissionError,TypeError) as exc:
                                error=True;output=dict(status='tool_error',error_type=type(exc).__name__,message=str(exc)[:600])
                        encoded=encode(output)
                        if len(encoded)>42000:
                            output=dict(status='result_too_large',message='Narrow the search or read individual record IDs.',
                                record_ids=[r.get('record_id') for r in output.get('results',[])],truncated=True)
                            encoded=encode(output)
                        if not error and isinstance(output,dict) and output.get('object_id') and output.get('kind') in (
                                'Finding','Question','GapAssessment','PlanVersion','Action','Evidence'):
                            state['produced_ids'].append(output['object_id'])
                        store.audit(case_id,'tool_result',dict(role=role,task_id=identity,tool_call_id=call['id'],
                            tool=name,arguments=arguments,output=output,is_error=error,
                            elapsed_seconds=round(time.monotonic()-started,3)),actor=role)
                        pending['results'].append(dict(type='tool_result',tool_use_id=call['id'],content=encoded,is_error=error))
                        pending['cursor']+=1
                        checkpoint.save()
                except BaseException:
                    state.clear();state.update(state_before)
                    service.observed=observed_before;service.fact_lookups=lookups_before
                    raise
            state['messages'].append(dict(role='user',content=copy.deepcopy(pending['results'])))
            state['pending']=None
            if state['completion']:
                status='completed' if state['completion']['status']=='completed' else 'waiting'
                checkpoint.save(status,result=state['completion'])
                return state['completion']
            checkpoint.save()
    except Exception as exc:
        if checkpoint is not None:
            try:checkpoint.save('failed',error_type=type(exc).__name__)
            except Exception:pass  # The previous committed checkpoint remains.
        raise
    finally:runner.active_tasks.discard(identity)
