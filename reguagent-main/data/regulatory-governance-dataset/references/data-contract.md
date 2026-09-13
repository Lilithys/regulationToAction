# Person 1 Data Contract

This reference is normative when the repository has no existing schema. Read it before creating or changing any Person 1 file. A repository-owned schema takes precedence; document any compatibility mapping instead of maintaining two competing shapes.

## Conventions

- JSON is UTF-8, two-space indented, with one trailing newline.
- Dates use `YYYY-MM-DD`; timestamps use UTC ISO 8601 ending in `Z`.
- Unknown nullable scalar values are `null`, not `"unknown"`, `"TBC"`, or an invented value.
- Unknown collections are empty arrays plus a `missing_evidence` entry explaining what is absent.
- Every listed key is required unless marked optional. Empty arrays and `null` are valid only where stated.
- Controlled enum values are lowercase snake case.
- Top-level records are sorted by primary ID. ID-reference arrays are sorted and deduplicated.
- Put project-specific extras inside an optional `extensions` object instead of creating near-duplicate core fields.

## Common envelope

Every file has these required fields:

```json
{
  "schema_version": "1.0.0",
  "dataset_scope": "person_1_regulatory_governance",
  "as_of_date": "2026-09-04",
  "generated_at": "2026-09-04T12:00:00Z",
  "<records_key>": []
}
```

The records key is fixed by path:

| Path | Records key | Additional top-level key |
| --- | --- | --- |
| `regulatory_sources/change_register.json` | `changes` | `sources` |
| `regulatory_sources/requirements.json` | `requirements` | none |
| `04_governance/policies.json` | `policies` | none |
| `04_governance/controls.json` | `controls` | none |
| `04_governance/procedures.json` | `procedures` | none |

All five envelopes must use identical `schema_version`, `dataset_scope`, and `as_of_date` values. `generated_at` may differ only when files were intentionally updated in separate atomic operations.

## Common record objects

### `provenance`

```json
{
  "origin": "authoritative_external_source",
  "source_ids": ["SRC-IPS-EURLEX-2024-886"],
  "created_at": "2026-09-04T12:00:00Z",
  "created_by": "coding_agent",
  "last_verified_at": "2026-09-04T12:00:00Z",
  "notes": []
}
```

Required fields and enums:

- `origin`: `authoritative_external_source`, `provided_internal_record`, or `synthetic_bank_design`.
- `source_ids`: source IDs supporting the record. It is non-empty for external records. For synthetic internal records it contains any scenario-design source IDs available, otherwise `[]`.
- `created_at`: creation timestamp. Preserve it on refresh.
- `created_by`: a tool-neutral label such as `coding_agent`, `human_author`, or a supplied project identity. Do not claim a human identity.
- `last_verified_at`: timestamp or `null` for an unverified internal record.
- `notes`: concise provenance notes.

### `annotation`

```json
{
  "label_status": "silver",
  "annotated_by": "coding_agent",
  "reviewed_by": null,
  "reviewed_at": null,
  "notes": []
}
```

- `label_status`: `unreviewed`, `silver`, or `gold`.
- `gold` requires documented human review against cited official text.
- `reviewed_by` and `reviewed_at` are nullable; neither may be invented.
- Annotation is about source/extraction quality, never the expected end-to-end exposure label.

### `missing_evidence`

```json
[
  {
    "field": "owner_role_id",
    "reason": "The shared roles file is not available.",
    "required_input": "06_organisation/roles.json containing the approved owner role",
    "responsible_scope": "person_4",
    "blocking": false
  }
]
```

- `responsible_scope`: `person_1`, `person_2`, `person_3`, `person_4`, `legal_reviewer`, or `user`.
- `blocking` means the record cannot truthfully be marked `verified`, not that the whole run must stop.
- Use `record_status: "insufficient_evidence"` when a necessary fact is absent. Use `needs_review` for an unresolved interpretation, conflict, or human-review requirement.

## `change_register.json`

Canonical shape:

