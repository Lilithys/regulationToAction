"""Phase 5: wraps dataset_runtime.closure_gate() (unmodified) and packages a
non-close result into the queue-item shape the reference frontend already uses --
'closure' while nothing has been submitted yet, 'evidence' once something has been
submitted but review/hash/metadata is still incomplete.
"""
from __future__ import annotations

from dataset_runtime import closure_gate

_UNCOLLECTED = 'required/planned evidence is not collected'


def check_closure(action: dict, evidence: list, root=None) -> dict:
    gate = closure_gate(action, evidence, **({} if root is None else dict(root=root)))
    if gate['can_close']:
        return dict(can_close=True, gate=gate, queue_item=None)

    any_submitted = any(e.get('status') in ('collected', 'accepted') for e in evidence)
    if not any_submitted:
        return dict(can_close=False, gate=gate, queue_item=dict(
            section='closure', payload=dict(actionTitle=action.get('title', action['action_id']))))
    return dict(can_close=False, gate=gate, queue_item=dict(
        section='evidence', payload=dict(items=gate['reasons'])))
