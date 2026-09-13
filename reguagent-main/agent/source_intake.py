"""Explicit registered-source replay and local version registration; no fake fetches."""
from __future__ import annotations
import copy
import difflib
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from case_store import digest, utcnow
from dataset_runtime import load_runtime, DEFAULT_ROOT

ESG_SOURCE='SRC-ESG-EBA-GL-2025-01'
SUPPORTED_REQUEST_ID='REQ-ESG-CREDIT-MONITORING-001'


def _required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Request field {field} must be a non-empty string')
    return value.strip()


def load_reviewed_request(request_file, root=DEFAULT_ROOT):
    """Build a frozen, single-requirement input from a reviewed upstream handoff.

    This is intentionally not a regulation detector or a legal-review substitute.
    The supported demo request is constrained to the existing SME ESG monitoring
    response templates, so deterministic Part B/Part C calculations remain valid.
    """
    request_path=Path(request_file)
    try:
        request=json.loads(request_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ValueError(f'Request file does not exist: {request_path}') from None
    except json.JSONDecodeError as exc:
        raise ValueError(f'Request file is not valid JSON: {exc.msg}') from None
    if not isinstance(request,dict):raise ValueError('Request file must contain a JSON object')
    if request.get('review_status')!='human_reviewed':
        raise ValueError('Request must have review_status "human_reviewed" before a live assessment')
    request_id=_required_text(request.get('request_id'),'request_id')
    reviewer=_required_text(request.get('reviewed_by'),'reviewed_by')
    requirement_id=_required_text(request.get('requirement_id'),'requirement_id')
    if requirement_id!=SUPPORTED_REQUEST_ID:
        raise ValueError(f'This demo supports only {SUPPORTED_REQUEST_ID}; use the matching scoped request')
    change_id=_required_text(request.get('change_id'),'change_id')
    title=_required_text(request.get('title'),'title')
    requirement_text=_required_text(request.get('requirement_text'),'requirement_text')
    effective_date=_required_text(request.get('effective_date'),'effective_date')
    date.fromisoformat(effective_date)
    scope=request.get('scope')
    if not isinstance(scope,dict):raise ValueError('Request field scope must be an object')
    addressees=scope.get('addressee_types');jurisdictions=scope.get('jurisdictions')
    if not isinstance(addressees,list) or 'credit_institution' not in addressees:
        raise ValueError('scope.addressee_types must include credit_institution')
    if not isinstance(jurisdictions,list) or not {'EU','IE'}.issubset(set(jurisdictions)):
        raise ValueError('scope.jurisdictions must include EU and IE for the Northstar scenario')
    citations=request.get('source_citations')
    if not isinstance(citations,list) or not citations:raise ValueError('Request must include at least one source citation')
    normalized_citations=[]
    source_id='SRC-REQUEST-'+digest(request_id)[:16].upper()
    for index,citation in enumerate(citations,1):
        if not isinstance(citation,dict):raise ValueError('Each source citation must be an object')
        url=_required_text(citation.get('url'),f'source_citations[{index}].url')
        if urlparse(url).scheme!='https' or not urlparse(url).netloc:
            raise ValueError('Each source citation URL must be an HTTPS URL')
        normalized_citations.append(dict(
            citation_id=f'CIT-{request_id}-{index:02d}',source_id=source_id,
            locator_type='paragraph',locator=_required_text(citation.get('locator'),f'source_citations[{index}].locator'),
            evidence_type='reviewed_request_excerpt',
            evidence_text=_required_text(citation.get('excerpt'),f'source_citations[{index}].excerpt'),
            supports_fields=['requirement_text','scope','effective_date'],verification_status='human_reviewed'))

    files=load_runtime(Path(root))
    requirement=dict(
        requirement_id=requirement_id,change_id=change_id,title=title,requirement_text=requirement_text,
        legal_force=request.get('legal_force','supervisory_expectation'),addressee_types=addressees,jurisdictions=jurisdictions,
        applicability_conditions=[dict(condition_id='COND-'+requirement_id+'-ENTITY',
            description='Confirm Northstar is a credit institution.',condition_type='bank_fact',
            fact_path='01_entity/bank_profile.json#/entity_classification',operator='equals',expected_value=['credit_institution'],
            source_citation_ids=[normalized_citations[0]['citation_id']],evidence_status='reviewed')],
        exclusions_and_exemptions=[],
        compliance_events=[dict(event_type='application',date=effective_date,
            condition='Reviewed request effective date for the Northstar demo scope.',
            source_citation_ids=[normalized_citations[0]['citation_id']],verification_status='human_reviewed',
            extensions={'snci_selector':False})],
        source_citations=normalized_citations,
        required_bank_facts=[dict(fact_ref='03_exposure/lending_portfolio.csv',purpose='Part B SME portfolio exposure.',evidence_status='provided'),
            dict(fact_ref='03_exposure/esg_assessment_snapshot.csv',purpose='Part B sector-data coverage.',evidence_status='provided'),
            dict(fact_ref='04_governance/controls.json',purpose='Part C candidate control investigation.',evidence_status='provided')],
        capability_domains=['credit_risk','esg_risk'],policy_ids=[],control_ids=[],procedure_ids=[],
        current_coverage=dict(rating='unknown',assessment_basis='live_investigation',
            rationale='The reviewed request provides no pre-decided bank capability result.',control_ids=[],
            uncovered_dimensions=[],verification_status='not_assessed'),
        record_status='human_reviewed',synthetic=True,
        provenance=dict(origin='reviewed_upstream_request',source_ids=[source_id],created_at=utcnow(),
            created_by=request_id,last_verified_at=utcnow(),notes=['This is a reviewed input handoff, not live monitoring.']),
        annotation=dict(label_status='reviewed',annotated_by=request_id,reviewed_by=reviewer,reviewed_at=utcnow(),notes=[]),
        missing_evidence=[],extensions=dict(request_id=request_id,portfolio_scope=scope.get('portfolio','existing SME lending'),
            assessment_contract_version='request-intake-v1',jurisdiction_basis='institution'))
    files['regulatory_sources/requirements.json']=dict(schema_version='1.0.0',dataset_scope='reviewed_request',
        as_of_date=files['01_entity/bank_profile.json']['as_of_date'],requirements=[requirement])
    files['regulatory_sources/change_register.json']=dict(sources=[dict(source_id=source_id,title=title,url=citations[0]['url'],
        verification_status='human_reviewed',content_sha256=None)],changes=[dict(change_id=change_id,topic_key='esg_risk_management',
        title=title,application_events=copy.deepcopy(requirement['compliance_events']),source_ids=[source_id],
        requirement_ids=[requirement_id],review_status='human_reviewed')])
    return request,files,source_id


def open_reviewed_request_case(store, request_file, mode, goal=None, root=DEFAULT_ROOT, nonce=None):
    request,files,source_id=load_reviewed_request(request_file,root)
    manifest=json.loads((Path(root)/'dataset_manifest.json').read_text())
    goal=goal or ('Assess the reviewed regulatory request "'+request['title']+'" for Northstar\'s existing SME lending book. '
        'Produce one supported Part B exposure finding and one scoped Part C capability/action finding; do not assess unrelated requirements.')
    key=digest(dict(request=request,inputs=files,goal=goal,mode=mode,nonce=nonce))
    case_id,created=store.create_case(goal,files,manifest['dataset_version'],manifest['scenario_as_of_date'],mode,key)
    if created:
        store.put(case_id,'SourceVersion','reviewed-request',dict(source_id=source_id,request_id=request['request_id'],
            review_status='human_reviewed',reviewed_by=request['reviewed_by'],intake_mode='reviewed_structured_request',
            workflow_policy='trusted_request_part_b_c_first',
            note='Upstream detection is out of scope for this case; the request is the trusted, human-reviewed detection result. '
                 'Start with Part B/Part C bank investigation; source-version comparison is optional.'),
            ['file:regulatory_sources/requirements.json'],'recorded')
    return case_id,created

def open_registered_case(store,goal,mode,root=DEFAULT_ROOT,nonce=None):
    root=Path(root)
    files=load_runtime(root)
    manifest=json.loads((root/'dataset_manifest.json').read_text())
    change=next(c for c in files['regulatory_sources/change_register.json']['changes'] if c['topic_key']=='esg_risk_management')
    key=digest(dict(source_id=ESG_SOURCE,change=change,inputs=files,goal=goal,mode=mode,nonce=nonce))
    case_id,created=store.create_case(goal,files,manifest['dataset_version'],manifest['scenario_as_of_date'],mode,key)
    if created:
        store.put(case_id,'SourceVersion','registered-event',dict(source_id=ESG_SOURCE,change=change,
            intake_mode='registered_source_replay',observed_at=utcnow(),content_sha256=None,
            note='Replays the registered candidate. No current network monitoring or complete amendment audit was performed.'),
            ['file:regulatory_sources/change_register.json'],'recorded')
    return case_id,created


def register_local_snapshot(store,case_id,version,artifact,artifact_root):
    """Local CLI/service only. A user-supplied file is an unverified official candidate."""
    inputs=store.inputs(case_id)
    pair=inputs['regulatory_sources/version_pairs.json'][0]
    metadata=next((pair[k] for k in ('older','newer') if pair[k]['identifier']==version),None)
    if not metadata or urlparse(metadata['url']).hostname!='www.eba.europa.eu':
        raise ValueError('Version is not in the selected official ESG source registry')
    artifact=Path(artifact)
    if not artifact.is_file() or artifact.suffix.lower() not in ('.pdf','.txt'):
        raise ValueError('Provide an existing .pdf or .txt source candidate')
    if not 0<artifact.stat().st_size<=30_000_000:raise ValueError('Source file must be nonempty and at most 30 MB')
    raw=artifact.read_bytes()
    if artifact.suffix.lower()=='.pdf' and not raw.startswith(b'%PDF-'):raise ValueError('Not a PDF file')
    if artifact.suffix.lower()=='.txt':raw.decode('utf-8')
    sha=hashlib.sha256(raw).hexdigest();base=Path(artifact_root).resolve();base.mkdir(parents=True,exist_ok=True)
    target=base/(sha+artifact.suffix.lower())
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=sha:raise ValueError('Stored source artefact was modified')
    if not target.exists():shutil.copyfile(artifact,target)
    key=version+':'+sha
    prior=store.get(case_id,'SourceVersion',key)
    if prior:return prior
    return store.put(case_id,'SourceVersion',key,dict(metadata,source_id=ESG_SOURCE,
        local_artifact=target.name,content_sha256=sha,acquisition='user_supplied_unverified',
        authenticity_status='needs_review',registered_at=utcnow()),['source:'+ESG_SOURCE],'recorded')


def _text(record,artifact_root):
    root=Path(artifact_root).resolve();path=(root/record['local_artifact']).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('Missing or invalid source path')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=record['content_sha256']:raise ValueError('Source hash mismatch')
    if path.suffix=='.pdf':
        try:from pypdf import PdfReader
        except ImportError:raise ValueError('PDF extraction needs pypdf; retain original file and install dependency before extraction')
        return '\n'.join(f'[Page {i+1}]\n{p.extract_text() or ""}' for i,p in enumerate(PdfReader(path).pages))
    return data.decode('utf-8')


def compare_versions(store,case_id,artifact_root):
    pair=copy.deepcopy(store.inputs(case_id)['regulatory_sources/version_pairs.json'][0])
    rows=[o['payload'] for o in store.objects(case_id,'SourceVersion') if o['payload'].get('local_artifact')]
    selected=[]
    for side in ('older','newer'):
        candidates=[r for r in rows if r['identifier']==pair[side]['identifier']]
        if len(candidates)>1:return dict(status='ambiguous_versions',reason='Select/review conflicting source hashes before comparison')
        if not candidates:return dict(status='insufficient_source_snapshots',missing_identifier=pair[side]['identifier'],comparison_kind=pair['comparison_kind'])
        selected.append(candidates[0])
    texts=[_text(r,artifact_root) for r in selected]
    if any(not t.strip() for t in texts):return dict(status='insufficient_extracted_text')
    diff='\n'.join(difflib.unified_diff(texts[0].splitlines(),texts[1].splitlines(),fromfile=selected[0]['identifier'],tofile=selected[1]['identifier'],lineterm=''))
    return dict(status='candidate_text_diff',comparison_kind=pair['comparison_kind'],
        diff=diff[:18000],truncated=len(diff)>18000,content_sha256=[r['content_sha256'] for r in selected],
        authenticity_status='needs_review',note='Text comparison of supplied files; consultation is not prior binding law. No authenticity or legal-materiality approval.')


def read_snapshot(store,case_id,identifier,artifact_root,offset=0,limit=6000):
    rows=[o['payload'] for o in store.objects(case_id,'SourceVersion') if o['payload'].get('identifier')==identifier and o['payload'].get('local_artifact')]
    if len(rows)!=1:return dict(status='insufficient_source_snapshots' if not rows else 'ambiguous_versions',identifier=identifier)
    text=_text(rows[0],artifact_root)
    return dict(status='ok',identifier=identifier,text=text[offset:offset+limit],offset=offset,
                has_more=offset+limit<len(text),text_kind='supplied_source_text',authenticity_status='needs_review',
                content_sha256=rows[0]['content_sha256'],official_url=rows[0]['url'])
