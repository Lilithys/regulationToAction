"""Phase 4: wraps dataset_runtime.calculate_options() (unmodified) and packages a
chosen option into a single action record shaped like
evaluation_ground_truth/reference_actions.json -- read only during development for
its field shape, never as a runtime input (dataset_manifest.json explicitly
excludes evaluation_ground_truth/ from agent inputs).

Deliberately does NOT try to reproduce reference_actions.json's exact
owner/accountable split: that reflects a human judgment call this project's own
data model doesn't fully encode (cost-centre effort share, not a role-to-action
authority table). Instead this surfaces every plausible role per cost centre and
marks the pick as needing human confirmation when more than one resolves -- keeping
the "code decides only what the data actually supports" discipline the rest of this
project follows, rather than silently guessing a single owner.
"""
from __future__ import annotations

from datetime import date

from dataset_runtime import calculate_options


def compare_response_options(files: dict) -> dict:
    return calculate_options(files)


def resolve_cost_centre_owners(effort_days_by_cost_centre: dict, roles: list) -> dict:
    """cost_centre_id -> sorted list of role_ids whose roles.json cost_centre_id matches.
    Empty list means no role in this dataset resolves to that cost centre."""
    by_cc = {}
    for role in roles:
        by_cc.setdefault(role.get('cost_centre_id'), []).append(role['role_id'])
    return {cc: sorted(by_cc.get(cc, [])) for cc in effort_days_by_cost_centre}


def package_chosen_option(comparison: dict, response_options: list, option_id: str, requirement_ids: list,
                           roles: list, cost_centre_names: dict, required_evidence_ids: list, as_of: date) -> dict:
    option = next(o for o in comparison['options'] if o['option_id'] == option_id)
    # calculate_options()'s result only carries the aggregated effort_days total;
    # the per-cost-centre breakdown lives on the raw response_options.json record.
    raw_option = next(o for o in response_options if o['option_id'] == option_id)
    owners_by_cc = resolve_cost_centre_owners(raw_option['effort_days_by_cost_centre'], roles)
    return dict(
        action_id=f'ACT-{option_id}',
        title=f'Adopt {option["option_id"]} for {", ".join(requirement_ids)}',
        addresses_requirement_ids=requirement_ids,
        chosen_option=option,
        candidate_owners_by_cost_centre={cost_centre_names.get(cc, cc): role_ids
                                          for cc, role_ids in owners_by_cc.items()},
        owner_assignment_status=('needs_human_assignment' if any(len(v) != 1 for v in owners_by_cc.values())
                                  else 'single_candidate_per_cost_centre'),
        estimated_total_cost_eur=option['scenarios']['base']['three_year_tco_eur'],
        cost_basis='three_year_tco_eur, base scenario; see scenarios.low/high for sensitivity range',
        required_evidence_ids=required_evidence_ids,
        closure_criteria='All required_evidence_ids collected, hash-verified and human-reviewed (see closure_gate).',
        regulatory_deadline_feasible=option['regulatory_deadline_feasible'],
        capacity_sufficient=option['capacity_sufficient'],
        human_review_status='pending',
        calculation_timestamp=as_of.isoformat(),
        recommendation_basis=comparison['recommendation_status'],
        note=comparison['note'],
    )
