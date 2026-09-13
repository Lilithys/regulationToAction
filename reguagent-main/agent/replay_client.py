"""Explicit scripted integration replay, NOT an LLM or an agent-quality evaluation.

It emits real tool-use messages and branches on real tool observations so tests
exercise the same persistence/permissions/answer path as live model calls.
"""
import json
import re
import uuid
import copy


def history(messages):
    calls={};observations=[]
    for message in messages:
        content=message.get('content')
        if not isinstance(content,list):continue
        for block in content:
            if block.get('type')=='tool_use':calls[block['id']]=block
            elif block.get('type')=='tool_result':
                call=calls[block['tool_use_id']]
                observations.append((call['name'],call['input'],json.loads(block['content'])))
    return observations


def call(name,**arguments):return dict(content=[dict(type='tool_use',id='replay-'+uuid.uuid4().hex,name=name,input=arguments)],stop_reason='tool_use',usage={'input_tokens':0,'output_tokens':0})


class ReplayClient:
    mode='replay'
    request_attempts=0

    def __init__(self):
        # Script fixtures keep their already-seen observations, analogous to local
        # test variables. This is not model memory or a live inference result.
        self._seen_results={}

    def restore_observations(self,messages):
        for message in messages:
            if not isinstance(message.get('content'),list):continue
            for block in message['content']:
                if block.get('type')=='tool_result' and json.loads(block['content']).get('status')!='context_compacted':
                    self._seen_results[block['tool_use_id']]=block['content']

    def generate(self,*,role,system,messages,tools,max_tokens,timeout):
        messages=copy.deepcopy(messages)
        for message in messages:
            if not isinstance(message.get('content'),list):continue
            for block in message['content']:
                if block.get('type')!='tool_result':continue
                key=block['tool_use_id']
                if json.loads(block['content']).get('status')=='context_compacted':
                    block['content']=self._seen_results.get(key,block['content'])
                else:self._seen_results[key]=block['content']
        seen=history(messages)
        last=seen[-1] if seen else None
        if last and last[2].get('status')=='tool_error':raise ValueError('Replay hit a tool contract error: '+last[2]['message'])
        if role=='coordinator':return self.coordinate(last)
        if role=='regulatory_analyst':return self.regulation(seen)
        if role=='bank_investigator':return self.bank(seen,json.loads(messages[0]['content'])['task'])
        if role=='response_planner':return self.costs(seen)
        raise ValueError('Unknown replay role')

    def coordinate(self,last):
        if not last or last[0]=='delegate':return call('case_context')
        if last[0]!='case_context':raise ValueError('Unexpected replay observation')
        current={o['key']:o for o in last[2]['objects']}
        if 'source-summary' not in current or current['source-summary']['status']=='stale':
            return call('delegate',role='regulatory_analyst',task_key='source-scope',task='Inspect credit-monitoring source, actual text availability, dates and provisional scope.')
        if 'energy-data' not in current:
            return call('delegate',role='bank_investigator',task_key='bank-investigation',task='Investigate onboarding versus monitoring using governance text, dependencies and the unresolved energy-data fact.')
        if current['energy-data']['status']=='stale':
            return call('delegate',role='bank_investigator',task_key='energy-refresh',task='Recompute energy-data completeness after the attributed owner answer; preserve unrelated source and cost findings.')
        if 'conditional-costs' not in current:
            return call('delegate',role='response_planner',task_key='conditional-costs',task='Compare existing scoped cost templates while any data question remains unresolved. Do not approve a recommendation.')
        unassessed=[o for o in last[2]['objects'] if o['kind']=='Evidence' and o['payload'].get('content_assessment') is None]
        if unassessed:
            target=unassessed[0]
            return call('delegate',role='bank_investigator',task_key='evidence-review:'+target['key'],
                task=f"Review submitted evidence {target['key']}; read its actual text before judging content relevance and type match.")
        waiting=any(o['kind']=='Question' and o['status']=='open' for o in last[2]['objects'])
        return call('finish',status='waiting' if waiting else 'completed',
            summary=('Investigation findings and conditional costs have been saved; awaiting an energy-data answer with an explicit denominator.' if waiting else
                     'Energy-data completeness has been updated from the answer; existing source and cost findings have been retained. Full source text, legal review and subsequent action implementation remain outstanding.'))

    def regulation(self,seen):
        names=[name for name,_,_ in seen];results={name:result for name,_,result in seen}
        if not seen:return call('get_record',record_id='REQ-ESG-CREDIT-MONITORING-001')
        req=results['get_record']['results'][0]
        if 'source_citation' not in names:return call('source_citation',citation_id=req['record']['source_citations'][0]['citation_id'])
        if 'source_versions' not in names:return call('source_versions')
        if 'applicability' not in names:return call('applicability',requirement_id=req['record_id'])
        if 'record_finding' not in names:
            scope=results['applicability'];versions=results['source_versions']
            return call('record_finding',key='source-summary',category='source',
                summary=f"The source is a registered candidate; version check={versions['status']}. Candidate scope={scope['legal_scope']}; timing={scope['temporal_status']}. This uses curated clause paraphrases; independent source-text extraction and legal review have not been completed.",
                reference_ids=[req['reference_id'],results['source_citation']['reference_id'],versions['reference_id'],scope['reference_id']])
        return call('finish',status='completed',summary='Source limitations, dates and candidate scope have been recorded; the legal interpretation remains provisional.')

    def bank(self,seen,task):
        names=[name for name,_,_ in seen];results={name:result for name,_,result in seen}
        review_match=re.match(r'Review submitted evidence (\S+);',task)
        if review_match:
            evidence_key=review_match.group(1)
            if 'read_evidence' not in names:return call('read_evidence',evidence_key=evidence_key)
            ev=results['read_evidence'];text=ev['text'].lower()
            if 'review_evidence' not in names:
                plausible='esg' in text and ('control' in text or 'test' in text or 'monitor' in text)
                return call('review_evidence',evidence_key=evidence_key,
                    content_assessment='plausibly_responsive' if plausible else 'unrelated_content',
                    rationale=('The text refers to ESG monitoring controls or tests for the existing portfolio, consistent with the declared evidence type.' if plausible else
                               'The text lacks relevant ESG, control or monitoring content and appears unrelated to the declared evidence type.'),
                    reference_ids=[ev['reference_id']])
            return call('finish',status='completed',summary='The evidence has been read and its content assessed; final verification and closure still require human decisions.')
        refresh=task.startswith('Recompute')
        if not refresh:
            if not seen:return call('get_record',record_id='REQ-ESG-CREDIT-MONITORING-001')
            if 'search_records' not in names:return call('search_records',query='ESG sector screen new lending',collection='governance',limit=6,detail='full')
            req=results['get_record']['results'][0]
            candidates=[r for r in results['search_records']['results'] if r['path']=='04_governance/controls.json']
            if not candidates:raise ValueError('Replay fixture expects a governance control candidate; this is not a general semantic agent')
            control=candidates[0]
            if 'propose_mapping' not in names:
                per_application=control['record'].get('frequency')=='per_new_credit_application'
                return call('propose_mapping',requirement_id=req['record_id'],control_id=control['record_id'],
                    support='related_not_supporting' if per_application else 'unknown',
                    rationale='The control runs for each new application and does not demonstrate ongoing monitoring of the existing portfolio.' if per_application else 'The relationship between control frequency and ongoing monitoring needs review.',
                    reference_ids=[req['reference_id'],control['reference_id']])
            if 'walk_dependencies' not in names:return call('walk_dependencies',record_id=control['record_id'],depth=1)
            if 'portfolio_facts' not in names:return call('portfolio_facts')
        if 'energy_coverage' not in names:return call('energy_coverage')
        energy=results['energy_coverage']
        if energy['coverage_pct'] is None and 'request_question' not in names:
            return call('request_question',fact_id='FACT-ESG-ENERGY-COVERAGE',decision_reason='Determine how many borrowers need energy-data collection; do not interpret this percentage as a risk level or automation rate.')
        if 'record_finding' not in names:
            summary=('Energy-data coverage remains unknown; the data-collection workload is still uncertain.' if energy['coverage_pct'] is None else
                     f"According to the attributed answer: of {energy['denominator']} existing SME borrowers, {energy['usable_borrower_count']} have usable energy data and {energy['missing_borrower_count']} still need data. The answer is not operating evidence.")
            return call('record_finding',key='energy-data',category='data_quality',summary=summary,reference_ids=[energy['reference_id']])
        return call('finish',status='waiting' if energy['coverage_pct'] is None else 'completed',summary='The energy-data question and related findings have been saved.')

    def costs(self,seen):
        names=[name for name,_,_ in seen];results={name:result for name,_,result in seen}
        if not seen:return call('compare_costs')
        if 'record_finding' not in names:
            result=results['compare_costs']
            amounts={o['option_id']:o['scenarios']['base']['three_year_tco_eur'] for o in result['options']}
            return call('record_finding',key='conditional-costs',category='cost',summary=f'Template three-year TCO for the two requirements: {amounts}. Team capacity is unknown; the lowest cost is not an approved recommendation.',reference_ids=[result['reference_id']])
        if 'find_roles' not in names:return call('find_roles',process_id='PROC-CREDIT-RISK-MONITORING')
        if 'propose_plan' not in names:
            costs=results['compare_costs']
            return call('propose_plan',option_id='OPT-ESG-AUTOMATED',requirement_ids=['REQ-ESG-CREDIT-MONITORING-001'],
                rationale='This task covers only ESG monitoring for existing borrowers. The automated template has the lowest three-year cost, but capacity and legal review remain unresolved. Propose a plan for this requirement and address other ESG requirements separately.',
                reference_ids=[costs['reference_id']])
        if 'propose_action' not in names:
            plan=results['propose_plan'];roles=results['find_roles']
            return call('propose_action',plan_key=plan['object_key'],title='Implement automated ESG monitoring controls for the existing portfolio',
                steps='Confirm the data fields and implementation steps for automated monitoring; validate accuracy in a small pilot; extend coverage to all existing SME borrowers and retain operating evidence.',
                target_date=plan['payload']['calculation']['projected_delivery_date'],
                accountable_role_id=roles['candidates'][0]['role_id'],
                dependency_note='First confirm the governance mapping review: a per-application control does not directly demonstrate existing-portfolio monitoring. Avoid double-counting the coverage of the same control.',
                required_evidence=[dict(evidence_key='design',evidence_type='control_design',title='Control design document for automated ESG monitoring of the existing portfolio'),
                                    dict(evidence_key='test',evidence_type='control_effectiveness_test',title='Control effectiveness test results')],
                reference_ids=[roles['reference_id']])
        return call('finish',status='completed',
            summary='The conditional cost comparison, phased plan scoped to existing-portfolio ESG monitoring and draft responsibility assignment have been saved. Acceptance, execution and evidence review still require human confirmation outside the investigation; resources and final remediation commitments have not been approved.')
