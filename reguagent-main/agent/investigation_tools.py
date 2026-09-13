"""Allowlisted, provenance-bearing investigation tools and fact-answer services."""
from __future__ import annotations
import copy
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from case_store import digest, utcnow, encode
from source_intake import compare_versions, read_snapshot
from tool_contracts import obj,string,choice,array,integer,validate
from dataset_runtime import calculate_options, evaluate_option, deadline_status
from exposure_esg import portfolio_fact_report
from applicability import assess_requirement_applicability
from evidence_intake import read_evidence_text, evaluate_closure

FACT_ID='FACT-ESG-ENERGY-COVERAGE'
SME_PRODUCT='PRD-SME-WORKING-CAPITAL'
ID_KEYS=['requirement_id','control_id','policy_id','procedure_id','source_id','change_id','dependency_mapping_id',
         'process_id','system_id','data_asset_id','vendor_id','function_id','role_id','fact_id','portfolio_record_id',
         'product_id','business_line_id','entity_id','option_id','cost_centre_id','version_pair_id','payment_metric_id','position_id','mortgage_case_id']
COLLECTIONS={'governance':['04_governance/'],'regulation':['regulatory_sources/'],'business':['01_entity/','02_business/','03_exposure/'],
             'operations':['05_operations/'],'organisation':['06_organisation/'],'economics':['07_economics/']}
ANSWER_SCHEMA=obj(dict(value=dict(type='number',minimum=0,maximum=100),unit=choice('percent_of_existing_sme_borrowers'),
    denominator=integer(1,10_000_000),numerator=integer(0,10_000_000),population_product_id=choice(SME_PRODUCT),
    as_of_date=string(10),answered_by=string(200),answered_by_role_id=string(100),source=string(1000),
    synthetic=dict(type='boolean')))


def strip_mapping_answers(value):
    hidden={'requirement_ids','policy_ids','control_ids','procedure_ids','current_coverage','gap_flags',
            'extensions','annotation','interpretation_notes','missing_evidence','provenance'}
    if isinstance(value,dict):return {k:strip_mapping_answers(v) for k,v in value.items() if k not in hidden}
    if isinstance(value,list):return [strip_mapping_answers(v) for v in value]
    return value


def indexed_records(files):
    result=[]
    for path,data in files.items():
        # Response templates are exposed through the cost tool, not as bank facts.
        if path=='07_economics/response_options.json':continue
        if isinstance(data,list):groups=[('',data)]
        elif isinstance(data,dict) and 'entity_id' in data:groups=[('',[data])]
        elif isinstance(data,dict):groups=[(key,rows) for key,rows in data.items() if isinstance(rows,list) and rows and isinstance(rows[0],dict)]
        else:continue
        for envelope,rows in groups:
            for index,raw in enumerate(rows):
                record=strip_mapping_answers(raw) if path.startswith('04_governance/') or path=='regulatory_sources/requirements.json' else copy.deepcopy(raw)
                id_field=next((key for key in ID_KEYS if isinstance(record.get(key),str)),None)
                record_id=record[id_field] if id_field else f'row:{index}'
                ref='REF-'+digest(dict(path=path,envelope=envelope,index=index,record=record))[:24]
                result.append(dict(reference_id=ref,path=path,envelope=envelope,record_id=record_id,id_field=id_field,
                    record=record,content_sha256=digest(record),depends_on=['file:'+path],
                    text_kind='synthetic_internal_record' if raw.get('synthetic') in (True,'true') else 'curated_source_record',
                    record_status=raw.get('record_status','provided'),review_status='provisional'))
    return result


