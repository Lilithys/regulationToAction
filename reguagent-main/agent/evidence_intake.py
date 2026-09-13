"""Evidence artifact submission and the deterministic closure gate.

Submission is a local human/service action (mirrors source_intake.register_local_snapshot),
not an LLM tool. Content review (does the artifact plausibly support this specific
requirement?) is a separate LLM-tool step in investigation_tools.py. Final human
decisions live only in case_store.py. This module never sets human_review_status or
review_status itself -- it only translates already-decided CaseStore fields into the
literal shape dataset_runtime.closure_gate() expects, so that pure function stays
unmodified and reusable exactly as tested.
"""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path
from case_store import utcnow
from dataset_runtime import closure_gate


def submit_evidence(store, case_id, action_key, evidence_slot, evidence_type, artifact, artifact_root, submitted_by_role_id):
    """Local CLI/service only. A user-supplied file is an unverified candidate until reviewed and decided.

    evidence_slot is the short id from the action's own required_evidence (e.g. 'design');
    the CaseStore Evidence object's own key is the full 'action_key::evidence_slot' composite,
    the same evidence_key used by decide_evidence/read_evidence/review_evidence elsewhere."""
    action = store.get(case_id, 'Action', action_key)
    if not action or action['status'] == 'stale':
        raise ValueError('Action is missing or stale; refresh the plan/action before submitting evidence')
    required = {item['evidence_key']: item for item in action['payload'].get('required_evidence', [])}
    if evidence_slot not in required:
        raise ValueError("evidence_slot is not one of this action's own declared required_evidence items")
    if required[evidence_slot]['evidence_type'] != evidence_type:
        raise ValueError('evidence_type does not match what this action originally declared for this evidence_slot')
    artifact = Path(artifact)
    if not artifact.is_file() or artifact.suffix.lower() not in ('.pdf', '.txt'):
        raise ValueError('Provide an existing .pdf or .txt evidence artefact')
    if not 0 < artifact.stat().st_size <= 30_000_000:
        raise ValueError('Evidence artefact must be nonempty and at most 30 MB')
    raw = artifact.read_bytes()
    if artifact.suffix.lower() == '.pdf' and not raw.startswith(b'%PDF-'):
        raise ValueError('Not a PDF file')
    if artifact.suffix.lower() == '.txt':
        raw.decode('utf-8')
    sha = hashlib.sha256(raw).hexdigest()
    base = Path(artifact_root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = base / (sha + artifact.suffix.lower())
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != sha:
        raise ValueError('Stored evidence artefact was modified')
    if not target.exists():
        shutil.copyfile(artifact, target)
    key = action_key + '::' + evidence_slot
    prior = store.get(case_id, 'Evidence', key)
    if prior and prior['status'] == 'submitted' and prior['payload']['content_sha256'] == sha:
        return prior
    return store.put(case_id, 'Evidence', key, dict(
        action_key=action_key, evidence_key=evidence_slot, evidence_type=evidence_type,
        title=required[evidence_slot]['title'], artifact_path=target.name, content_sha256=sha,
        submitted_by_role_id=submitted_by_role_id, collected_at=utcnow(),
        content_assessment=None, content_rationale=None, human_decision=None,
        note='Submission only; content review and the human verify/reject decision are separate steps.'),
        ['object:Action:' + action_key], 'submitted')


def _evidence_text(record, artifact_root):
    root = Path(artifact_root).resolve()
    path = (root / record['artifact_path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Missing or invalid evidence artefact path')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['content_sha256']:
        raise ValueError('Evidence artefact hash mismatch')
    if path.suffix == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError('PDF extraction needs pypdf; retain original file and install dependency before extraction')
        return '\n'.join(p.extract_text() or '' for p in PdfReader(path).pages)
    return data.decode('utf-8')


def read_evidence_text(store, case_id, evidence_key, artifact_root, offset=0, limit=6000):
    record = store.get(case_id, 'Evidence', evidence_key)
    if not record:
        raise ValueError('Unknown evidence_key')
    text = _evidence_text(record['payload'], artifact_root)
    return dict(status='ok', evidence_key=evidence_key, evidence_type=record['payload']['evidence_type'],
                title=record['payload']['title'], text=text[offset:offset + limit], offset=offset,
                has_more=offset + limit < len(text), content_sha256=record['payload']['content_sha256'])


def evaluate_closure(store, case_id, action_key, artifact_root=None):
    """Read-only. Builds the exact dict shape closure_gate() expects from whatever
    CaseStore Action/Evidence objects currently exist, then calls it unmodified."""
    root = Path(artifact_root) if artifact_root else Path(store.path).parent / 'evidence_artifacts'
    action = store.get(case_id, 'Action', action_key)
    if not action:
        raise ValueError('Unknown action_key')
    evidence_objects = [e for e in store.objects(case_id, 'Evidence') if e['payload'].get('action_key') == action_key]
    translated_action = dict(
        action_id=action_key,
        required_evidence_ids=action['payload'].get('required_evidence_ids', []),
        human_review_status='approved' if action['payload'].get('acceptance_status') == 'accepted' else 'pending',
        reviewed_by=action['payload'].get('accepted_by_role_id'),
        reviewed_at=action['payload'].get('accepted_at'))
    translated_evidence = [dict(
        evidence_id=e['payload']['evidence_key'], action_id=action_key,
        status='collected' if e['status'] in ('submitted', 'verified', 'rejected') and e['payload'].get('content_sha256') else 'required',
        human_review_status='approved' if e['payload'].get('human_decision') == 'verified' else 'pending',
        reviewed_by=e['payload'].get('decided_by_role_id'), reviewed_at=e['payload'].get('decided_at'),
        collected_at=e['payload'].get('collected_at'), artifact_path=e['payload'].get('artifact_path'),
        content_sha256=e['payload'].get('content_sha256')) for e in evidence_objects]
    return closure_gate(translated_action, translated_evidence, root=root)
