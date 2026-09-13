"""Regression counterexamples from the architecture review, never model-quality claims."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from itertools import combinations
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from applicability import (assess_requirement_applicability, assess_product_applicability,
    assess_bank_level_applicability, gate5_region_ok, resolve_pointer, eval_condition)
from dataset_runtime import load_runtime, calculate_options
from exposure_esg import (matrix_from_pairs, ahp_weights, portfolio_fact_report, compute_portfolio_exposure,
    score_freshness, score_geography, draft_pairwise_matrix_prompt, EXPOSURE_DIMENSIONS, CONFIDENCE_DIMENSIONS)
from gap_assessment import assess_capability_gap
from test_review_matrix_cli import FAKE_DRAFT, CONTEXT
import review_matrix_cli as review

ASOF = date(2026,9,8)
SME = ['PRD-SME-WORKING-CAPITAL']


class ScopeBoundaries(unittest.TestCase):
    def setUp(self):
        self.files=load_runtime()
        self.bank=self.files['01_entity/bank_profile.json']
        self.products=self.files['02_business/products.json']
        self.req=next(r for r in self.files['regulatory_sources/requirements.json']['requirements'] if r['requirement_id']=='REQ-ESG-CREDIT-MONITORING-001')
        self.product=next(p for p in self.products if p['product_id']==SME[0])

    def assess(self):return assess_requirement_applicability(self.req,self.bank,self.products,ASOF)

    def test_null_entity_is_unknown_not_exempt(self):
        self.bank['entity_classification']=None
        self.assertEqual(self.assess()['legal_scope'],'unknown')

    def test_future_date_does_not_bypass_entity_exclusion(self):
        self.bank['snci_status']=True
        self.bank['entity_classification']='non_financial_corporate'
        r=assess_product_applicability(self.req,self.bank,self.product,ASOF)
        self.assertEqual(r['legal_scope'],'out_of_scope')
        self.assertEqual(r['temporal_status'],'before_application_date')

    def test_snci_changes_date_not_scope(self):
        self.bank['snci_status']=True
        r=self.assess()
        self.assertEqual(r['legal_scope'],'in_scope')
        self.assertEqual(r['selected_event']['date'],'2027-01-11')
        self.assertEqual(r['temporal_status'],'before_application_date')

    def test_unknown_snci_preserves_known_scope(self):
        self.bank['snci_status']=None
        r=self.assess()
        self.assertEqual(r['legal_scope'],'in_scope')
        self.assertEqual(r['temporal_status'],'unknown')
        self.assertEqual(r['review_status'],'provisional')

    def test_entity_country_missing_or_outside(self):
        self.bank['headquarters']['country_code']=None
        self.assertEqual(assess_bank_level_applicability(self.req,self.bank,ASOF)['legal_scope'],'unknown')
        self.bank['headquarters']['country_code']='US'
        self.assertEqual(assess_bank_level_applicability(self.req,self.bank,ASOF)['legal_scope'],'out_of_scope')

    def test_product_region_us_is_not_eu(self):
        self.product['markets']=['US']
        self.assertIs(gate5_region_ok(self.product,self.req)[0],False)
        # Institution-level framework remains relevant; reason must not claim US in EU.
        r=assess_product_applicability(self.req,self.bank,self.product,ASOF)
        self.assertEqual(r['legal_scope'],'in_scope')
        self.assertIn('institution, not product market',r['rationale'])

    def test_unknown_markets_for_product_scoped_requirement(self):
        self.req['extensions']['jurisdiction_basis']='product'
        self.product['markets']=[]
        self.assertEqual(assess_product_applicability(self.req,self.bank,self.product,ASOF)['legal_scope'],'unknown')

    def test_novel_product_does_not_disappear(self):
        self.products.append(dict(product_id='PRD-NEW',product_type='new_credit_facility',markets=['IE']))
        r=self.assess()
        self.assertIn('PRD-NEW',r['unresolved_product_ids'])
        self.assertFalse(r['scope_complete'])
        self.assertEqual(r['review_status'],'provisional')

    def test_pointer_supports_arrays_escapes_and_empty_keys(self):
        self.assertEqual(resolve_pointer({'a/b':[{'~':7}]},'#/a~1b/0/~0'),(7,True))
        self.assertEqual(resolve_pointer({'':3},'/'),(3,True))
        self.assertEqual(resolve_pointer([9],'/00'),(None,False))
        r=self.assess()
        refs=[x for p in r['product_results'] for x in p['evidence_references'] if x.get('record_id')]
        self.assertTrue(all('pointer' not in x for x in refs))

    def test_date_branch_shared_and_independent_of_event_order(self):
        self.bank['snci_status']=True
        change=next(c for c in self.files['regulatory_sources/change_register.json']['changes'] if c['topic_key']=='esg_risk_management')
        change['application_events'].reverse()
        due=calculate_options(self.files)['options'][0]['selected_regulatory_due_date']
        self.assertEqual(due,self.assess()['selected_event']['date'])
        self.bank['snci_status']='false'
        self.assertIsNone(calculate_options(self.files)['options'][0]['selected_regulatory_due_date'])


class ReviewBoundaries(unittest.TestCase):
    def test_invalid_pair_tables_fail_before_cr(self):
        dims=['a','b','c']
        good=[dict(dimension_a=a,dimension_b=b,ratio=1) for a,b in combinations(dims,2)]
        cases=[[],good[:-1],good+[good[0]]]
        for value in [0,-1,float('nan'),float('inf'),10,0.01,True,'2']:
            bad=copy.deepcopy(good);bad[0]['ratio']=value;cases.append(bad)
        for a,b in [('a','a'),('a','d'),('a','c')]:
            bad=copy.deepcopy(good);bad[0].update(dimension_a=a,dimension_b=b);cases.append(bad)
        for pairs in cases:
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):matrix_from_pairs(pairs,dims)

    def test_direct_nonreciprocal_matrix_rejected(self):
        with self.assertRaises(ValueError):ahp_weights([[1,2,3],[2,1,2],[1/3,.5,1]],['a','b','c'])

    def test_n_skip_empty_invalid_do_not_confirm_or_mutate(self):
        for answer in ['n','skip','','yes please','no']:
            draft=copy.deepcopy(FAKE_DRAFT)
            with patch('builtins.input',return_value=answer):
                result=review.run_review_session(draft,'Named test reviewer')
            self.assertEqual(result['status'],'cancelled')
            self.assertNotIn('confirmed_by',result)
            self.assertEqual(draft,FAKE_DRAFT)

    def test_cancel_does_not_save_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'registry.json')
            with patch.object(review,'draft_pairwise_matrix',return_value=copy.deepcopy(FAKE_DRAFT)),patch('builtins.input',return_value='n'):
                with self.assertRaises(PermissionError):
                    review.confirm_and_weigh('REQ-TEST','exposure',EXPOSURE_DIMENSIONS,'Reviewer',path,requirement_context=CONTEXT)
            self.assertFalse(path.exists())

    def test_cache_requires_same_context_and_preserves_prior_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'registry.json')
            old={'status':'confirmed','confirmed_by':'Prior human','pairs':[]}
            path.write_text(json.dumps({'REQ-TEST::exposure':old}))
            self.assertIsNone(review.load_confirmed_weights('REQ-TEST','exposure',EXPOSURE_DIMENSIONS,path,requirement_context=CONTEXT))
            with patch.object(review,'draft_pairwise_matrix',return_value=copy.deepcopy(FAKE_DRAFT)),patch('builtins.input',return_value='y'):
                review.confirm_and_weigh('REQ-TEST','exposure',EXPOSURE_DIMENSIONS,'Reviewer',path,requirement_context=CONTEXT)
            self.assertEqual(json.loads(path.read_text())['_history'],[old])
            changed=dict(CONTEXT,scope_version='changed')
            self.assertIsNone(review.load_confirmed_weights('REQ-TEST','exposure',EXPOSURE_DIMENSIONS,path,requirement_context=changed))
            changed=dict(CONTEXT,requirement_text='Changed legal extraction')
            self.assertIsNone(review.load_confirmed_weights('REQ-TEST','exposure',EXPOSURE_DIMENSIONS,path,requirement_context=changed))

    def test_no_context_no_llm_draft(self):
        with self.assertRaises(ValueError):draft_pairwise_matrix_prompt('REQ-TEST','exposure',EXPOSURE_DIMENSIONS)
        _,prompt=draft_pairwise_matrix_prompt('REQ-TEST','exposure',EXPOSURE_DIMENSIONS,CONTEXT)
        self.assertIn(CONTEXT['requirement_text'],prompt)


class EvidenceBoundaries(unittest.TestCase):
    def setUp(self):
        self.criteria=[dict(dimension_type='population',dimension_ref=x) for x in ('new','existing')]
        self.req=dict(requirement_id='REQ-TEST',control_ids=['C1','C2'],extensions={'coverage_criteria':self.criteria})
        self.controls={}
        for i,criterion in enumerate(self.criteria,1):
            cid=f'C{i}'
            self.controls[cid]=dict(control_id=cid,operating_status='operating',evidence_item_ids=[f'E{i}'],
                extensions={'requirement_mappings':[dict(requirement_id='REQ-TEST',support='supported',rationale='Synthetic test scoped mapping',
                    evidence_fields=['objective'],coverage=[dict(criterion,coverage_status='covered')])]})

    def test_union_of_exact_criteria_and_fake_evidence(self):
        r=assess_capability_gap(self.req,self.controls)
        self.assertEqual(r['design_coverage'],'covered')
        self.assertEqual(r['status'],'partial')
        self.assertEqual(r['operating_evidence'],'unverified')

    def test_other_requirement_coverage_does_not_contribute(self):
        self.controls['C2']['extensions']['requirement_mappings'][0]['requirement_id']='REQ-OTHER'
        r=assess_capability_gap(self.req,self.controls)
        self.assertEqual(r['design_coverage'],'partial')
        self.assertEqual(r['criteria_results'][1]['coverage_status'],'unknown')

    def test_empty_coverage_cannot_be_evidenced(self):
        for c in self.controls.values():c['extensions']['requirement_mappings'][0]['coverage']=[]
        self.assertEqual(assess_capability_gap(self.req,self.controls)['status'],'insufficient_evidence')

    def test_evidence_must_cover_every_criterion_and_match_content_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'test.txt');path.write_text('Synthetic narrow test artifact')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            evidence=[dict(evidence_id=f'E{i}',control_id=f'C{i}',requirement_ids=['REQ-TEST'],tested_criteria=[criterion],
                status='accepted',human_review_status='approved',reviewed_by='SIMULATED TEST REVIEWER',reviewed_at='2026-09-08',
                collected_at='2026-09-07',valid_through='2026-09-30',content_review_status='supported',test_result='passed',
                artifact_path='test.txt',content_sha256=digest,reviewed_content_sha256=digest) for i,criterion in enumerate(self.criteria,1)]
            self.assertEqual(assess_capability_gap(self.req,self.controls,evidence,root=tmp,as_of=ASOF)['status'],'evidenced')
            self.assertNotEqual(assess_capability_gap(self.req,self.controls,evidence[:1],root=tmp,as_of=ASOF)['status'],'evidenced')
            for field,value in [('requirement_ids',['OTHER']),('valid_through','2026-09-01'),('reviewed_at','2027-01-01'),('content_sha256','0'*64),('reviewed_content_sha256','0'*64),('test_result','failed')]:
                changed=copy.deepcopy(evidence);changed[1][field]=value
                with self.subTest(field=field):
                    self.assertNotEqual(assess_capability_gap(self.req,self.controls,changed,root=tmp,as_of=ASOF)['status'],'evidenced')

    def test_no_mapping_not_missing_without_documented_absence(self):
        self.req['control_ids']=[]
        self.assertEqual(assess_capability_gap(self.req,self.controls)['status'],'insufficient_evidence')
        context=dict(status='complete',requirement_id='REQ-TEST',absence_confirmed=True,reviewed_by='SIMULATED reviewer',
            reviewed_at='2026-09-08',negative_evidence_references=['synthetic_review_document'],searched_control_ids=['C1','C2'])
        self.assertEqual(assess_capability_gap(self.req,self.controls,search_context=context)['status'],'insufficient_evidence')
        # A fabricated negative-evidence ID is no better than a fabricated positive one.
        context['searched_control_ids']=[]
        self.assertEqual(assess_capability_gap(self.req,self.controls,search_context=context)['status'],'insufficient_evidence')

    def test_documented_absence_requires_real_current_review_artifact(self):
        self.req['control_ids'] = []
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp,'absence.txt');path.write_text('Synthetic reviewed absence finding for a narrow test scope.')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            evidence=dict(evidence_id='E-ABSENCE',evidence_type='capability_absence_review',requirement_ids=['REQ-TEST'],
                absence_confirmed=True,searched_control_ids=['C1','C2'],status='accepted',human_review_status='approved',
                reviewed_by='SIMULATED TEST REVIEWER',reviewed_at='2026-09-08',collected_at='2026-09-07',valid_through='2026-09-30',
                content_review_status='supported',artifact_path='absence.txt',content_sha256=digest,reviewed_content_sha256=digest)
            search=dict(status='complete',requirement_id='REQ-TEST',negative_evidence_references=['E-ABSENCE'],searched_control_ids=['C1','C2'])
            self.assertEqual(assess_capability_gap(self.req,self.controls,[evidence],root=tmp,as_of=ASOF,search_context=search)['status'],'missing')
            path.write_text('Changed document invalidates prior review')
            self.assertEqual(assess_capability_gap(self.req,self.controls,[evidence],root=tmp,as_of=ASOF,search_context=search)['status'],'insufficient_evidence')


class PortfolioBoundaries(unittest.TestCase):
    def test_dates_and_country_codes(self):
        for value in ['2027-01-01','bad',None]:self.assertEqual(score_freshness(value,ASOF),0)
        for value in ['somewhere','EU','',None]:self.assertEqual(score_geography(value),0)

    def test_cohort_split_preserves_facts_and_optional_priority(self):
        files=load_runtime();changed=copy.deepcopy(files)
        records=changed['03_exposure/lending_portfolio.csv'];snapshots=changed['03_exposure/esg_assessment_snapshot.csv']
        original=next(r for r in records if r['portfolio_record_id']=='PORT-SME-002')
        snap=next(r for r in snapshots if r['portfolio_record_id']=='PORT-SME-002')
        records.remove(original);snapshots.remove(snap)
        from decimal import Decimal
        for suffix in ('A','B'):
            row=dict(original,portfolio_record_id='PORT-SPLIT-'+suffix,
                outstanding_balance_eur_millions=str(Decimal(original['outstanding_balance_eur_millions'])/2),
                borrower_count=str(int(original['borrower_count'])//2))
            records.append(row);snapshots.append(dict(snap,portfolio_record_id=row['portfolio_record_id']))
        ew=dict(zip(EXPOSURE_DIMENSIONS,[.4,.4,.2]));qw=dict.fromkeys(CONFIDENCE_DIMENSIONS,.25)
        before=portfolio_fact_report(files,SME,ASOF);after=portfolio_fact_report(changed,SME,ASOF)
        self.assertEqual(before['borrower_count'],after['borrower_count'])
        self.assertEqual(before['imprecise_sector_exposure_pct'],after['imprecise_sector_exposure_pct'])
        def without_storage_ids(rows):return [{k:v for k,v in r.items() if k!='source_record_ids'} for r in rows]
        self.assertEqual(without_storage_ids(before['groups']),without_storage_ids(after['groups']))
        self.assertEqual(without_storage_ids(compute_portfolio_exposure(files,SME,ew,qw,ASOF)),
                         without_storage_ids(compute_portfolio_exposure(changed,SME,ew,qw,ASOF)))

    def test_full_fields_do_not_remove_unverified_risk_evidence(self):
        r=portfolio_fact_report(load_runtime(),SME,ASOF)
        group=next(g for g in r['groups'] if 'PORT-SME-006' in g['source_record_ids'])
        self.assertIn('transition_risk_assessment_evidence',group['unresolved_facts'])
        self.assertIn('physical_risk_location_evidence',group['unresolved_facts'])
        self.assertEqual(group['risk_assessment_status'],'unverified')

    def test_mapping_input_keeps_policy_text_without_answer_links(self):
        raw=load_runtime();blind=load_runtime(profile='mapping')
        policies=raw['04_governance/policies.json']['policies']
        projected=blind['04_governance/policies.json']['policies']
        self.assertTrue(all(p['statements'] for p in projected))
        for p,q in zip(policies,projected):
            for a,b in zip(p['statements'],q['statements']):
                self.assertEqual(a['text'],b['text'])
        text=json.dumps(blind)
        self.assertNotIn('requirement_mappings',text)
        self.assertNotIn('current_coverage',text)
