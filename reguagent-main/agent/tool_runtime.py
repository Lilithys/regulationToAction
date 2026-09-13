"""Budgeted role-specific tool loop. Shared budget bounds nested specialist work."""
from __future__ import annotations
import time
import random
import math
from dataclasses import dataclass,field
from datetime import datetime
from case_store import uid,encode
from roles import system_prompt
from request_controls import bounded_messages,error_diagnostic,RequestTooLarge,TokenWindow


class BudgetExceeded(RuntimeError):pass

@dataclass
class RunBudget:
    max_model_calls:int=36
    max_tool_calls:int=70
    max_delegations:int=5
    max_tokens:int=160000
    max_seconds:float=180
    max_request_tokens:int=16000
    max_output_tokens:int=2400
    min_request_interval:float=0
    tokens_per_minute:int=0
    model_calls:int=0
    tool_calls:int=0
    delegations:int=0
    tokens:int=0
    started:float=field(default_factory=time.monotonic)

    def __post_init__(self):
        for name in ('max_model_calls','max_tool_calls','max_delegations','max_tokens','max_request_tokens','max_output_tokens'):
            if type(getattr(self,name)) is not int or getattr(self,name)<=0:raise ValueError(name+' must be a positive integer')
        if self.max_request_tokens-self.max_output_tokens<256:raise ValueError('Request budget must leave at least 256 input tokens')
        if not math.isfinite(self.max_seconds) or self.max_seconds<=0:raise ValueError('max_seconds must be positive and finite')
        if not math.isfinite(self.min_request_interval) or self.min_request_interval<0:raise ValueError('min_request_interval must be non-negative and finite')
        if type(self.tokens_per_minute) is not int or self.tokens_per_minute<0:raise ValueError('tokens_per_minute must be a non-negative integer')

    def remaining_seconds(self):return self.max_seconds-(time.monotonic()-self.started)
    def check(self):
        if self.remaining_seconds()<=0 or self.tokens>=self.max_tokens:raise BudgetExceeded('Time or token budget exhausted')
    def model(self):
        self.check()
        if self.model_calls>=self.max_model_calls:raise BudgetExceeded('Model call budget exhausted')
        self.model_calls+=1
    def tool(self):
        self.check()
        if self.tool_calls>=self.max_tool_calls:raise BudgetExceeded('Tool call budget exhausted')
        self.tool_calls+=1
    def delegate(self):
        self.check()
        if self.delegations>=self.max_delegations:raise BudgetExceeded('Delegation budget exhausted')
        self.delegations+=1
    def summary(self):return dict(model_turn_attempts=self.model_calls,tool_calls=self.tool_calls,
        delegations=self.delegations,tokens=self.tokens,elapsed_seconds=round(time.monotonic()-self.started,3))


