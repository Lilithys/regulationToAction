#!/usr/bin/env python3
"""Cross-team invariants in addition to the unchanged Person 1 validator."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from project_paths import RAW_DATA_ROOT
from dataset_runtime import DEFAULT_ROOT,load_runtime,portfolio_metrics,calculate_options,closure_gate

DEFINITIONS={
 'entity_id':('01_entity/bank_profile.json',None),
 'business_line_id':('02_business/business_lines.json',None),
 'product_id':('02_business/products.json',None),
 'requirement_id':('regulatory_sources/requirements.json','requirements'),
 'change_id':('regulatory_sources/change_register.json','changes'),
 'source_id':('regulatory_sources/change_register.json','sources'),
 'policy_id':('04_governance/policies.json','policies'),
 'control_id':('04_governance/controls.json','controls'),
 'procedure_id':('04_governance/procedures.json','procedures'),
 'process_id':('05_operations/processes.json','processes'),
 'system_id':('05_operations/systems.json','systems'),
 'data_asset_id':('05_operations/data_assets.json','data_assets'),
 'vendor_id':('05_operations/vendors.json','vendors'),
 'function_id':('05_operations/critical_services.json','critical_or_important_functions'),
 'dependency_mapping_id':('05_operations/dependencies.json','dependency_mappings'),
 'role_id':('06_organisation/roles.json',None),
 'cost_centre_id':('06_organisation/cost_centres.json',None),
 'option_id':('07_economics/response_options.json',None),
}
REFS={
 'requirement_ids':'requirement_id','change_id':'change_id','related_change_ids':'change_id',
 'source_ids':'source_id','source_id':'source_id','primary_source_id':'source_id',
 'policy_ids':'policy_id','control_ids':'control_id','procedure_ids':'procedure_id',
 'business_line_ids':'business_line_id','product_ids':'product_id','product_id':'product_id',
 'process_ids':'process_id','affected_process_ids':'process_id','related_process_id':'process_id','processes':'process_id',
 'system_ids':'system_id','affected_system_ids':'system_id','supporting_systems':'system_id','systems_of_record':'system_id','supports_systems':'system_id','systems':'system_id',
 'data_asset_ids':'data_asset_id','affected_data_asset_ids':'data_asset_id','data_assets':'data_asset_id',
 'vendor_id':'vendor_id','vendor_ids':'vendor_id','affected_vendor_ids':'vendor_id','vendors':'vendor_id',
 'critical_service_ids':'function_id','function_id':'function_id',
 'owner_role_id':'role_id','accountable_role_id':'role_id','performer_role_id':'role_id','backup_role_id':'role_id','role_id':'role_id',
 'cost_centre_id':'cost_centre_id','owner_cost_centre_id':'cost_centre_id',
 'affected_control_ids':'control_id','split_from_requirement_id':'requirement_id',
}


def validate(root=DEFAULT_ROOT):
 root=Path(root);files=load_runtime(root);errors=[];checks=[]
 def check(condition,message):
  (checks if condition else errors).append(message)
 indexes={}
 for key,(path,envelope) in DEFINITIONS.items():
  data=files[path];rows=data[envelope] if envelope else data
  if isinstance(rows,dict):rows=[rows]
  ids=[r[key] for r in rows]
  check(len(ids)==len(set(ids)),f'Unique definitions: {key}')
  indexes[key]=set(ids)
 allids=[x for s in indexes.values() for x in s]
 check(len(allids)==len(set(allids)),'Global definition IDs do not collide')
 def walk(x,where):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in REFS and v is not None:
     vals=v if isinstance(v,list) else [v]
     for item in vals:
      if isinstance(item,str):check(item in indexes[REFS[k]],f'{where}.{k} resolves: {item}')
    if k in ['fact_ref','fact_path'] and isinstance(v,str):
     path,_,pointer=v.partition('#')
     check(path in files,f'Fact file exists: {v}')
     if path in files and pointer:
      obj=files[path]
      try:
       for part in pointer.strip('/').split('/'):
        part=part.replace('~1','/').replace('~0','~')
        obj=obj[int(part)] if isinstance(obj,list) else obj[part]
      except (KeyError,IndexError,ValueError,TypeError):check(False,f'Unresolvable JSON pointer: {v}')
    walk(v,where+'.'+k)
  elif isinstance(x,list):
   for i,v in enumerate(x):walk(v,where+f'[{i}]')
 for p,d in files.items():walk(d,p)
 actions=json.loads((root/'evaluation_ground_truth/reference_actions.json').read_text())
 evidence=json.loads((root/'evaluation_ground_truth/reference_evidence.json').read_text())
 walk(actions,'reference_actions');walk(evidence,'reference_evidence')
 amap={a['action_id']:a for a in actions};emap={e['evidence_id']:e for e in evidence}
 check(len(amap)==len(actions),'Unique action template IDs')
 check(len(emap)==len(evidence),'Unique evidence template IDs')
 for a in actions:
  check(set(a['required_evidence_ids'])=={e['evidence_id'] for e in evidence if e['action_id']==a['action_id']},f'Action/evidence reciprocal: {a["action_id"]}')
  check(a['estimated_total_cost_eur']==a['estimated_internal_cost_eur']+a['estimated_external_cost_eur'],f'Action cost arithmetic: {a["action_id"]}')
  check(not closure_gate(a,evidence,root)['can_close'],f'Required evidence cannot close action: {a["action_id"]}')
 for e in evidence:
  check(e['action_id'] in amap,f'Evidence action resolves: {e["evidence_id"]}')
  check(e['expected_by']<=amap[e['action_id']]['target_date'],f'Evidence due by action target: {e["evidence_id"]}')
 with (root/'evaluation_ground_truth/reference_raci.csv').open(newline='') as f:raci=list(csv.DictReader(f))
 for a in actions:
  roles=[r for r in raci if r['action_id']==a['action_id']]
  check(sum(r['raci']=='A' for r in roles)==1,f'Exactly one accountable role: {a["action_id"]}')
  check(any(r['raci']=='R' and r['role_id']==a['owner_role_id'] for r in roles),f'Responsible owner matches RACI: {a["action_id"]}')
 summary=files['03_exposure/portfolio_summary.json'];b=summary['non_overlapping_balances']
 check(sum(b.values())==summary['total_assets'],'Asset components sum to total assets')
 check(sum(b[k] for k in ['consumer_loans','home_improvement_loans','sme_working_capital','mortgages'])==summary['loan_book_total'],'Loan subportfolios sum to loan book')
 check(sum(float(r['outstanding_balance_eur_millions']) for r in files['03_exposure/lending_portfolio.csv'])+b['mortgages']==summary['loan_book_total'],'Cohort amounts plus mortgages reconcile')
 check(sum(float(r['market_value_eur_millions']) for r in files['03_exposure/trading_book.csv'])==b['liquidity'],'Liquidity positions reconcile')
 metrics=portfolio_metrics(files)
 check(metrics['sme_borrower_count']==summary['sme_borrowers'],'SME borrower population reconciles')
 check(metrics['missing_or_broad_nace_borrower_pct']==20,'Borrower-weighted NACE incompleteness is 20%')
 loans={r['portfolio_record_id'] for r in files['03_exposure/lending_portfolio.csv']}
 check(all(r['portfolio_record_id'] in loans for r in files['03_exposure/esg_assessment_snapshot.csv']),'ESG snapshots join existing cohorts')
 check(len(files['05_operations/critical_services.json']['critical_or_important_functions'])==5,'Five supplied critical functions preserved')
 for r in files['07_economics/change_capacity.csv']:
  check(int(r['remaining_days'])==int(r['available_days'])-int(r['committed_days']),f'Capacity arithmetic: {r["role_id"]}')
 for r in files['03_exposure/payments.csv']:
  difference=abs(round(int(r['transaction_count'])*(1-float(r['success_rate_pct'])/100))-int(r['failed_payment_count']))
  check(difference<=1,f'Payment failures agree with rounded success rate: {r["payment_metric_id"]}')
 for s in files['regulatory_sources/change_register.json']['sources']:
  if s['content_sha256']:
   check(s['content_sha256']!=hashlib.sha256(b'').hexdigest(),f'Source hash is not empty response: {s["source_id"]}')
 for r in files['regulatory_sources/requirements.json']['requirements']:
  check(not (r['record_status']=='verified' and any(m['blocking'] for m in r['missing_evidence'])),f'No verified record with blocking evidence: {r["requirement_id"]}')
  check(r['annotation']['label_status']!='gold','No model-only gold label')
 forbidden=['frtb_applicability_assessment','overall_esg_risk_band','expected_applicability','expected_exposure','expected_outcome','expected_action_ids','esg_risk_assessment_priority']
 serialized=json.dumps(files)
 check(all('"'+s+'"' not in serialized for s in forbidden),'Expected assessment labels absent from agent input')
 check(files['08_evidence/actions.json']==[],'Initial runtime contains no answer action plan')
 check(files['08_evidence/evidence_register.json']==[],'Initial runtime contains no answer evidence plan')
 check('current_coverage' not in json.dumps(load_runtime(root,'mapping')),'Blind mapping input removes curated coverage answer')
 check('regulatory_sources/requirements.json' not in load_runtime(root,'extraction'),'Blind extraction input removes extracted answer')
 calc=calculate_options(files)
 for o in calc['options']:
  check(o['scenarios']['low']['three_year_tco_eur']<=o['scenarios']['base']['three_year_tco_eur']<=o['scenarios']['high']['three_year_tco_eur'],f'Monotone cost intervals: {o["option_id"]}')
  check(o['expected_risk_cost_eur'] is None,'Unknown risk inputs are not zero cost')
 for entry in json.loads((root/'calibration/input_inventory.json').read_text()):
  p=RAW_DATA_ROOT/entry['path']
  check(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256'],f'Original input unchanged: {entry["path"]}')
 warnings=[
  'All legal interpretations remain silver and require qualified human review.',
  'EUR-Lex operative-text currency audit and FRTB 2026 OJ status remain unresolved.',
  'Official full-text version pair is not locally preserved; change-diff evaluation is not ready.',
  'Existing bank snapshots retain June 2026 dates; do not claim live or point-in-time backtesting readiness.',
  'Delivery-team capacity, risk-loss model and revenue response are unknown; no approved recommendation.',
  'No control-operation artefact or human sign-off is present.'
 ]
 return dict(structural_pass=not errors,passed_checks=len(checks),errors=errors,warnings=warnings,
             legal_signoff_ready=False,full_change_detection_ready=False,metrics=metrics)


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=DEFAULT_ROOT);ap.add_argument('--output',type=Path)
 a=ap.parse_args();r=validate(a.root)
 if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['structural_pass'] else 1)


if __name__=='__main__':main()