```json
{
  "schema_version": "1.0.0",
  "dataset_scope": "person_1_regulatory_governance",
  "as_of_date": "2026-09-04",
  "generated_at": "2026-09-04T12:00:00Z",
  "sources": [
    {
      "source_id": "SRC-IPS-EURLEX-2024-886",
      "title": "Regulation (EU) 2024/886",
      "publisher": "Official Journal of the European Union",
      "document_identifier": "CELEX:32024R0886",
      "source_type": "official_journal_legal_text",
      "authority_tier": 1,
      "official": true,
      "url": "https://eur-lex.europa.eu/eli/reg/2024/886/oj",
      "language": "en",
      "publication_date": "2024-03-19",
      "retrieved_at": "2026-09-04T12:00:00Z",
      "content_sha256": null,
      "verification_status": "verified",
      "notes": []
    }
  ],
  "changes": [
    {
      "change_id": "REG-IPS-2024-886",
      "topic_key": "instant_payments",
      "title": "Instant credit transfers in euro",
      "short_name": "Instant Payments Regulation",
      "legal_instrument_id": "Regulation (EU) 2024/886",
      "celex": "32024R0886",
      "issuing_body": "European Parliament and Council of the European Union",
      "instrument_type": "eu_regulation",
      "jurisdictions": ["EU", "IE"],
      "legal_status": "in_force",
      "binding_nature": "binding",
      "publication_date": "2024-03-19",
      "entry_into_force_date": "2024-04-08",
      "application_events": [
        {
          "event_type": "application",
          "date": null,
          "applies_to": "An institution class and obligation verified from the instrument",
          "locator": "Article or amending provision",
          "source_ids": ["SRC-IPS-EURLEX-2024-886"],
          "verification_status": "needs_review"
        }
      ],
      "change_summary": "Faithful, non-legal-advice summary of what changed.",
      "amends_or_supersedes": ["Regulation (EU) No 260/2012"],
      "related_change_ids": [],
      "primary_source_id": "SRC-IPS-EURLEX-2024-886",
      "source_ids": ["SRC-IPS-EURLEX-2024-886"],
      "requirement_ids": ["REQ-IPS-VOP-001"],
      "record_status": "needs_review",
      "synthetic": false,
      "provenance": {
        "origin": "authoritative_external_source",
        "source_ids": ["SRC-IPS-EURLEX-2024-886"],
        "created_at": "2026-09-04T12:00:00Z",
        "created_by": "coding_agent",
        "last_verified_at": "2026-09-04T12:00:00Z",
        "notes": []
      },
      "annotation": {
        "label_status": "silver",
        "annotated_by": "coding_agent",
        "reviewed_by": null,
        "reviewed_at": null,
        "notes": []
      },
      "missing_evidence": [
        {
          "field": "application_events[0].date",
          "reason": "The illustrative event has not been verified for a specific institution class.",
          "required_input": "Exact operative provision and institution classification",
          "responsible_scope": "legal_reviewer",
          "blocking": true
        }
      ]
    }
  ]
}
```

### Source enums

- `source_type`: `official_journal_legal_text`, `consolidated_legal_text`, `irish_legislation`, `final_guideline`, `official_guidance`, `official_q_and_a`, `official_decision`, `official_explanatory_page`, `consultation`, `proposal`, or `secondary_discovery`.
- `authority_tier`: integer `1`–`4`, following the skill's source priority.
- `verification_status`: `verified`, `needs_review`, or `unavailable`.
- `content_sha256`: optional SHA-256 of a downloaded source file, otherwise `null`. Never hash a search-results page as if it were the instrument.

### Change enums

