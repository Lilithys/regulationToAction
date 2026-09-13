#!/usr/bin/env python3
"""Offline deterministic baseline demo. Optional AHP: --review-ahp.

This entry point does not yet implement the planned autonomous four-agent loop.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from dataset_runtime import load_runtime, DEFAULT_ROOT
from assessment_pipeline import find_change, find_requirement
from applicability import assess_requirement_applicability, direct_only_products
from review_matrix_cli import confirm_and_weigh
from exposure_esg import CONFIDENCE_DIMENSIONS, EXPOSURE_DIMENSIONS, compute_portfolio_exposure, portfolio_fact_report
from gap_assessment import assess_capability_gap
from response_design import compare_response_options, package_chosen_option
from evidence_closure import check_closure

REQUIREMENT_ID = 'REQ-ESG-CREDIT-MONITORING-001'


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-ahp", action="store_true", help="Optional live method review; requires LLM credentials")
    parser.add_argument("--non-interactive", action="store_true", help="Inspect only; no plan selection or approval")
    args = parser.parse_args()
    if args.review_ahp and args.non_interactive:
        parser.error("--review-ahp requires an interactive review")
    files = load_runtime()
    as_of = date.fromisoformat(files['01_entity/bank_profile.json']['as_of_date'])
    print(f'离线基线演示；场景日期={as_of}；不是实时监管监测或自主 Agent 运行。')

    change = find_change(files, 'esg_risk_management')
    section(f"1. 变更提醒: {change['title']}")
    print(f"来源: {change['primary_source_id']}  法律状态: {change['legal_status']}")

    requirement = find_requirement(files, REQUIREMENT_ID)
    section('2. 适用性判断')
    applicability = assess_requirement_applicability(
        requirement, files['01_entity/bank_profile.json'], files['02_business/products.json'], as_of)
    print(f"法律范围: {applicability['legal_scope']}；时间: {applicability['temporal_status']}；审核: {applicability['review_status']}")
    print(f"依据: {applicability['rationale']}")
    if applicability['applicability'] not in ('direct', 'indirect'):
        print('适用性未确定为direct/indirect，流程在此暂停，交人工确认。')
        return

    section('3. 组合事实与数据缺口')
    product_ids = direct_only_products(applicability)
    facts = portfolio_fact_report(files, product_ids, as_of)
    print(f"SME客户数={facts['borrower_count']}；余额={facts['exposure_eur_millions']}百万欧元")
    print(f"行业分类不精确：客户占比={facts['imprecise_sector_borrower_pct']:.1f}%；余额占比={facts['imprecise_sector_exposure_pct']:.2f}%")
    for group in facts['groups']:
        print(f"  {group['sector']}: 余额={group['exposure_eur_millions']}百万；份额={group['exposure_share_pct']:.2f}%；待核实={group['unresolved_facts']}")
    print('风险评估未验证；行业代理和字段完整度不能证明风险判断正确。')
    if args.review_ahp:
        reviewer = input('方法审核人姓名/角色：').strip()
        context = dict(requirement, dataset_version=json.loads((DEFAULT_ROOT/'dataset_manifest.json').read_text())['dataset_version'],
                       scope_version='existing-sme-product-sector-country-v1')
        try:
            exp, _, _ = confirm_and_weigh(REQUIREMENT_ID, 'exposure', EXPOSURE_DIMENSIONS, reviewer, requirement_context=context)
            quality, _, _ = confirm_and_weigh(REQUIREMENT_ID, 'field_quality', CONFIDENCE_DIMENSIONS, reviewer, requirement_context=context)
        except PermissionError:
            print('方法审核已取消，保留事实输出。')
        else:
            for row in compute_portfolio_exposure(files, product_ids, exp, quality, as_of):
                print(f"  {row['business_unit_id']}: 可选调查优先级={row['exposure_score']}；字段质量指数={row['field_quality_index']}；非风险概率")

    section('4. 能力缺口判断')
    controls_by_id = {c['control_id']: c for c in files['04_governance/controls.json']['controls']}
    for req_id in change['requirement_ids']:
        req = find_requirement(files, req_id)
        gap = assess_capability_gap(req, controls_by_id, files['08_evidence/evidence_register.json'], root=DEFAULT_ROOT, as_of=as_of)
        print(f"  {req_id}: {gap['status']} — {gap['rationale']}")

    section('5. 响应方案对比')
    comparison = compare_response_options(files)
    for o in comparison['options']:
        base = o['scenarios']['base']
        print(f"  {o['option_id']}: 三年TCO={base['three_year_tco_eur']}€"
              f"  截止日可行={o['regulatory_deadline_feasible']}  产能是否足够={o['capacity_sufficient']}")
    print(f"最低基准TCO方案: {comparison['lowest_base_tco_option_id']}（{comparison['recommendation_status']}）")
    option_ids = [o['option_id'] for o in comparison['options']]
    if args.non_interactive:
        print('仅完成基线检查；未选择、指派或批准行动。')
        return
    chosen = input(f"选择草案方案 [{'/'.join(option_ids)}]（回车不选择）：").strip()
    if not chosen:
        print('未选择方案；最低TCO不代表可执行或已批准。')
        return
    if chosen not in option_ids:
        print('无效方案ID，未生成行动。')
        return

    roles = files['06_organisation/roles.json']
    cc_names = {r['cost_centre_id']: r['cost_centre_name'] for r in files['07_economics/operational_costs.csv']}
    action = package_chosen_option(comparison, files['07_economics/response_options.json'], chosen,
                                    next(o['requirement_ids'] for o in files['07_economics/response_options.json'] if o['option_id'] == chosen), roles, cc_names,
                                    ['EVD-ESG-DATA-PROFILE', 'EVD-ESG-DATA-QUALITY-REPORT'], as_of)
    print(f"\n已生成行动: {action['action_id']}")
    print(f"负责人候选（按成本中心）: {action['candidate_owners_by_cost_centre']}")
    print(f"负责人指派状态: {action['owner_assignment_status']}")
    print(f"方案三年TCO（非单个任务成本）: {action['estimated_total_cost_eur']}€")

    section('6. 证据与结案')
    result = check_closure(action, [])
    print(f"能否结案: {result['can_close']}")
    for reason in result['gate']['reasons']:
        print(f"  - {reason}")


if __name__ == '__main__':
    main()
