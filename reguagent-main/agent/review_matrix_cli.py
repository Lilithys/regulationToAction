#!/usr/bin/env python3
"""Optional AHP method configuration; explicit version-bound human confirmation."""
import copy
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_paths import METHOD_REGISTRY
from exposure_esg import (EXPOSURE_DIMENSIONS, CONFIDENCE_DIMENSIONS, METHOD_VERSION,
                          ahp_weights, matrix_from_pairs, draft_pairwise_matrix_prompt)

DEFAULT_REGISTRY_PATH = METHOD_REGISTRY


def context_binding(requirement_id, dimension_set, dimension_names, context):
    if not context or not context.get('requirement_text') or not context.get('source_citations'):
        raise ValueError('Requirement text and citations are required; an ID alone is not context.')
    if context.get('requirement_id') != requirement_id:
        raise ValueError('Requirement context ID mismatch.')
    if not context.get('dataset_version') or not context.get('scope_version'):
        raise ValueError('Dataset and scope versions are required.')
    payload = dict(requirement_id=requirement_id, dimension_set=dimension_set,
                   dimension_names=dimension_names, method_version=METHOD_VERSION, context=context)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def draft_pairwise_matrix(requirement_id, dimension_set, dimension_names, requirement_context):
    from llm import complete
    system, user = draft_pairwise_matrix_prompt(requirement_id, dimension_set, dimension_names, requirement_context)
    pairs = json.loads(complete(system, user, max_tokens=2000))
    matrix_from_pairs(pairs, dimension_names)
    return dict(requirement_id=requirement_id, dimension_set=dimension_set, dimension_names=dimension_names,
                pairs=pairs, status='draft', drafted_by='llm', drafted_at=datetime.now(timezone.utc).isoformat())


def run_review_session(draft, reviewer):
    if not reviewer or not reviewer.strip():
        raise ValueError('Named reviewer/role is required; there is no default approver.')
    draft = copy.deepcopy(draft)
    print(f"\n=== 待审核: {draft['requirement_id']} · {draft['dimension_set']} ===")
    for pair in draft['pairs']:
        print(f"  {pair['dimension_a']} vs {pair['dimension_b']}: 比例={pair['ratio']} 理由: {pair.get('reasoning', '')}")
    decision = input('确认输入 y，修改输入 adjust，其他输入取消：').strip().lower()
    if decision == 'adjust':
        for pair in draft['pairs']:
            value = input(f"  {pair['dimension_a']} vs {pair['dimension_b']} [回车保留{pair['ratio']}]：").strip()
            if value:
                pair['original_ratio'] = pair['ratio']
                pair['ratio'] = float(value)
                pair['adjusted_by'] = reviewer
        # Validate the amended table before requesting its final explicit approval.
        ahp_weights(matrix_from_pairs(draft['pairs'], draft['dimension_names']), draft['dimension_names'])
        decision = input('修改后的矩阵确认输入 y，其他输入取消：').strip().lower()
    if decision != 'y':
        draft['status'] = 'cancelled'
        for field in ('confirmed_by', 'confirmed_at'):
            draft.pop(field, None)
        return draft
    weights, cr = ahp_weights(matrix_from_pairs(draft['pairs'], draft['dimension_names']), draft['dimension_names'])
    draft.update(status='confirmed', confirmed_by=reviewer.strip(), confirmed_at=datetime.now(timezone.utc).isoformat(),
                 weights=weights, consistency_ratio=cr)
    return draft


def load_confirmed_weights(requirement_id, dimension_set, dimension_names,
                           registry_path=DEFAULT_REGISTRY_PATH, *, requirement_context=None):
    if requirement_context is None:
        return None  # unversioned legacy approval is retained, never silently reused
    binding = context_binding(requirement_id, dimension_set, dimension_names, requirement_context)
    registry_path = Path(registry_path)
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    record = registry.get(f'{requirement_id}::{dimension_set}')
    if not (record and record.get('status') == 'confirmed' and record.get('confirmed_by')
            and record.get('confirmed_at') and record.get('context_sha256') == binding
            and record.get('dimension_names') == dimension_names and record.get('method_version') == METHOD_VERSION):
        return None
    weights, cr = ahp_weights(matrix_from_pairs(record['pairs'], dimension_names), dimension_names)
    return weights, cr, record


def confirm_and_weigh(requirement_id, dimension_set, dimension_names, reviewer,
                      registry_path=DEFAULT_REGISTRY_PATH, *, requirement_context=None):
    binding = context_binding(requirement_id, dimension_set, dimension_names, requirement_context)
    cached = load_confirmed_weights(requirement_id, dimension_set, dimension_names, registry_path,
                                    requirement_context=requirement_context)
    if cached:
        return cached
    draft = draft_pairwise_matrix(requirement_id, dimension_set, dimension_names, requirement_context)
    confirmed = run_review_session(draft, reviewer)
    if confirmed['status'] != 'confirmed':
        raise PermissionError('Matrix review cancelled; no confirmation was saved.')
    weights, cr = ahp_weights(matrix_from_pairs(confirmed['pairs'], dimension_names), dimension_names)
    confirmed.update(context_sha256=binding, method_version=METHOD_VERSION,
                     requirement_context=copy.deepcopy(requirement_context))
    registry_path = Path(registry_path)
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
    key = f'{requirement_id}::{dimension_set}'
    if key in registry:
        registry.setdefault('_history', []).append(copy.deepcopy(registry[key]))
    registry[key] = confirmed
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=registry_path.parent, delete=False, encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write('\n')
        temporary = f.name
    os.replace(temporary, registry_path)
    print(f'已保存本版本的明确确认，CR={cr:.4f}。')
    return weights, cr, confirmed


if __name__ == '__main__':
    from dataset_runtime import load_runtime, DEFAULT_ROOT
    files = load_runtime()
    requirement = next(r for r in files['regulatory_sources/requirements.json']['requirements']
                       if r['requirement_id'] == 'REQ-ESG-CREDIT-MONITORING-001')
    context = dict(requirement, dataset_version=json.loads((DEFAULT_ROOT/'dataset_manifest.json').read_text())['dataset_version'],
                   scope_version='existing-sme-product-sector-country-v1')
    reviewer = input('审核人姓名/角色：').strip()
    for name, dims in [('exposure', EXPOSURE_DIMENSIONS), ('field_quality', CONFIDENCE_DIMENSIONS)]:
        confirm_and_weigh(requirement['requirement_id'], name, dims, reviewer, requirement_context=context)