- `instrument_type`: `eu_regulation`, `eu_directive`, `eu_delegated_regulation`, `eu_implementing_regulation`, `irish_act`, `irish_statutory_instrument`, `eba_guideline`, `esa_guideline`, `cbi_rule`, `cbi_guidance`, `official_q_and_a`, `proposal`, or `other`.
- `legal_status`: `in_force`, `adopted_not_in_force`, `applicable`, `final_guideline`, `consultation`, `proposal`, `repealed`, `superseded`, or `unknown`.
- `binding_nature`: `binding`, `comply_or_explain`, `supervisory_expectation`, `non_binding`, or `unknown`.
- `application_events[].event_type`: `entry_into_force`, `application`, `transition`, `institution_deadline`, `reporting`, `review`, or `other`.

`publication_date`, `entry_into_force_date`, `application_events[].date`, and `celex` are nullable only when an official source does not provide them or they do not apply; explain the gap in `missing_evidence`. Do not copy the illustrative dates above without rechecking the instrument at runtime.

## `requirements.json`

Canonical shape:

```json
{
  "schema_version": "1.0.0",
  "dataset_scope": "person_1_regulatory_governance",
  "as_of_date": "2026-09-04",
  "generated_at": "2026-09-04T12:00:00Z",
  "requirements": [
    {
      "requirement_id": "REQ-IPS-VOP-001",
      "change_id": "REG-IPS-2024-886",
      "title": "Verification service for payment service users",
      "requirement_text": "One atomic, source-faithful normalized requirement.",
      "legal_force": "obligation",
      "addressee_types": ["payment_service_provider"],
      "jurisdictions": ["EU", "IE"],
      "applicability_conditions": [
        {
          "condition_id": "COND-REQ-IPS-VOP-001-01",
          "description": "A legally relevant condition stated without assuming the bank fact.",
          "condition_type": "bank_fact",
          "fact_path": "01_entity/bank_profile.json#/<field-or-id>",
          "operator": "equals",
          "expected_value": ["payment_service_provider"],
          "source_citation_ids": ["CIT-REQ-IPS-VOP-001-01"],
          "evidence_status": "insufficient_evidence"
        }
      ],
      "exclusions_and_exemptions": [],
      "compliance_events": [
        {
          "event_type": "institution_deadline",
          "date": null,
          "condition": "The institution class to which this date applies",
          "source_citation_ids": ["CIT-REQ-IPS-VOP-001-01"],
          "verification_status": "needs_review"
        }
      ],
      "source_citations": [
        {
          "citation_id": "CIT-REQ-IPS-VOP-001-01",
          "source_id": "SRC-IPS-EURLEX-2024-886",
          "locator_type": "article",
          "locator": "Exact article/paragraph/subparagraph",
          "evidence_type": "paraphrase",
          "evidence_text": "Short support for the normalized requirement.",
          "supports_fields": ["requirement_text", "applicability_conditions"],
          "verification_status": "verified"
        }
      ],
      "required_bank_facts": [
        {
          "fact_ref": "01_entity/bank_profile.json#/<field-or-id>",
          "purpose": "Determine whether the addressee condition is met.",
          "evidence_status": "insufficient_evidence"
        }
      ],
      "capability_domains": ["payments"],
      "policy_ids": ["POL-PAYMENTS-SECURITY"],
      "control_ids": ["CTRL-VOP-WEB"],
      "procedure_ids": ["PRCD-VOP-WEB"],
      "current_coverage": {
        "rating": "partial",
        "assessment_basis": "person1_governance_only",
        "rationale": "Current control coverage is limited to a documented channel.",
        "control_ids": ["CTRL-VOP-WEB"],
        "uncovered_dimensions": ["mobile_channel"],
        "verification_status": "verified"
      },
      "interpretation_notes": [],
      "record_status": "insufficient_evidence",
      "synthetic": false,
      "provenance": {
        "origin": "authoritative_external_source",
        "source_ids": ["SRC-IPS-EURLEX-2024-886"],
        "created_at": "2026-09-04T12:00:00Z",
        "created_by": "coding_agent",
        "last_verified_at": "2026-09-04T12:00:00Z",
        "notes": []
      },
      "annotation": {
        "label_status": "silver",
        "annotated_by": "coding_agent",
        "reviewed_by": null,
        "reviewed_at": null,
        "notes": []
      },
      "missing_evidence": [
        {
          "field": "required_bank_facts[0]",
          "reason": "The bank's legal entity and PSP classification were not available in the example.",
          "required_input": "01_entity/bank_profile.json with verified entity classification",
          "responsible_scope": "person_2",
          "blocking": true
        }
      ]
    }
  ]
}
```

