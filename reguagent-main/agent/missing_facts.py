"""Shared tool for unresolved dimensions/facts: try to infer from the same
borrower's other records first, otherwise fall back to a fixture answer (user's
decision: fixture-driven auto-continue for this demo, not a live terminal pause --
contrast with agent/review_matrix_cli.py, which is the one step that does pause).

logic A-B-C/B-Logic.md section 3.4/附录C says this path never fires because each
SME borrower has exactly one loan record. Checking the actual calibrated_v0_2 CSV
shows something more specific: every row's record_grain is "portfolio_cohort" --
calibration_report.md's own change log explains why ("22行改为portfolio cohort，
移除误导性的单户ID"). There is no borrower_id column at all any more, so this
isn't "zero matches happened to be found" for an per-borrower lookup that still
applies; the per-borrower lookup itself no longer has anything to key on. Treated
here as always empty for cohort-grain rows, not as a borrower_id join that would
raise a KeyError.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parent / 'fixtures' / 'interview_answers.json'


def find_related_records(records: list, record: dict) -> list:
    if record.get('record_grain') == 'portfolio_cohort':
        return []  # a cohort has no "this same borrower's other loan" to relate to
    raise ValueError(f"Unhandled record_grain {record.get('record_grain')!r}; this dataset only defines "
                      "portfolio_cohort today, so a non-borrower-keyed relation isn't implemented.")


def attempt_infer_from_related_records(missing_dimension: str, related_records: list) -> dict:
    if not related_records:
        return dict(status='no_related_records')
    return dict(status='cannot_infer')  # no related records exist in this dataset, so no LLM call is needed here


def resolve_missing_fact(fact_id: str, fixture_path: Path = FIXTURE_PATH) -> dict:
    """Returns the fixture record for fact_id. Raises if none is registered --
    this must never silently invent an answer; an unresolved fact stays
    unresolved and the caller should surface it (e.g. as an 'earlyexit'/'fact'
    queue item), which is the correct outcome for facts this fixture deliberately
    leaves open (see agent/fixtures/interview_answers.json)."""
    fixtures = json.loads(fixture_path.read_text())
    entry = next((f for f in fixtures if f['fact_id'] == fact_id), None)
    if entry is None:
        raise KeyError(f'No fixture answer registered for {fact_id} in {fixture_path}; '
                        'this fact stays unresolved for this demo run.')
    return entry