class InvestigationTools:
    def __init__(self,store,case_id,role,artifact_root=None):
        self.store=store;self.case_id=case_id;self.role=role
        self.files=store.inputs(case_id);self.case=store.case(case_id)
        self.records=indexed_records(self.files);self.byref={r['reference_id']:r for r in self.records}
        self.observed={};self.fact_lookups=set();self.artifact_root=artifact_root or store.path.parent/'source_artifacts'
        self.evidence_root=store.path.parent/'evidence_artifacts'

    def _observe(self,result):
        if isinstance(result,dict):
            if result.get('reference_id'):self.observed[result['reference_id']]=copy.deepcopy(result)
            for key in ('results','nodes'):
                for row in result.get(key,[]):self._observe(row)
        return result

    def get_record(self,record_id):
        hits=[r for r in self.records if r['record_id']==record_id]
        return self._observe(dict(status='ok' if hits else 'not_found',results=copy.deepcopy(hits)))

    def search_records(self,query,collection='all',limit=5,detail='summary'):
        words=set(re.findall(r'[a-z0-9]+',query.lower()))
        candidates=self.records if collection=='all' else [r for r in self.records if any(r['path'].startswith(p) for p in COLLECTIONS[collection])]
        hits=[]
        for row in candidates:
            # Governance body is retained; no pre-filled requirement links in index.
            body=encode(row['record']).lower();score=sum(1 for word in words if word in body)
            if score:hits.append((score,row))
        hits.sort(key=lambda item:(-item[0],item[1]['reference_id']))
        rows=[copy.deepcopy(r) for _,r in hits[:limit]]
        if detail=='summary':
            for row in rows:
                record=row.pop('record')
                row['record']={k:v[:350] for k,v in record.items()
                    if k in ('title','name','short_name','objective','frequency','requirement_text') and isinstance(v,str)}
                row['excerpt']=encode(record)[:650]
                row['view']='search_preview'
                row['note']='Discovery excerpt only. Use get_record(record_id) for full text before assessing coverage.'
        return self._observe(dict(status='ok' if hits else 'not_found',results=rows,
            total_matches=len(hits),truncated=len(hits)>limit,search_method='keyword_overlap',
            scope='Frozen case input, allowlisted collections only; not proof that all bank documents exist here.'))

    def resolve_reference(self,reference_id):
        if reference_id not in self.byref:raise ValueError('Reference is not in the frozen allowlisted case input')
        return self._observe(copy.deepcopy(self.byref[reference_id]))

    def source_citation(self,citation_id):
        requirements=self.files['regulatory_sources/requirements.json']['requirements']
        sources={s['source_id']:s for s in self.files['regulatory_sources/change_register.json']['sources']}
        found=[c for r in requirements for c in r.get('source_citations',[]) if c['citation_id']==citation_id]
        if len(found)!=1:raise ValueError('Citation must resolve uniquely')
        c=found[0];source=sources[c['source_id']]
        result=dict(reference_id=citation_id,status='ok',citation=copy.deepcopy(c),official_url=source['url'],
            text_kind=c['evidence_type'],source_verification_status=source['verification_status'],
            full_original_available=bool(source.get('content_sha256')),review_status='provisional',
            depends_on=['file:regulatory_sources/requirements.json','source:'+c['source_id']],
            note='A curated paraphrase is not a verbatim quote or a preserved official full-text version.')
        return self._observe(result)

    def source_versions(self):
        result=compare_versions(self.store,self.case_id,self.artifact_root)
        result.update(reference_id='SOURCE-COMPARE-'+digest(result)[:16],depends_on=['source:SRC-ESG-EBA-GL-2025-01'])
        return self._observe(result)

    def source_text(self,identifier,offset=0):
        result=read_snapshot(self.store,self.case_id,identifier,self.artifact_root,offset)
        result.update(reference_id='SOURCE-TEXT-'+digest(result)[:16],depends_on=['source:SRC-ESG-EBA-GL-2025-01'])
        return self._observe(result)

    def walk_dependencies(self,record_id,depth=1):
        known={r['record_id'] for r in self.records};frontier={record_id};visited=set();edges=[]
        def references(value):
            if isinstance(value,str):return {value} if value in known else set()
            if isinstance(value,list):return set().union(*(references(v) for v in value)) if value else set()
            if isinstance(value,dict):return set().union(*(references(v) for v in value.values())) if value else set()
            return set()
        for _ in range(depth):
            next_ids=set()
            for row in self.records:
                refs=references(row['record'])-{row['record_id']}
                if row['record_id'] in frontier:
                    for target in refs:edges.append(dict(source=row['record_id'],target=target,reference_id=row['reference_id']))
                    next_ids |= refs
                elif refs & frontier:
                    for target in refs & frontier:edges.append(dict(source=row['record_id'],target=target,reference_id=row['reference_id']))
                    next_ids.add(row['record_id'])
            visited |= frontier;frontier=next_ids-visited
        visited |= frontier
        return self._observe(dict(status='ok',nodes=[copy.deepcopy(r) for r in self.records if r['record_id'] in visited][:40],
            edges=sorted({(e['source'],e['target'],e['reference_id']) for e in edges}),
            truncated=len([r for r in self.records if r['record_id'] in visited])>40,
            note='Recorded relationships, not evidence of complete dependency coverage.'))

    def portfolio_facts(self):
        result=portfolio_fact_report(self.files,[SME_PRODUCT],date.fromisoformat(self.case['as_of_date']))
        result.update(reference_id='CALC-PORTFOLIO-'+digest(result)[:16],depends_on=['file:03_exposure/lending_portfolio.csv','file:03_exposure/esg_assessment_snapshot.csv'])
        return self._observe(result)

    def applicability(self,requirement_id):
        req=next((r for r in self.files['regulatory_sources/requirements.json']['requirements'] if r['requirement_id']==requirement_id),None)
        if req is None or not requirement_id.startswith('REQ-ESG'):raise ValueError('This investigation tool supports the selected ESG scenario')
        result=assess_requirement_applicability(req,self.files['01_entity/bank_profile.json'],self.files['02_business/products.json'],date.fromisoformat(self.case['as_of_date']))
        result.update(reference_id='CALC-SCOPE-'+digest(result)[:16],depends_on=['file:regulatory_sources/requirements.json','file:01_entity/bank_profile.json','file:02_business/products.json'])
        return self._observe(result)

    def compare_costs(self):
        result=calculate_options(self.files)
        result.update(reference_id='CALC-COSTS-'+digest(result)[:16],depends_on=['file:03_exposure/lending_portfolio.csv','file:07_economics/response_options.json','file:07_economics/operational_costs.csv'],
            scope='Existing SME data-gaps and credit-monitoring templates only; not all ESG obligations.')
        return self._observe(result)

    def get_fact(self,fact_id):
        fact=next((f for f in self.files['03_exposure/missing_facts.json'] if f['fact_id']==fact_id),None)
        if not fact:raise ValueError('Unknown missing-fact ID')
        self.fact_lookups.add(fact_id)
        patch=self.store.get(self.case_id,'FactPatch',fact_id)
        result=dict(fact_id=fact_id,status='answered' if patch else 'unknown',value=patch['payload']['value'] if patch else fact['value'],
            source=patch['payload'] if patch else 'frozen_missing_fact_register',question=fact['question'],owner_role_id=fact['owner_role_id'],
            reference_id='FACT-OBS-'+digest(dict(fact=fact,patch=patch))[:20],depends_on=['fact:'+fact_id],
            searched_inputs=['03_exposure/missing_facts.json','runtime FactPatch versions'],
            note='A business response is an attributed fact, not verified operating evidence.')
        if fact_id==FACT_ID:
            records=[r for r in self.files['03_exposure/lending_portfolio.csv'] if r['product_id']==SME_PRODUCT]
            result.update(denominator=sum(int(r['borrower_count']) for r in records),unit='percent_of_existing_sme_borrowers',
                population_product_id=SME_PRODUCT,snapshot_dates=sorted({r['snapshot_date'] for r in records}))
            # Search available business text as well, without extracting an invented
            # percentage from unrelated scope/cost numbers.
            result['related_materials']=self.search_records('energy cost data','business',3)['results']
            result['searched_inputs'] += ['frozen_business_records_keyword_search']
        return self._observe(result)

    def energy_coverage(self):
        fact=self.get_fact(FACT_ID);value=fact['value'];denominator=fact['denominator']
        usable=Decimal(str(value))*denominator/100 if value is not None else None
        result=dict(reference_id='CALC-ENERGY-'+digest(fact)[:20],depends_on=['fact:'+FACT_ID,'file:03_exposure/lending_portfolio.csv'],
            status='known_from_attributed_answer' if value is not None else 'unknown',
            population_product_id=SME_PRODUCT,denominator=denominator,unit=fact['unit'],coverage_pct=value,
            usable_borrower_count=int(usable) if usable is not None and usable==int(usable) else None,
            missing_borrower_count=denominator-int(usable) if usable is not None and usable==int(usable) else None,
            snapshot_dates=fact['snapshot_dates'],evidence_status='owner_statement_unverified' if value is not None else 'missing',
            note='Only energy-data completeness changes. No borrower-level allocation, risk score, automation rate or TCO is inferred from this percentage.')
        return self._observe(result)

    def request_question(self,fact_id,decision_reason):
        if fact_id!=FACT_ID:raise ValueError('Only the scoped numeric SME energy interview is implemented; preserve other facts as unknown')
        if fact_id not in self.fact_lookups:raise ValueError('Call get_fact or energy_coverage before asking the user')
        fact=self.get_fact(fact_id)
        if fact['status']=='answered':return dict(status='already_answered',fact=fact)
        existing=self.store.get(self.case_id,'Question',fact_id)
        if existing:return existing
        roles={r['role_id'] for r in self.files['06_organisation/roles.json']}
        if fact['owner_role_id'] not in roles:raise ValueError('Question owner does not resolve')
        return self.store.put(self.case_id,'Question',fact_id,dict(question=fact['question'],decision_reason=decision_reason,
            owner_role_id=fact['owner_role_id'],unit=fact['unit'],denominator=fact['denominator'],
            population_product_id=SME_PRODUCT,snapshot_dates=fact['snapshot_dates'],fact_id=fact_id,
            legal_approval=False),['fact:'+fact_id],'open')

    def record_finding(self,key,summary,category,reference_ids,depends_on_findings=None):
        existing=self.store.get(self.case_id,'Finding',key)
        if existing and existing['payload'].get('author_role') not in (None,self.role):
            raise PermissionError('A specialist cannot replace another role’s finding')
        missing=set(reference_ids)-set(self.observed)
        if missing or not reference_ids:raise ValueError('Finding must cite references actually observed by this task')
        deps={dep for ref in reference_ids for dep in self.observed[ref].get('depends_on',[])}
        for name in depends_on_findings or []:
            parent=self.store.get(self.case_id,'Finding',name)
            if not parent or parent['status']=='stale':raise ValueError('Dependent finding is missing or stale')
            deps.add('object:Finding:'+name)
        return self.store.put(self.case_id,'Finding',key,dict(summary=summary,category=category,
            reference_ids=reference_ids,author_role=self.role,review_status='provisional',
            interpretation_not_legal_approval=True),deps,'draft')

    def propose_mapping(self,requirement_id,control_id,support,rationale,reference_ids):
        if not reference_ids or set(reference_ids)-set(self.observed):raise ValueError('Mapping must cite observed records')
        observed_ids={self.observed[r].get('record_id') for r in reference_ids}
        if requirement_id not in observed_ids or control_id not in observed_ids:raise ValueError('Read both requirement and control before proposing their relationship')
        if any(self.observed[r].get('view')=='search_preview' for r in reference_ids):
            raise ValueError('Search previews identify candidates only; get_record for full requirement/control text before mapping')
        if not any(r['record_id']==control_id and r['path']=='04_governance/controls.json' for r in self.records):raise ValueError('Unknown control')
        return self.store.put(self.case_id,'GapAssessment',requirement_id+'::'+control_id,
            dict(requirement_id=requirement_id,candidate_control_id=control_id,mapping_support=support,
                rationale=rationale,reference_ids=reference_ids,design_coverage='requires_criterion_review',
                operating_evidence='unverified',review_status='provisional',author_role=self.role),
            ['file:regulatory_sources/requirements.json','file:04_governance/controls.json'],'draft')

    def find_roles(self,process_id):
        rows=[r for r in self.files['06_organisation/raci.csv'] if r['process_id']==process_id]
        if not rows:raise ValueError('No RACI row recorded for this process_id')
        roles_by_id={r['role_id']:r for r in self.files['06_organisation/roles.json']}
        candidates=[]
        for row in rows:
            role=roles_by_id.get(row['role_id'])
            if role is None:continue
            candidates.append(dict(role_id=row['role_id'],raci=row['raci'],basis=row['notes'],
                title=role['title'],function=role['function'],seniority=role['seniority']))
        if not candidates:raise ValueError('RACI row references an unresolved role_id')
        result=dict(reference_id='RACI-'+digest(dict(process_id=process_id,candidates=candidates))[:20],
            process_id=process_id,candidates=candidates,
            depends_on=['file:06_organisation/raci.csv','file:06_organisation/roles.json'],
            note='Recorded standing-process accountability only; does not check current capacity or quarterly allocation.')
        return self._observe(result)

    def propose_plan(self,option_id,requirement_ids,rationale,reference_ids,population_count=None):
        if not reference_ids or set(reference_ids)-set(self.observed):
            raise ValueError('Plan must cite observed findings/gap assessments justifying scope and option choice')
        options={o['option_id']:o for o in self.files['07_economics/response_options.json']}
        if option_id not in options:raise ValueError('Unknown response option template')
        template=options[option_id];template_scope=set(template.get('requirement_ids',[]))
        requested=list(dict.fromkeys(requirement_ids))
        if not requested or set(requested)-template_scope:
            raise ValueError("requirement_ids must be a non-empty subset of the template's own declared scope; "
                             'propose a different/composed option to cover more requirements, do not overclaim this one')
        all_esg={r['requirement_id'] for r in self.files['regulatory_sources/requirements.json']['requirements']
                 if r['requirement_id'].startswith('REQ-ESG')}
        calculation=evaluate_option(self.files,template,scope_requirement_ids=requested,population_count=population_count)
        key=option_id+'::'+digest(requested)[:12]
        deps=['file:07_economics/response_options.json']+[dep for ref in reference_ids for dep in self.observed[ref].get('depends_on',[])]
        return self.store.put(self.case_id,'PlanVersion',key,dict(
            option_id=option_id,addresses_requirement_ids=requested,deferred_requirement_ids=sorted(all_esg-set(requested)),
            rationale=rationale,reference_ids=reference_ids,calculation=calculation,author_role=self.role,
            review_status='provisional',recommendation_status='needs_legal_review_and_delivery_team_capacity',
            note='Lowest cost or shortest delivery is not an approved recommendation; deferred requirements are not solved by this plan.'),
            deps,'draft')

    def propose_action(self,plan_key,title,steps,target_date,accountable_role_id,dependency_note,required_evidence,reference_ids):
        plan=self.store.get(self.case_id,'PlanVersion',plan_key)
        if not plan or plan['status']=='stale':raise ValueError('Plan is missing or stale; refresh it before proposing an action')
        if not reference_ids or set(reference_ids)-set(self.observed):
            raise ValueError('Action must cite an observed find_roles result justifying the accountable role')
        role_evidence=[self.observed[r] for r in reference_ids if 'candidates' in self.observed[r]]
        if not any(accountable_role_id in {c['role_id'] for c in ev['candidates']} for ev in role_evidence):
            raise ValueError('accountable_role_id must be one of an observed find_roles candidate, not asserted directly')
        date.fromisoformat(target_date)
        if date.fromisoformat(target_date)<date.fromisoformat(self.case['as_of_date']):
            raise ValueError('target_date is an internal remediation goal; it cannot be dated before the case as_of_date')
        evidence_keys=[e['evidence_key'] for e in required_evidence]
        if not required_evidence or len(set(evidence_keys))!=len(evidence_keys):
            raise ValueError('required_evidence must be non-empty with unique evidence_key values')
        regulatory_due_date=plan['payload']['calculation'].get('selected_regulatory_due_date')
        payload=dict(plan_key=plan_key,title=title,steps=steps,accountable_role_id=accountable_role_id,
            target_date=target_date,regulatory_due_date=regulatory_due_date,
            regulatory_deadline_status=deadline_status(regulatory_due_date,self.case['as_of_date']) if regulatory_due_date else 'unknown',
            internal_target_status=deadline_status(target_date,self.case['as_of_date']),
            dependency_note=dependency_note,acceptance_status='proposed',
            required_evidence=required_evidence,required_evidence_ids=evidence_keys,
            addresses_requirement_ids=plan['payload']['addresses_requirement_ids'],
            reference_ids=reference_ids,author_role=self.role,review_status='provisional',
            note='regulatory_due_date is sourced and immutable; target_date is an unapproved internal goal, never a replacement for it.')
        deps=['object:PlanVersion:'+plan_key]+[dep for r in reference_ids for dep in self.observed[r].get('depends_on',[])]
        return self.store.put(self.case_id,'Action',plan_key+'::action',payload,deps,'draft')

    def read_evidence(self,evidence_key,offset=0):
        result=read_evidence_text(self.store,self.case_id,evidence_key,self.evidence_root,offset)
        result.update(reference_id='EVD-TEXT-'+digest(dict(evidence_key=evidence_key,offset=offset,sha=result['content_sha256']))[:20],
            depends_on=['object:Evidence:'+evidence_key])
        return self._observe(result)

    def review_evidence(self,evidence_key,content_assessment,rationale,reference_ids):
        if not reference_ids or set(reference_ids)-set(self.observed):
            raise ValueError('Review must cite this evidence actually observed via read_evidence in this task')
        if not any(self.observed[r].get('evidence_key')==evidence_key for r in reference_ids):
            raise ValueError('reference_ids must include a read_evidence observation of this exact evidence_key')
        evidence=self.store.get(self.case_id,'Evidence',evidence_key)
        if not evidence or evidence['status']!='submitted':raise ValueError('Evidence is not in a submitted, undecided state')
        deps=set(evidence['depends_on'])|{dep for r in reference_ids for dep in self.observed[r].get('depends_on',[])}
        return self.store.put(self.case_id,'Evidence',evidence_key,dict(evidence['payload'],
            content_assessment=content_assessment,content_rationale=rationale,assessed_by_role=self.role,
            review_status='provisional'),sorted(deps),'submitted')

    def check_closure(self,action_key):
        result=evaluate_closure(self.store,self.case_id,action_key,self.evidence_root)
        result.update(reference_id='CLOSURE-'+digest(dict(action_key=action_key,result=result))[:20],
            depends_on=['object:Action:'+action_key],
            note='Metadata/hash/review-flag gate only; a qualified human still judges substantive sufficiency and legal/ESG scope.')
        return self._observe(result)

    def case_context(self):
        case=self.store.case(self.case_id)
        rows=self.store.objects(self.case_id)
        objects=[dict(kind=o['kind'],key=o['object_key'],version=o['version'],status=o['status'],payload=o['payload']) for o in rows if o['kind']!='Task']
        if self.role=='coordinator':
            # Coordination needs deliverables and open issues, not every source or
            # calculation repeated in its context. Specialists retain full reads.
            case={k:case[k] for k in ('case_id','goal','mode','status','as_of_date','snapshot_dates','revision','dataset_version')}
            for obj in objects:
                p=obj['payload']
                if obj['kind']=='SourceVersion':
                    p={k:p[k] for k in ('source_id','intake_mode','identifier','authenticity_status','note') if k in p}
                    change=obj['payload'].get('change',{})
                    p['change']={k:change[k] for k in ('title','legal_status','requirement_ids') if k in change}
                elif obj['kind']=='PlanVersion':
                    p={k:p[k] for k in ('option_id','addresses_requirement_ids','deferred_requirement_ids','rationale','review_status') if k in p}
                obj['payload']=p
        tasks=[dict(task_id=o['object_key'],role=o['payload'].get('role'),task_key=o['payload'].get('task_key'),
            status=o['status'],case_revision=o['payload'].get('case_revision'),
            checkpoint_available=bool(o['payload'].get('checkpoint'))) for o in rows if o['kind']=='Task']
        return dict(case=case,objects=objects,tasks=tasks,
            note='Task checkpoints retain tool observations; current-revision interrupted delegations resume automatically. Findings remain provisional.')

    def answer_question(self,fact_id,answer,request_key,question_version):
        validate(answer,ANSWER_SCHEMA)
        q=self.store.get(self.case_id,'Question',fact_id)
        if not q:raise ValueError('Question does not exist')
        if fact_id!=FACT_ID:raise ValueError('Unsupported answer contract')
        payload=q['payload']
        if answer['denominator']!=payload['denominator'] or answer['as_of_date'] not in payload['snapshot_dates']:
            raise ValueError('Answer denominator/date does not match the frozen question population')
        if date.fromisoformat(answer['as_of_date'])>date.fromisoformat(self.case['as_of_date']):raise ValueError('Answer is future-dated relative to the case')
        if answer['answered_by_role_id']!=payload['owner_role_id']:raise ValueError('Answer needs the designated owner role')
        if Decimal(str(answer['value']))*answer['denominator']/100!=answer['numerator']:
            raise ValueError('Percentage, numerator and denominator do not reconcile')
        if self.case['mode']=='replay' and not answer['synthetic']:raise ValueError('Replay answers must be explicitly synthetic')
        # Do not invent the actor's identity or an evidential verification flag.
        return self.store.apply_answer(self.case_id,fact_id,answer,request_key,question_version)