### Requirement enums and rules

- `legal_force`: `obligation`, `prohibition`, `permission`, `reporting`, `governance`, `monitoring`, `supervisory_expectation`, or `other`.
- `condition_type`: `legal` or `bank_fact`.
- `operator`: `equals`, `not_equals`, `in`, `not_in`, `greater_than`, `less_than`, `exists`, `not_exists`, `all_of`, `any_of`, or `legal_interpretation_required`.
- `evidence_status`: `verified`, `needs_review`, or `insufficient_evidence`.
- `locator_type`: `article`, `paragraph`, `section`, `annex`, `page`, `recital`, `question_answer`, or `other`.
- `evidence_type`: `quote` or `paraphrase`.
- `current_coverage.rating`: `full`, `partial`, `none`, `unknown`, or `not_assessed`.
- `current_coverage.assessment_basis`: `person1_governance_only` or `joined_dataset`.

A requirement must contain one testable duty. Its text must retain actor, action, object, condition/exception, and timing when material. `source_citations` must support the actual requirement, not merely the document's topic.

When `current_coverage.rating` is `partial`, `uncovered_dimensions` is non-empty. When it is `full`, all selected dimensions have active control coverage and `uncovered_dimensions` is empty. When evidence is missing, use `unknown`, not `none`.

## `policies.json`

Canonical policy record:

```json
{
  "policy_id": "POL-PAYMENTS-SECURITY",
  "title": "Payments Security Policy",
  "version": "1.0",
  "lifecycle_status": "active",
  "approval_date": null,
  "effective_date": "2025-01-01",
  "next_review_date": null,
  "owner_role_id": null,
  "purpose": "Defines the fictional bank's current payment-security principles.",
  "scope": {
    "jurisdictions": ["IE"],
    "business_line_ids": ["BL-PAYMENTS"],
    "product_ids": ["PRD-SEPA-INSTANT"],
    "process_ids": [],
    "system_ids": [],
    "data_asset_ids": [],
    "vendor_ids": [],
    "critical_service_ids": []
  },
  "statements": [
    {
      "statement_id": "PST-PAYMENTS-VOP-001",
      "text": "A synthetic current-state policy statement, not copied from a real bank.",
      "requirement_ids": ["REQ-IPS-VOP-001"],
      "implementation_status": "partial",
      "control_ids": ["CTRL-VOP-WEB"]
    }
  ],
  "requirement_ids": ["REQ-IPS-VOP-001"],
  "control_ids": ["CTRL-VOP-WEB"],
  "procedure_ids": ["PRCD-VOP-WEB"],
  "current_state_summary": "Policy intent exists, but implementation is limited to the documented coverage.",
  "record_status": "needs_review",
  "synthetic": true,
  "provenance": {
    "origin": "synthetic_bank_design",
    "source_ids": [],
    "created_at": "2026-09-04T12:00:00Z",
    "created_by": "coding_agent",
    "last_verified_at": null,
    "notes": ["Designed for the agreed synthetic-bank scenario."]
  },
  "annotation": {
    "label_status": "silver",
    "annotated_by": "coding_agent",
    "reviewed_by": null,
    "reviewed_at": null,
    "notes": []
  },
  "missing_evidence": [
    {
      "field": "owner_role_id",
      "reason": "No approved shared role record was available.",
      "required_input": "06_organisation/roles.json",
      "responsible_scope": "person_4",
      "blocking": false
    }
  ]
}
```

The file envelope adds `policies: [<record>]`.

