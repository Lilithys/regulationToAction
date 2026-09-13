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
            summary=('调查及条件性成本已保存；等待明确分母的能源数据答复。' if waiting else
                     '已根据答复更新能源数据完整度；原有来源和成本发现保留。来源全文、法律审核及后续行动实施仍待完成。'))

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
                summary=f"来源为已登记候选；版本检查={versions['status']}。候选范围={scope['legal_scope']}，时间={scope['temporal_status']}。使用整理后的条款转述，未独立完成原文抽取或法律审核。",
                reference_ids=[req['reference_id'],results['source_citation']['reference_id'],versions['reference_id'],scope['reference_id']])
        return call('finish',status='completed',summary='来源限制、日期与候选范围已记录，法律解释保持 provisional。')

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
                    rationale=('文本提及ESG存量监测控制/测试相关内容，与该证据类型声明相符。' if plausible else
                               '文本未提及ESG、控制或监测，疑似与声明的证据类型无关。'),
                    reference_ids=[ev['reference_id']])
            return call('finish',status='completed',summary='已读取并给出证据内容判断；最终认定与结案仍需人工决定。')
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
                    rationale='控制按新申请执行，不能证明存量持续监测。' if per_application else '需要审核控制频率与持续监测之间的支持关系。',
                    reference_ids=[req['reference_id'],control['reference_id']])
            if 'walk_dependencies' not in names:return call('walk_dependencies',record_id=control['record_id'],depth=1)
            if 'portfolio_facts' not in names:return call('portfolio_facts')
        if 'energy_coverage' not in names:return call('energy_coverage')
        energy=results['energy_coverage']
        if energy['coverage_pct'] is None and 'request_question' not in names:
            return call('request_question',fact_id='FACT-ESG-ENERGY-COVERAGE',decision_reason='确定能源数据采集的缺失客户规模；不把该比例推断为风险水平或自动化率。')
        if 'record_finding' not in names:
            summary=('能源数据覆盖仍未知；保留采集工作量的不确定性。' if energy['coverage_pct'] is None else
                     f"按归属明确的答复：{energy['denominator']}个存量SME客户中，{energy['usable_borrower_count']}个有可用能源数据，{energy['missing_borrower_count']}个待补齐。答复不是实操证据。")
            return call('record_finding',key='energy-data',category='data_quality',summary=summary,reference_ids=[energy['reference_id']])
        return call('finish',status='waiting' if energy['coverage_pct'] is None else 'completed',summary='能源数据问题及相关发现已保存。')

    def costs(self,seen):
        names=[name for name,_,_ in seen];results={name:result for name,_,result in seen}
        if not seen:return call('compare_costs')
        if 'record_finding' not in names:
            result=results['compare_costs']
            amounts={o['option_id']:o['scenarios']['base']['three_year_tco_eur'] for o in result['options']}
            return call('record_finding',key='conditional-costs',category='cost',summary=f'两条要求的模板三年TCO：{amounts}。团队产能未知，最低成本不等于获批建议。',reference_ids=[result['reference_id']])
        if 'find_roles' not in names:return call('find_roles',process_id='PROC-CREDIT-RISK-MONITORING')
        if 'propose_plan' not in names:
            costs=results['compare_costs']
            return call('propose_plan',option_id='OPT-ESG-AUTOMATED',requirement_ids=['REQ-ESG-CREDIT-MONITORING-001'],
                rationale='本任务范围仅为存量客户ESG监测要求；自动化模板三年期成本最低，但产能与法律审核未决，先按此单一要求提出方案，其余ESG要求分开处理。',
                reference_ids=[costs['reference_id']])
        if 'propose_action' not in names:
            plan=results['propose_plan'];roles=results['find_roles']
            return call('propose_action',plan_key=plan['object_key'],title='部署自动化存量ESG监测控制',
                steps='确认自动化监测所需数据字段与实施步骤；小范围试点验证准确性；扩大到全部存量SME客户并保留运行证据。',
                target_date=plan['payload']['calculation']['projected_delivery_date'],
                accountable_role_id=roles['candidates'][0]['role_id'],
                dependency_note='依赖治理映射审核结论（per-application控制不能直接证明存量监测）先确认，避免重复计入同一控制的覆盖范围。',
                required_evidence=[dict(evidence_key='design',evidence_type='control_design',title='存量自动化ESG监测控制设计文档'),
                                    dict(evidence_key='test',evidence_type='control_effectiveness_test',title='控制有效性测试结果')],
                reference_ids=[roles['reference_id']])
        return call('finish',status='completed',
            summary='条件性经济比较、按存量ESG监测要求单独提出的分阶段方案与责任指派（草案）已保存；责任接受、执行与证据审核仍需人工在调查之外确认，不构成已批准资源或最终整改承诺。')