COMMON={'case_context','search_records','get_record','resolve_reference','get_fact','record_finding','check_closure'}
PERMISSIONS={
 'coordinator':{'case_context','delegate','finish','check_closure'},
 'regulatory_analyst':COMMON|{'source_citation','source_versions','source_text','applicability','finish'},
 'bank_investigator':COMMON|{'walk_dependencies','portfolio_facts','energy_coverage','request_question','propose_mapping','read_evidence','review_evidence','finish'},
 'response_planner':COMMON|{'compare_costs','walk_dependencies','energy_coverage','find_roles','propose_plan','propose_action','finish'},
}
SCHEMAS={
 'case_context':obj({}),
 'search_records':obj(dict(query=string(300),collection=choice('all',*COLLECTIONS),limit=integer(1,8),detail=choice('summary','full')),['query']),
 'get_record':obj(dict(record_id=string(120))),
 'resolve_reference':obj(dict(reference_id=string(180))),
 'source_citation':obj(dict(citation_id=string(180))),
 'source_versions':obj({}),
 'source_text':obj(dict(identifier=string(100),offset=integer(0,2_000_000)),['identifier']),
 'walk_dependencies':obj(dict(record_id=string(120),depth=integer(1,2)),['record_id']),
 'portfolio_facts':obj({}),
 'applicability':obj(dict(requirement_id=string(180))),
 'compare_costs':obj({}),
 'get_fact':obj(dict(fact_id=string(180))),
 'energy_coverage':obj({}),
 'request_question':obj(dict(fact_id=string(180),decision_reason=string(1500))),
 'record_finding':obj(dict(key=string(150),summary=string(3500),category=choice('source','scope','control_gap','data_quality','cost','synthesis'),
      reference_ids=array(string(180),1,12),depends_on_findings=array(string(150),0,12)),['key','summary','category','reference_ids']),
 'propose_mapping':obj(dict(requirement_id=string(180),control_id=string(180),support=choice('partial','related_not_supporting','unknown'),
      rationale=string(2500),reference_ids=array(string(180),2,8))),
 'find_roles':obj(dict(process_id=string(120))),
 'propose_plan':obj(dict(option_id=string(80),requirement_ids=array(string(180),1,8),rationale=string(2500),
      reference_ids=array(string(180),1,6),population_count=integer(0,10_000_000)),
      ['option_id','requirement_ids','rationale','reference_ids']),
 'propose_action':obj(dict(plan_key=string(150),title=string(300),steps=string(3000),target_date=string(10),
      accountable_role_id=string(100),dependency_note=string(1000),
      required_evidence=array(obj(dict(evidence_key=string(80),evidence_type=string(120),title=string(300)),
          ['evidence_key','evidence_type','title']),1,4),
      reference_ids=array(string(180),1,6))),
 'read_evidence':obj(dict(evidence_key=string(150),offset=integer(0,2_000_000)),['evidence_key']),
 'review_evidence':obj(dict(evidence_key=string(150),
      content_assessment=choice('plausibly_responsive','unrelated_content','wrong_evidence_type','insufficient_detail'),
      rationale=string(2000),reference_ids=array(string(180),1,4))),
 'check_closure':obj(dict(action_key=string(150))),
 'delegate':obj(dict(role=choice('regulatory_analyst','bank_investigator','response_planner'),task=string(2500),task_key=string(150))),
 'finish':obj(dict(status=choice('completed','waiting','needs_review'),summary=string(4000))),
}
DESCRIPTIONS={
 'search_records':'Find candidate IDs and short excerpts (default detail=summary). Then get_record for selected full text; use detail=full only for a small targeted set. Pre-filled governance answer links are removed.',
 'source_citation':'Resolve a real citation ID to its curated text, locator and official URL; explicitly distinguish paraphrase from original.',
 'source_versions':'Compare locally registered source versions; return insufficient_source_snapshots when absent. Never invent prior law.',
 'source_text':'Read a bounded segment of a registered local source candidate, with hash and authenticity status.',
 'record_finding':'Persist a provisional finding with references observed in this task and dependencies for later invalidation.',
 'propose_mapping':'Persist a provisional semantic relationship using observed requirement and control text, without modifying baseline links.',
 'find_roles':'Look up the standing RACI-accountable role(s) for an organisational process; does not check current capacity or allocation.',
 'propose_plan':'Draft a provisional plan scoped to a subset of a response-option templates own requirement_ids, computed from real cost numbers; not an approved recommendation.',
 'propose_action':'Draft a provisional action from a non-stale plan, with an accountable role grounded in an observed find_roles result and its own closure evidence requirements; requires separate human acceptance.',
 'read_evidence':'Read a bounded, hash-verified segment of a submitted evidence artefact; call before judging its content.',
 'review_evidence':'Persist a provisional content judgment (plausibly responsive / unrelated / wrong type / insufficient) on evidence actually read in this task; never itself a completeness gate or approval.',
 'check_closure':'Recompute the deterministic evidence-completeness gate for an action from current records; metadata/hash/review-flag only, not a substantive or legal sufficiency judgment.',
 'request_question':'Open the scoped energy-data question only after fact lookup; unresolved facts do not automatically block unrelated work.',
 'delegate':'Delegate a bounded task to a specialist and observe its actual tool-backed result; choose role and next step based on current needs.',
 'finish':'Return this investigation task as completed/waiting/needs_review. Never approves legal compliance or closes an action.',
 'energy_coverage':'Calculate energy coverage using attributed runtime answer and explicit population denominator. Does not alter risk or TCO.',
 'compare_costs':'Calculate the three existing two-requirement templates, retaining unknown capacity and no approved recommendation.',
}

def tool_definitions(role):
    if role not in PERMISSIONS:raise ValueError('Unknown agent role')
    return [dict(name=name,description=DESCRIPTIONS.get(name,name.replace('_',' ')+' on the frozen case data; preserve unknowns and provenance.'),
                 input_schema=SCHEMAS[name]) for name in sorted(PERMISSIONS[role])]