- `lifecycle_status`: `draft`, `active`, `superseded`, `retired`, or `unknown`.
- `statements[].implementation_status`: `implemented`, `partial`, `not_implemented`, or `unknown`.
- `owner_role_id` and all cross-team arrays may be empty/null only with appropriate missing-evidence documentation when material.
- A policy statement expresses intent; it does not prove that a control operates.

## `controls.json`

Canonical control record:

```json
{
  "control_id": "CTRL-VOP-WEB",
  "title": "Web channel verification of payee",
  "objective": "Describe the current synthetic control objective.",
  "control_type": "preventive",
  "execution_mode": "automated",
  "frequency": "per_transaction",
  "lifecycle_status": "active",
  "design_status": "designed",
  "operating_status": "unknown",
  "owner_role_id": null,
  "requirement_ids": ["REQ-IPS-VOP-001"],
  "policy_ids": ["POL-PAYMENTS-SECURITY"],
  "procedure_ids": ["PRCD-VOP-WEB"],
  "business_line_ids": ["BL-PAYMENTS"],
  "product_ids": ["PRD-SEPA-INSTANT"],
  "process_ids": [],
  "system_ids": [],
  "data_asset_ids": [],
  "vendor_ids": [],
  "critical_service_ids": [],
  "coverage": [
    {
      "dimension_type": "channel",
      "dimension_ref": "web",
      "coverage_status": "covered",
      "rationale": "Synthetic scenario fact encoded by this control."
    },
    {
      "dimension_type": "channel",
      "dimension_ref": "mobile",
      "coverage_status": "not_covered",
      "rationale": "Intentional first-demo gap; no mobile control is asserted."
    }
  ],
  "expected_evidence_types": ["configuration record", "test result"],
  "evidence_item_ids": [],
  "gap_flags": [
    {
      "gap_code": "MISSING_CHANNEL_COVERAGE",
      "description": "The mobile channel is not covered by the current control.",
      "status": "open"
    }
  ],
  "record_status": "needs_review",
  "synthetic": true,
  "provenance": {
    "origin": "synthetic_bank_design",
    "source_ids": [],
    "created_at": "2026-09-04T12:00:00Z",
    "created_by": "coding_agent",
    "last_verified_at": null,
    "notes": []
  },
  "annotation": {
    "label_status": "silver",
    "annotated_by": "coding_agent",
    "reviewed_by": null,
    "reviewed_at": null,
    "notes": []
  },
  "missing_evidence": []
}
```

The file envelope adds `controls: [<record>]`.

- `control_type`: `preventive`, `detective`, `corrective`, or `directive`.
- `execution_mode`: `manual`, `automated`, or `hybrid`.
- `lifecycle_status`: `planned`, `active`, `suspended`, `retired`, or `unknown`.
- `design_status`: `not_designed`, `partially_designed`, `designed`, or `unknown`.
- `operating_status`: `not_implemented`, `partially_operating`, `operating`, `failed`, or `unknown`.
- `coverage[].dimension_type`: `channel`, `business_line`, `product`, `process`, `system`, `data_asset`, `vendor`, `critical_service`, `population`, or `other`.
- `coverage[].coverage_status`: `covered`, `partially_covered`, `not_covered`, or `unknown`.
- `gap_flags[].status`: `open`, `accepted`, `remediated`, or `needs_review`.

Do not set `operating_status: "operating"` merely because a synthetic design says a control exists. Operating status requires an existing evidence item or explicit scenario evidence. `expected_evidence_types` describe what would prove operation; they do not prove it.

## `procedures.json`

Canonical procedure record:

