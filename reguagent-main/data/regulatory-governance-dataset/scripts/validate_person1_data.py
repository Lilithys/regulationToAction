#!/usr/bin/env python3
"""Validate the five Person 1 regulatory/governance dataset files.

The validator uses only the Python standard library. It checks the default data
contract, source provenance, ID shape, bidirectional links, and selected semantic
invariants. Repository-native schemas/tests should still be run when present.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


FILES = {
    "changes": Path("regulatory_sources/change_register.json"),
    "requirements": Path("regulatory_sources/requirements.json"),
    "policies": Path("04_governance/policies.json"),
    "controls": Path("04_governance/controls.json"),
    "procedures": Path("04_governance/procedures.json"),
}

PRIMARY_ID_FIELDS = {
    "sources": ("source_id", r"SRC-[A-Z0-9]+(?:-[A-Z0-9]+)+"),
    "changes": ("change_id", r"REG-[A-Z0-9]+(?:-[A-Z0-9]+)+"),
    "requirements": ("requirement_id", r"REQ-[A-Z0-9]+(?:-[A-Z0-9]+)+"),
    "policies": ("policy_id", r"POL-[A-Z0-9]+(?:-[A-Z0-9]+)+"),
    "controls": ("control_id", r"CTRL-[A-Z0-9]+(?:-[A-Z0-9]+)+"),
    "procedures": ("procedure_id", r"PRCD-[A-Z0-9]+(?:-[A-Z0-9]+)+"),
}

RECORD_STATUSES = {"verified", "needs_review", "insufficient_evidence"}
LABEL_STATUSES = {"unreviewed", "silver", "gold"}
SOURCE_VERIFICATION = {"verified", "needs_review", "unavailable"}
OFFICIAL_HOST_SUFFIXES = (
    "eur-lex.europa.eu",
    "europa.eu",
    "eba.europa.eu",
    "centralbank.ie",
    "irishstatutebook.ie",
)

COMMON_RECORD_KEYS = {
    "record_status",
    "synthetic",
    "provenance",
    "annotation",
    "missing_evidence",
}


@dataclass
class Findings:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")

    def warn(self, location: str, message: str) -> None:
        self.warnings.append(f"{location}: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the five Person 1 regulatory/governance JSON files."
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Dataset root containing regulatory_sources/ and 04_governance/.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a failure exit code when warnings remain.",
    )
    parser.add_argument(
        "--require-first-demo",
        action="store_true",
        help="Require ESG, Instant Payments, DORA, and FRTB topic keys.",
    )
    return parser.parse_args()


def load_json(path: Path, findings: Findings) -> dict[str, Any] | None:
    if not path.is_file():
        findings.error(str(path), "required file is missing")
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        findings.error(str(path), f"cannot parse JSON: {exc}")
        return None
    if not isinstance(value, dict):
        findings.error(str(path), "top-level JSON value must be an object")
        return None
    return value


def is_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def require_keys(
    value: Any, required: Iterable[str], location: str, findings: Findings
) -> bool:
    if not isinstance(value, dict):
        findings.error(location, "must be an object")
        return False
    missing = sorted(set(required) - set(value))
    if missing:
        findings.error(location, f"missing required keys: {', '.join(missing)}")
        return False
    return True


def require_string_list(value: Any, location: str, findings: Findings) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        findings.error(location, "must be an array of strings")
        return []
    if len(value) != len(set(value)):
        findings.error(location, "must not contain duplicate values")
    return value


def check_envelope(
    data: dict[str, Any], records_key: str, path: Path, findings: Findings
) -> list[dict[str, Any]]:
    require_keys(
        data,
        {"schema_version", "dataset_scope", "as_of_date", "generated_at", records_key},
        str(path),
        findings,
    )
    if data.get("schema_version") != "1.0.0":
        findings.error(str(path), "schema_version must be '1.0.0'")
    if data.get("dataset_scope") != "person_1_regulatory_governance":
        findings.error(
            str(path), "dataset_scope must be 'person_1_regulatory_governance'"
        )
    if not is_date(data.get("as_of_date")):
        findings.error(str(path), "as_of_date must be YYYY-MM-DD")
    if not is_timestamp(data.get("generated_at")):
        findings.error(str(path), "generated_at must be an ISO 8601 UTC timestamp")
    records = data.get(records_key)
    if not isinstance(records, list):
        findings.error(str(path), f"{records_key} must be an array")
        return []
    output: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            findings.error(f"{path}:{records_key}[{index}]", "record must be an object")
        else:
            output.append(record)
    return output


def check_provenance(
    record: dict[str, Any], location: str, external: bool, findings: Findings
) -> None:
    require_keys(record, COMMON_RECORD_KEYS, location, findings)
    status = record.get("record_status")
    if status not in RECORD_STATUSES:
        findings.error(location, f"invalid record_status: {status!r}")
    synthetic = record.get("synthetic")
    if not isinstance(synthetic, bool):
        findings.error(location, "synthetic must be a boolean")
    elif external and synthetic:
        findings.error(location, "external regulatory records cannot be synthetic")

    provenance = record.get("provenance")
    if require_keys(
        provenance,
        {"origin", "source_ids", "created_at", "created_by", "last_verified_at", "notes"},
        f"{location}.provenance",
        findings,
    ):
        origin = provenance.get("origin")
        allowed = {
            "authoritative_external_source",
            "provided_internal_record",
            "synthetic_bank_design",
        }
        if origin not in allowed:
            findings.error(f"{location}.provenance", f"invalid origin: {origin!r}")
        if external and origin != "authoritative_external_source":
            findings.error(
                f"{location}.provenance",
                "external records require authoritative_external_source origin",
            )
        if synthetic is True and origin != "synthetic_bank_design":
            findings.error(
                f"{location}.provenance",
                "synthetic records require synthetic_bank_design origin",
            )
        source_ids = require_string_list(
            provenance.get("source_ids"), f"{location}.provenance.source_ids", findings
        )
        if external and not source_ids:
            findings.error(f"{location}.provenance", "external record needs source_ids")
        if not is_timestamp(provenance.get("created_at")):
            findings.error(
                f"{location}.provenance", "created_at must be an ISO 8601 UTC timestamp"
            )
        verified_at = provenance.get("last_verified_at")
        if verified_at is not None and not is_timestamp(verified_at):
            findings.error(
                f"{location}.provenance",
                "last_verified_at must be null or an ISO 8601 UTC timestamp",
            )
        require_string_list(provenance.get("notes"), f"{location}.provenance.notes", findings)

    annotation = record.get("annotation")
    if require_keys(
        annotation,
        {"label_status", "annotated_by", "reviewed_by", "reviewed_at", "notes"},
        f"{location}.annotation",
        findings,
    ):
        label_status = annotation.get("label_status")
        if label_status not in LABEL_STATUSES:
            findings.error(f"{location}.annotation", f"invalid label_status: {label_status!r}")
        if label_status == "gold" and (
            not annotation.get("reviewed_by") or not is_timestamp(annotation.get("reviewed_at"))
        ):
            findings.error(
                f"{location}.annotation",
                "gold annotation requires reviewed_by and reviewed_at",
            )
        require_string_list(annotation.get("notes"), f"{location}.annotation.notes", findings)

    missing = record.get("missing_evidence")
    if not isinstance(missing, list):
        findings.error(f"{location}.missing_evidence", "must be an array")
        return
    has_blocker = False
    for index, item in enumerate(missing):
        item_location = f"{location}.missing_evidence[{index}]"
        if not require_keys(
            item,
            {"field", "reason", "required_input", "responsible_scope", "blocking"},
            item_location,
            findings,
        ):
            continue
        if not isinstance(item.get("blocking"), bool):
            findings.error(item_location, "blocking must be a boolean")
        has_blocker = has_blocker or item.get("blocking") is True
    if status == "verified" and has_blocker:
        findings.error(location, "verified record cannot contain blocking missing evidence")


def register_ids(
    kind: str,
    records: list[dict[str, Any]],
    findings: Findings,
    seen: dict[str, str],
) -> dict[str, dict[str, Any]]:
    field_name, pattern = PRIMARY_ID_FIELDS[kind]
    index: dict[str, dict[str, Any]] = {}
    for position, record in enumerate(records):
        location = f"{kind}[{position}]"
        identifier = record.get(field_name)
        if not isinstance(identifier, str) or not re.fullmatch(pattern, identifier):
            findings.error(location, f"{field_name} has invalid format: {identifier!r}")
            continue
        if identifier in seen:
            findings.error(location, f"duplicate ID; already used at {seen[identifier]}")
        else:
            seen[identifier] = location
        if identifier in index:
            findings.error(location, f"duplicate {field_name} within {kind}")
        index[identifier] = record
    return index


def host_is_official(host: str) -> bool:
    normalized = host.lower().strip(".")
    return any(
        normalized == suffix or normalized.endswith("." + suffix)
        for suffix in OFFICIAL_HOST_SUFFIXES
    )


def validate_sources(
    records: list[dict[str, Any]], findings: Findings
) -> None:
    required = {
        "source_id",
        "title",
        "publisher",
        "document_identifier",
        "source_type",
        "authority_tier",
        "official",
        "url",
        "language",
        "publication_date",
        "retrieved_at",
        "content_sha256",
        "verification_status",
        "notes",
    }
    for index, record in enumerate(records):
        location = f"sources[{index}]"
        require_keys(record, required, location, findings)
        tier = record.get("authority_tier")
        if not isinstance(tier, int) or isinstance(tier, bool) or tier not in range(1, 5):
            findings.error(location, "authority_tier must be an integer from 1 to 4")
        official = record.get("official")
        if not isinstance(official, bool):
            findings.error(location, "official must be a boolean")
        url = record.get("url")
        if not isinstance(url, str):
            findings.error(location, "url must be a string")
        else:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname:
                findings.error(location, "url must be an absolute HTTPS URL")
            elif official and not host_is_official(parsed.hostname):
                findings.warn(location, f"verify unrecognized official hostname {parsed.hostname!r}")
        publication_date = record.get("publication_date")
        if publication_date is not None and not is_date(publication_date):
            findings.error(location, "publication_date must be null or YYYY-MM-DD")
        if not is_timestamp(record.get("retrieved_at")):
            findings.error(location, "retrieved_at must be an ISO 8601 UTC timestamp")
        verification = record.get("verification_status")
        if verification not in SOURCE_VERIFICATION:
            findings.error(location, f"invalid verification_status: {verification!r}")
        if tier in {1, 2, 3} and official is False:
            findings.error(location, "authority tiers 1-3 must be official")
        if tier == 4 and verification == "verified":
            findings.warn(location, "Tier 4 source is discovery material, not verified authority")
        digest = record.get("content_sha256")
        if digest is not None and not re.fullmatch(r"[a-fA-F0-9]{64}", str(digest)):
            findings.error(location, "content_sha256 must be null or 64 hexadecimal characters")
        require_string_list(record.get("notes"), f"{location}.notes", findings)


def validate_changes(
    records: list[dict[str, Any]], sources: dict[str, dict[str, Any]], findings: Findings
) -> None:
    required = {
        "change_id",
        "topic_key",
        "title",
        "short_name",
        "legal_instrument_id",
        "celex",
        "issuing_body",
        "instrument_type",
        "jurisdictions",
        "legal_status",
        "binding_nature",
        "publication_date",
        "entry_into_force_date",
        "application_events",
        "change_summary",
        "amends_or_supersedes",
        "related_change_ids",
        "primary_source_id",
        "source_ids",
        "requirement_ids",
    } | COMMON_RECORD_KEYS
    for index, record in enumerate(records):
        location = f"changes[{index}]"
        require_keys(record, required, location, findings)
        check_provenance(record, location, external=True, findings=findings)
        source_ids = require_string_list(record.get("source_ids"), f"{location}.source_ids", findings)
        if not source_ids:
            findings.error(location, "change requires at least one source_id")
        for source_id in source_ids:
            if source_id not in sources:
                findings.error(location, f"unknown source_id {source_id!r}")
        primary = record.get("primary_source_id")
        if primary not in source_ids:
            findings.error(location, "primary_source_id must also appear in source_ids")
        elif primary not in sources:
            findings.error(location, f"unknown primary_source_id {primary!r}")
        elif record.get("record_status") == "verified":
            source = sources[primary]
            if not source.get("official") or source.get("authority_tier") not in {1, 2}:
                findings.error(location, "verified change needs a Tier 1 or 2 official primary source")
            if source.get("verification_status") != "verified":
                findings.error(location, "verified change needs a verified primary source")
        for key in ("publication_date", "entry_into_force_date"):
            value = record.get(key)
            if value is not None and not is_date(value):
                findings.error(location, f"{key} must be null or YYYY-MM-DD")
        require_string_list(record.get("requirement_ids"), f"{location}.requirement_ids", findings)
        require_string_list(record.get("related_change_ids"), f"{location}.related_change_ids", findings)
        events = record.get("application_events")
        if not isinstance(events, list):
            findings.error(location, "application_events must be an array")
        else:
            for event_index, event in enumerate(events):
                event_location = f"{location}.application_events[{event_index}]"
                if require_keys(
                    event,
                    {"event_type", "date", "applies_to", "locator", "source_ids", "verification_status"},
                    event_location,
                    findings,
                ):
                    if event.get("date") is not None and not is_date(event.get("date")):
                        findings.error(event_location, "date must be null or YYYY-MM-DD")
                    for source_id in require_string_list(
                        event.get("source_ids"), f"{event_location}.source_ids", findings
                    ):
                        if source_id not in sources:
                            findings.error(event_location, f"unknown source_id {source_id!r}")


def validate_requirements(
    records: list[dict[str, Any]], sources: dict[str, dict[str, Any]], findings: Findings
) -> None:
    required = {
        "requirement_id",
        "change_id",
        "title",
        "requirement_text",
        "legal_force",
        "addressee_types",
        "jurisdictions",
        "applicability_conditions",
        "exclusions_and_exemptions",
        "compliance_events",
        "source_citations",
        "required_bank_facts",
        "capability_domains",
        "policy_ids",
        "control_ids",
        "procedure_ids",
        "current_coverage",
        "interpretation_notes",
    } | COMMON_RECORD_KEYS
    citation_ids: set[str] = set()
    for index, record in enumerate(records):
        location = f"requirements[{index}]"
        require_keys(record, required, location, findings)
        check_provenance(record, location, external=True, findings=findings)
        for field_name in (
            "addressee_types",
            "jurisdictions",
            "capability_domains",
            "policy_ids",
            "control_ids",
            "procedure_ids",
            "interpretation_notes",
        ):
            require_string_list(record.get(field_name), f"{location}.{field_name}", findings)

        citations = record.get("source_citations")
        verified_official = False
        local_citation_ids: set[str] = set()
        if not isinstance(citations, list) or not citations:
            findings.error(location, "source_citations must be a non-empty array")
        else:
            for citation_index, citation in enumerate(citations):
                citation_location = f"{location}.source_citations[{citation_index}]"
                if not require_keys(
                    citation,
                    {
                        "citation_id",
                        "source_id",
                        "locator_type",
                        "locator",
                        "evidence_type",
                        "evidence_text",
                        "supports_fields",
                        "verification_status",
                    },
                    citation_location,
                    findings,
                ):
                    continue
                citation_id = citation.get("citation_id")
                if not isinstance(citation_id, str) or not re.fullmatch(
                    r"CIT-[A-Z0-9]+(?:-[A-Z0-9]+)+", citation_id
                ):
                    findings.error(citation_location, f"invalid citation_id: {citation_id!r}")
                elif citation_id in citation_ids:
                    findings.error(citation_location, f"duplicate citation_id {citation_id!r}")
                else:
                    citation_ids.add(citation_id)
                    local_citation_ids.add(citation_id)
                source_id = citation.get("source_id")
                if source_id not in sources:
                    findings.error(citation_location, f"unknown source_id {source_id!r}")
                if not isinstance(citation.get("locator"), str) or not citation.get("locator").strip():
                    findings.error(citation_location, "locator must be a non-empty string")
                require_string_list(
                    citation.get("supports_fields"),
                    f"{citation_location}.supports_fields",
                    findings,
                )
                if citation.get("verification_status") == "verified" and source_id in sources:
                    source = sources[source_id]
                    if source.get("official") and source.get("authority_tier") in {1, 2}:
                        verified_official = True
        if record.get("record_status") == "verified" and not verified_official:
            findings.error(location, "verified requirement needs a verified Tier 1 or 2 citation")

        conditions = record.get("applicability_conditions")
        if not isinstance(conditions, list):
            findings.error(location, "applicability_conditions must be an array")
        else:
            condition_ids: set[str] = set()
            for condition_index, condition in enumerate(conditions):
                condition_location = f"{location}.applicability_conditions[{condition_index}]"
                if not require_keys(
                    condition,
                    {
                        "condition_id",
                        "description",
                        "condition_type",
                        "fact_path",
                        "operator",
                        "expected_value",
                        "source_citation_ids",
                        "evidence_status",
                    },
                    condition_location,
                    findings,
                ):
                    continue
                condition_id = condition.get("condition_id")
                if condition_id in condition_ids:
                    findings.error(condition_location, f"duplicate condition_id {condition_id!r}")
                elif isinstance(condition_id, str):
                    condition_ids.add(condition_id)
                refs = require_string_list(
                    condition.get("source_citation_ids"),
                    f"{condition_location}.source_citation_ids",
                    findings,
                )
                for ref in refs:
                    if ref not in local_citation_ids:
                        findings.error(condition_location, f"unknown local citation_id {ref!r}")

        coverage = record.get("current_coverage")
        if require_keys(
            coverage,
            {
                "rating",
                "assessment_basis",
                "rationale",
                "control_ids",
                "uncovered_dimensions",
                "verification_status",
            },
            f"{location}.current_coverage",
            findings,
        ):
            rating = coverage.get("rating")
            if rating not in {"full", "partial", "none", "unknown", "not_assessed"}:
                findings.error(location, f"invalid current_coverage rating: {rating!r}")
            controls = require_string_list(
                coverage.get("control_ids"),
                f"{location}.current_coverage.control_ids",
                findings,
            )
            uncovered = require_string_list(
                coverage.get("uncovered_dimensions"),
                f"{location}.current_coverage.uncovered_dimensions",
                findings,
            )
            if rating == "partial" and (not controls or not uncovered):
                findings.error(location, "partial coverage needs controls and uncovered_dimensions")
            if rating == "full" and uncovered:
                findings.error(location, "full coverage cannot have uncovered_dimensions")
            if rating == "none" and controls:
                findings.error(location, "none coverage cannot list current controls")


def validate_policies(records: list[dict[str, Any]], findings: Findings) -> None:
    required = {
        "policy_id",
        "title",
        "version",
        "lifecycle_status",
        "approval_date",
        "effective_date",
        "next_review_date",
        "owner_role_id",
        "purpose",
        "scope",
        "statements",
        "requirement_ids",
        "control_ids",
        "procedure_ids",
        "current_state_summary",
    } | COMMON_RECORD_KEYS
    statement_ids: set[str] = set()
    for index, record in enumerate(records):
        location = f"policies[{index}]"
        require_keys(record, required, location, findings)
        check_provenance(record, location, external=False, findings=findings)
        for field_name in ("requirement_ids", "control_ids", "procedure_ids"):
            require_string_list(record.get(field_name), f"{location}.{field_name}", findings)
        for date_field in ("approval_date", "effective_date", "next_review_date"):
            value = record.get(date_field)
            if value is not None and not is_date(value):
                findings.error(location, f"{date_field} must be null or YYYY-MM-DD")
        scope = record.get("scope")
        if require_keys(
            scope,
            {
                "jurisdictions",
                "business_line_ids",
                "product_ids",
                "process_ids",
                "system_ids",
                "data_asset_ids",
                "vendor_ids",
                "critical_service_ids",
            },
            f"{location}.scope",
            findings,
        ):
            for field_name, value in scope.items():
                if field_name != "extensions":
                    require_string_list(value, f"{location}.scope.{field_name}", findings)
        statements = record.get("statements")
        if not isinstance(statements, list) or not statements:
            findings.error(location, "statements must be a non-empty array")
        else:
            for statement_index, statement in enumerate(statements):
                statement_location = f"{location}.statements[{statement_index}]"
                if not require_keys(
                    statement,
                    {"statement_id", "text", "requirement_ids", "implementation_status", "control_ids"},
                    statement_location,
                    findings,
                ):
                    continue
                statement_id = statement.get("statement_id")
                if not isinstance(statement_id, str) or not re.fullmatch(
                    r"PST-[A-Z0-9]+(?:-[A-Z0-9]+)+", statement_id
                ):
                    findings.error(statement_location, f"invalid statement_id {statement_id!r}")
                elif statement_id in statement_ids:
                    findings.error(statement_location, f"duplicate statement_id {statement_id!r}")
                else:
                    statement_ids.add(statement_id)


def validate_controls(records: list[dict[str, Any]], findings: Findings) -> None:
    required = {
        "control_id",
        "title",
        "objective",
        "control_type",
        "execution_mode",
        "frequency",
        "lifecycle_status",
        "design_status",
        "operating_status",
        "owner_role_id",
        "requirement_ids",
        "policy_ids",
        "procedure_ids",
        "business_line_ids",
        "product_ids",
        "process_ids",
        "system_ids",
        "data_asset_ids",
        "vendor_ids",
        "critical_service_ids",
        "coverage",
        "expected_evidence_types",
        "evidence_item_ids",
        "gap_flags",
    } | COMMON_RECORD_KEYS
    for index, record in enumerate(records):
        location = f"controls[{index}]"
        require_keys(record, required, location, findings)
        check_provenance(record, location, external=False, findings=findings)
        for field_name in (
            "requirement_ids",
            "policy_ids",
            "procedure_ids",
            "business_line_ids",
            "product_ids",
            "process_ids",
            "system_ids",
            "data_asset_ids",
            "vendor_ids",
            "critical_service_ids",
            "expected_evidence_types",
            "evidence_item_ids",
        ):
            require_string_list(record.get(field_name), f"{location}.{field_name}", findings)
        coverage = record.get("coverage")
        if not isinstance(coverage, list):
            findings.error(location, "coverage must be an array")
        else:
            for coverage_index, item in enumerate(coverage):
                require_keys(
                    item,
                    {"dimension_type", "dimension_ref", "coverage_status", "rationale"},
                    f"{location}.coverage[{coverage_index}]",
                    findings,
                )
        gap_flags = record.get("gap_flags")
        if not isinstance(gap_flags, list):
            findings.error(location, "gap_flags must be an array")
        else:
            for gap_index, item in enumerate(gap_flags):
                require_keys(
                    item,
                    {"gap_code", "description", "status"},
                    f"{location}.gap_flags[{gap_index}]",
                    findings,
                )
        if record.get("operating_status") == "operating" and not record.get("evidence_item_ids"):
            findings.error(location, "operating control requires existing evidence_item_ids")


def validate_procedures(records: list[dict[str, Any]], findings: Findings) -> None:
    required = {
        "procedure_id",
        "title",
        "version",
        "lifecycle_status",
        "effective_date",
        "next_review_date",
        "owner_role_id",
        "purpose",
        "trigger",
        "frequency",
        "scope",
        "requirement_ids",
        "policy_ids",
        "control_ids",
        "steps",
        "escalation_conditions",
        "expected_evidence_types",
        "evidence_item_ids",
    } | COMMON_RECORD_KEYS
    for index, record in enumerate(records):
        location = f"procedures[{index}]"
        require_keys(record, required, location, findings)
        check_provenance(record, location, external=False, findings=findings)
        for field_name in (
            "requirement_ids",
            "policy_ids",
            "control_ids",
            "escalation_conditions",
            "expected_evidence_types",
            "evidence_item_ids",
        ):
            require_string_list(record.get(field_name), f"{location}.{field_name}", findings)
        for date_field in ("effective_date", "next_review_date"):
            value = record.get(date_field)
            if value is not None and not is_date(value):
                findings.error(location, f"{date_field} must be null or YYYY-MM-DD")
        scope = record.get("scope")
        if require_keys(
            scope,
            {"business_line_ids", "product_ids", "process_ids", "system_ids", "data_asset_ids"},
            f"{location}.scope",
            findings,
        ):
            for field_name, value in scope.items():
                if field_name != "extensions":
                    require_string_list(value, f"{location}.scope.{field_name}", findings)
        steps = record.get("steps")
        if not isinstance(steps, list) or not steps:
            findings.error(location, "steps must be a non-empty array")
        else:
            numbers: list[int] = []
            for step_index, step in enumerate(steps):
                step_location = f"{location}.steps[{step_index}]"
                if require_keys(
                    step,
                    {
                        "step_number",
                        "action",
                        "performer_role_id",
                        "system_ids",
                        "data_asset_ids",
                        "control_ids",
                        "output_description",
                        "exception_handling",
                    },
                    step_location,
                    findings,
                ):
                    number = step.get("step_number")
                    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                        findings.error(step_location, "step_number must be a positive integer")
                    else:
                        numbers.append(number)
            if sorted(numbers) != list(range(1, len(steps) + 1)):
                findings.error(location, "step_number values must be unique and contiguous from 1")


def check_reference_list(
    source_name: str,
    source_record: dict[str, Any],
    source_field: str,
    target_name: str,
    target_index: dict[str, dict[str, Any]],
    reverse_field: str,
    findings: Findings,
) -> None:
    source_id_field = PRIMARY_ID_FIELDS[source_name][0]
    source_id = source_record.get(source_id_field)
    values = source_record.get(source_field)
    if not isinstance(values, list):
        return
    for target_id in values:
        target = target_index.get(target_id)
        if target is None:
            findings.error(
                source_id or source_name,
                f"{source_field} contains unknown {target_name} ID {target_id!r}",
            )
            continue
        reverse = target.get(reverse_field)
        if not isinstance(reverse, list) or source_id not in reverse:
            findings.error(
                source_id or source_name,
                f"{target_id}.{reverse_field} is missing reverse reference {source_id!r}",
            )


def validate_integrity(
    indexes: dict[str, dict[str, dict[str, Any]]], findings: Findings
) -> None:
    changes = indexes["changes"]
    requirements = indexes["requirements"]
    policies = indexes["policies"]
    controls = indexes["controls"]
    procedures = indexes["procedures"]

    by_change: dict[str, set[str]] = defaultdict(set)
    for requirement_id, requirement in requirements.items():
        change_id = requirement.get("change_id")
        if change_id not in changes:
            findings.error(requirement_id, f"unknown change_id {change_id!r}")
        else:
            by_change[change_id].add(requirement_id)
    for change_id, change in changes.items():
        actual = set(change.get("requirement_ids", []))
        if actual != by_change.get(change_id, set()):
            findings.error(
                change_id,
                "requirement_ids must exactly match requirements that point to this change",
            )

    for record in requirements.values():
        check_reference_list("requirements", record, "policy_ids", "policy", policies, "requirement_ids", findings)
        check_reference_list("requirements", record, "control_ids", "control", controls, "requirement_ids", findings)
        check_reference_list("requirements", record, "procedure_ids", "procedure", procedures, "requirement_ids", findings)
    for record in policies.values():
        check_reference_list("policies", record, "requirement_ids", "requirement", requirements, "policy_ids", findings)
        check_reference_list("policies", record, "control_ids", "control", controls, "policy_ids", findings)
        check_reference_list("policies", record, "procedure_ids", "procedure", procedures, "policy_ids", findings)
    for record in controls.values():
        check_reference_list("controls", record, "requirement_ids", "requirement", requirements, "control_ids", findings)
        check_reference_list("controls", record, "policy_ids", "policy", policies, "control_ids", findings)
        check_reference_list("controls", record, "procedure_ids", "procedure", procedures, "control_ids", findings)
    for record in procedures.values():
        check_reference_list("procedures", record, "requirement_ids", "requirement", requirements, "procedure_ids", findings)
        check_reference_list("procedures", record, "policy_ids", "policy", policies, "procedure_ids", findings)
        check_reference_list("procedures", record, "control_ids", "control", controls, "procedure_ids", findings)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)


def check_placeholders(documents: dict[str, dict[str, Any]], findings: Findings) -> None:
    pattern = re.compile(r"\b(?:TODO|TBC|FIXME|PLACEHOLDER)\b", re.IGNORECASE)
    for name, document in documents.items():
        for text in iter_strings(document):
            if pattern.search(text):
                findings.warn(name, f"placeholder-like text remains: {text[:100]!r}")


def collect_external_refs(records: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = defaultdict(set)
    pattern = re.compile(r"^(BL|PRD|PROC|SYS|DATA|VND|ROLE|EVD)-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
    for record in records:
        for value in iter_strings(record):
            match = pattern.fullmatch(value)
            if match:
                refs[match.group(1)].add(value)
    return refs


def collect_ids_from_json(path: Path) -> set[str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return set()
    pattern = re.compile(r"^[A-Z][A-Z0-9]*-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
    return {value for value in iter_strings(data) if pattern.fullmatch(value)}


def validate_cross_team_refs(
    root: Path, governance_records: Iterable[dict[str, Any]], findings: Findings
) -> None:
    owner_paths = {
        "BL": [Path("02_business/business_lines.json")],
        "PRD": [Path("02_business/products.json")],
        "PROC": [Path("05_operations/processes.json")],
        "SYS": [Path("05_operations/systems.json")],
        "DATA": [Path("05_operations/data_assets.json")],
        "VND": [Path("05_operations/vendors.json")],
        "ROLE": [Path("06_organisation/roles.json")],
        "EVD": [Path("08_evidence/evidence_register.json")],
    }
    refs = collect_external_refs(governance_records)
    for prefix, identifiers in sorted(refs.items()):
        paths = [root / relative for relative in owner_paths[prefix]]
        existing_paths = [path for path in paths if path.is_file()]
        if not existing_paths:
            findings.warn(
                prefix,
                f"cannot verify {len(identifiers)} cross-team reference(s); owner file is absent",
            )
            continue
        known: set[str] = set()
        for path in existing_paths:
            known.update(collect_ids_from_json(path))
        for identifier in sorted(identifiers - known):
            findings.error(prefix, f"cross-team ID {identifier!r} does not resolve in its owner file")


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    findings = Findings()
    documents: dict[str, dict[str, Any]] = {}
    records: dict[str, list[dict[str, Any]]] = {}

    for key, relative_path in FILES.items():
        path = root / relative_path
        document = load_json(path, findings)
        if document is None:
            continue
        documents[key] = document
        records[key] = check_envelope(document, key, path, findings)

    if len(documents) != len(FILES):
        return report(findings, args.strict)

    metadata = {
        (
            document.get("schema_version"),
            document.get("dataset_scope"),
            document.get("as_of_date"),
        )
        for document in documents.values()
    }
    if len(metadata) != 1:
        findings.error("envelopes", "schema_version, dataset_scope, and as_of_date must match")

    change_document = documents["changes"]
    raw_sources = change_document.get("sources")
    if not isinstance(raw_sources, list):
        findings.error(str(root / FILES["changes"]), "sources must be an array")
        raw_sources = []
    sources_records = [item for item in raw_sources if isinstance(item, dict)]

    seen: dict[str, str] = {}
    indexes = {
        "sources": register_ids("sources", sources_records, findings, seen),
        **{
            key: register_ids(key, records[key], findings, seen)
            for key in ("changes", "requirements", "policies", "controls", "procedures")
        },
    }

    validate_sources(sources_records, findings)
    validate_changes(records["changes"], indexes["sources"], findings)
    validate_requirements(records["requirements"], indexes["sources"], findings)
    validate_policies(records["policies"], findings)
    validate_controls(records["controls"], findings)
    validate_procedures(records["procedures"], findings)
    validate_integrity(indexes, findings)
    validate_cross_team_refs(
        root,
        records["policies"] + records["controls"] + records["procedures"],
        findings,
    )
    check_placeholders(documents, findings)

    if args.require_first_demo:
        topics = {record.get("topic_key") for record in records["changes"]}
        aliases = {
            "esg_risk_management": {"esg", "eba_esg", "esg_risk_management"},
            "instant_payments": {"ips", "instant_payments"},
            "dora": {"dora"},
            "frtb": {"frtb"},
        }
        for label, accepted in aliases.items():
            if topics.isdisjoint(accepted):
                findings.error("first_demo", f"missing change topic {label!r}")
                continue
            matching = [
                record for record in records["changes"] if record.get("topic_key") in accepted
            ]
            if not any(record.get("requirement_ids") for record in matching):
                findings.error(
                    "first_demo",
                    f"topic {label!r} has no linked atomic requirement",
                )

    return report(findings, args.strict)


def report(findings: Findings, strict: bool) -> int:
    for message in findings.errors:
        print(f"ERROR: {message}")
    for message in findings.warnings:
        print(f"WARNING: {message}")
    print(
        f"Validation complete: {len(findings.errors)} error(s), "
        f"{len(findings.warnings)} warning(s)."
    )
    if findings.errors or (strict and findings.warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