class ToolRunner:
    def __init__(self,store,case_id,client,budget=None):
        self.store=store;self.case_id=case_id;self.client=client;self.budget=budget or RunBudget();self.run_id=uid('RUN')
        mode=store.case(case_id)['mode']
        if getattr(client,'mode',None)!=mode:raise ValueError('Client and case modes must match; no silent replay fallback')
        self.active_tasks=set()
        self.last_request_started=None
        self.last_diagnostic=None
        self.token_window=TokenWindow()
        if mode=='live' and self.budget.tokens_per_minute:
            now=time.monotonic();wall=time.time()
            for event in self.store.audit_events(case_id):
                if event['event_type']!='model_request':continue
                payload=event['payload']
                reserved=payload.get('estimated_input_tokens',0)+payload.get('output_token_cap',0)
                age=max(0,wall-datetime.fromisoformat(event['created_at']).timestamp())
                if age<60 and type(reserved) is int and reserved>0:self.token_window.record(now-age,reserved)

    def _pause(self,seconds,reason,role):
        if seconds<=0:return
        if seconds+1>=self.budget.remaining_seconds():
            raise BudgetExceeded('Required wait exceeds remaining run time; case can be resumed later')
        self.store.audit(self.case_id,'request_wait',dict(seconds=round(seconds,3),reason=reason),actor=role)
        # Short interruptible sleeps; all waiting consumes the shared run budget.
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            time.sleep(max(0,min(1,end-time.monotonic())))
            self.budget.check()

    def _invoke(self,role,messages,definitions,task_progress=None):
        # SDK retries remain disabled. One bounded retry; never immediately hammer
        # a throttled endpoint or retry quota/context errors unchanged.
        progress=task_progress or {}
        feedback=dict(model_attempts_remaining_at_preparation=max(0,self.budget.max_model_calls-self.budget.model_calls),
            seconds_remaining_at_preparation=max(0,round(self.budget.remaining_seconds(),1)),
            task_turns_remaining=max(0,12-progress.get('turns',0)),
            persisted_deliverables=progress.get('persisted_deliverables',0))
        # Ephemeral run facts, not a replacement for the task or its checkpoint.
        # Include them in input sizing without making the latest tool result an
        # older observation that compression could silently discard.
        system=system_prompt(role)+'\nCURRENT EXECUTION BUDGET (application): '+encode(feedback)+'''
The budget includes this request, retries, waits and nested specialist work; it is
an upper bound, not a promise of enough calls to finish every item. Work toward ONE
useful persisted deliverable first. If existing observations support a limited
provisional finding, save it now before broadening the search. State unsupported
scope and remaining questions explicitly. Do not claim unperformed checks. When a
large delegated task is only partly addressed, return needs_review with remaining
work after saving the supported result; do not label the whole task completed.
Keep new delegations to one decision question and one expected saved deliverable.
'''
        request_cap=min(self.budget.max_request_tokens,self.budget.tokens_per_minute or self.budget.max_request_tokens)
        if request_cap<512:raise RequestTooLarge('Configured request/TPM budget is too small for this tool protocol.')
        max_output=min(self.budget.max_output_tokens,request_cap-256)
        bounded,estimated_input,compacted=bounded_messages(system,messages,definitions,
            request_cap-max_output)
        if compacted:self.store.audit(self.case_id,'context_compacted',dict(role=role,observations=compacted,
            estimated_input_tokens=estimated_input),actor=role)
        for attempt in range(2):
            self.budget.check()
            if self.budget.model_calls>=self.budget.max_model_calls:raise BudgetExceeded('Model call budget exhausted')
            if self.last_request_started is not None and self.client.mode=='live':
                self._pause(max(0,self.budget.min_request_interval-(time.monotonic()-self.last_request_started)),
                    'minimum_request_interval',role)
            remaining_tokens=self.budget.max_tokens-self.budget.tokens-estimated_input
            if remaining_tokens<256:raise BudgetExceeded('Insufficient remaining context/output token budget')
            reserved_tokens=estimated_input+min(max_output,remaining_tokens)
            if self.client.mode=='live':
                self._pause(self.token_window.delay(time.monotonic(),reserved_tokens,self.budget.tokens_per_minute),
                    'tokens_per_minute_window',role)
            self.budget.model()
            before=getattr(self.client,'request_attempts',0);start=time.monotonic()
            self.last_request_started=start
            if self.client.mode=='live':self.token_window.record(start,reserved_tokens)
            self.store.audit(self.case_id,'model_request',dict(role=role,attempt=attempt+1,
                estimated_input_tokens=estimated_input,output_token_cap=min(max_output,remaining_tokens),
                request_token_cap=request_cap,tokens_per_minute=self.budget.tokens_per_minute,
                execution_budget=feedback),actor=role)
            try:
                response=self.client.generate(role=role,system=system,messages=bounded,tools=definitions,
                    max_tokens=min(max_output,remaining_tokens),timeout=max(.1,min(35,self.budget.remaining_seconds())))
            except Exception as exc:
                diagnostic=error_diagnostic(exc);self.last_diagnostic=diagnostic
                self.store.audit(self.case_id,'model_error',dict(role=role,error_type=type(exc).__name__,attempt=attempt+1,
                    api_requests_attempted=getattr(self.client,'request_attempts',0)-before,**diagnostic),actor=role)
                if not diagnostic['retryable'] or attempt==1:raise
                if self.budget.model_calls>=self.budget.max_model_calls:
                    raise BudgetExceeded('Model call budget exhausted before retry') from None
                delay=diagnostic['retry_after_seconds']
                if delay is None:delay=(8 if diagnostic['category']=='rate_limit' else 1)*2**attempt+random.uniform(0,1)
                self._pause(delay,'provider_retry',role)
                continue
            self.last_diagnostic=None
            usage=response.get('usage',{})
            tokens=usage.get('input_tokens',estimated_input)+usage.get('output_tokens',max(1,len(encode(response.get('content',[])))//3))
            if type(tokens) is not int or tokens<0:raise ValueError('Invalid provider usage metadata')
            self.budget.tokens+=tokens
            self.store.audit(self.case_id,'model_response',dict(role=role,latency_seconds=round(time.monotonic()-start,3),
                tokens=tokens,stop_reason=response.get('stop_reason'),mode=self.client.mode,
                input_tokens=usage.get('input_tokens'),output_tokens=usage.get('output_tokens'),
                api_requests_attempted=getattr(self.client,'request_attempts',0)-before),actor=role)
            self.budget.check()
            return response

    def _task(self,role,task,task_key,depth=0):
        from task_execution import execute_task
        return execute_task(self,role,task,task_key,depth)

    def run(self):
        self.store.set_status(self.case_id,'running','Investigation run started')
        try:
            outcome=self._task('coordinator',self.store.case(self.case_id)['goal'],'coordinate')
            status={'completed':'investigation_complete','waiting':'waiting_for_input','needs_review':'needs_review'}[outcome['status']]
            self.store.set_status(self.case_id,status,outcome['summary'])
        except Exception as exc:
            outcome=dict(status='failed',error_type=type(exc).__name__,
                message='Investigation stopped; committed case state is retained. Inspect audit events and provider configuration before resuming.')
            if self.last_diagnostic:outcome['provider_diagnostic']=self.last_diagnostic
            if isinstance(exc,(RequestTooLarge,BudgetExceeded)):outcome['message']=str(exc)
            self.store.set_status(self.case_id,'failed',outcome['error_type'])
        result=dict(case_id=self.case_id,outcome=outcome,budget=self.budget.summary(),
                    api_requests_attempted=getattr(self.client,'request_attempts',0),mode=self.client.mode)
        self.store.audit(self.case_id,'run_finished',result)
        return result