```json
{
  "procedure_id": "PRCD-VOP-WEB",
  "title": "Web verification-of-payee procedure",
  "version": "1.0",
  "lifecycle_status": "active",
  "effective_date": "2025-01-01",
  "next_review_date": null,
  "owner_role_id": null,
  "purpose": "Describe how the synthetic bank executes the web-channel control.",
  "trigger": "An in-scope web payment instruction is initiated.",
  "frequency": "per_transaction",
  "scope": {
    "business_line_ids": ["BL-PAYMENTS"],
    "product_ids": ["PRD-SEPA-INSTANT"],
    "process_ids": [],
    "system_ids": [],
    "data_asset_ids": []
  },
  "requirement_ids": ["REQ-IPS-VOP-001"],
  "policy_ids": ["POL-PAYMENTS-SECURITY"],
  "control_ids": ["CTRL-VOP-WEB"],
  "steps": [
    {
      "step_number": 1,
      "action": "Describe one observable procedure action.",
      "performer_role_id": null,
      "system_ids": [],
      "data_asset_ids": [],
      "control_ids": ["CTRL-VOP-WEB"],
      "output_description": "Expected process output, not claimed evidence.",
      "exception_handling": "Escalate under an approved rule or record that the rule is missing."
    }
  ],
  "escalation_conditions": [],
  "expected_evidence_types": ["transaction log", "exception record"],
  "evidence_item_ids": [],
  "record_status": "needs_review",
  "synthetic": true,
  "provenance": {
    "origin": "synthetic_bank_design",
    "source_ids": [],
    "created_at": "2026-09-04T12:00:00Z",
    "created_by": "coding_agent",
    "last_verified_at": null,
    "notes": []
  },
  "annotation": {
    "label_status": "silver",
    "annotated_by": "coding_agent",
    "reviewed_by": null,
    "reviewed_at": null,
    "notes": []
  },
  "missing_evidence": []
}
```

The file envelope adds `procedures: [<record>]`.

- `lifecycle_status`: `draft`, `active`, `superseded`, `retired`, or `unknown`.
- `steps[].step_number` is a positive integer, unique within the procedure, and contiguous from 1.
- Each step is an observable action. Do not put multiple independent actions into one step.
- `performer_role_id`, system IDs, data IDs, and evidence IDs must resolve in shared files or remain empty with missing-evidence documentation.

## Referential-integrity matrix

| From | Field | Must resolve to | Reverse field |
| --- | --- | --- | --- |
| Change | `source_ids`, `primary_source_id` | Source | n/a |
| Change | `requirement_ids` | Requirement | `change_id` |
| Requirement | `source_citations[].source_id` | Source | n/a |
| Requirement | `policy_ids` | Policy | `requirement_ids` |
| Requirement | `control_ids` | Control | `requirement_ids` |
| Requirement | `procedure_ids` | Procedure | `requirement_ids` |
| Policy | `control_ids` | Control | `policy_ids` |
| Policy | `procedure_ids` | Procedure | `policy_ids` |
| Control | `procedure_ids` | Procedure | `control_ids` |
| Policy/control/procedure | `owner_role_id` | Role | project-defined |
| Governance scope | `BL-*`, `PRD-*`, `PROC-*`, `SYS-*`, `DATA-*`, `VND-*` | Person 2/3 file | project-defined |
| Control/procedure | `evidence_item_ids` | Evidence register | project-defined |

Bidirectional equality is required for Person 1 mappings, not merely subset inclusion. An empty reverse link is an error.

## Coverage semantics

Use these meanings consistently:

| Value | Meaning |
| --- | --- |
| `full` | Active controls demonstrably cover every selected dimension of the requirement. |
| `partial` | At least one dimension is covered and at least one is explicitly uncovered or partially covered. |
| `none` | Evidence confirms that no current control maps to the requirement. |
| `unknown` | Evidence is insufficient to decide whether a current control exists or covers the requirement. |
| `not_assessed` | Mapping has intentionally not yet been performed. |

`none` is a positive evidence-backed finding. It is not the default for an empty array.

## Record-status semantics

- `verified`: all assertions material to the record are supported and cross-file references resolve. For external requirements, at least one official located citation is verified.
- `needs_review`: sources exist, but legal interpretation, currency, mapping, or human approval remains unresolved.
- `insufficient_evidence`: a fact necessary to make the record's material assertion is missing.

The most conservative applicable status wins. A `verified` parent may reference a separate child needing review only if the parent's material assertion does not depend on that unresolved child; explain this in provenance notes.
