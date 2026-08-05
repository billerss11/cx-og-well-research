#!/usr/bin/env python
"""Standalone CX O&G research CLI."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from well_research_casing import build_global_casing_search, parse_casing_sizes
from well_research_config import DATASET_CATALOG, INCIDENT_TERMS
from well_research_core import (
    build_ranked_dataset,
    describe_table,
    repo_root_from,
    to_jsonable,
)
from well_research_current import (
    RAW_DATASETS,
    ResearchDataError,
    approval_options,
    build_dossier,
    bulk_files,
    bulk_war,
    compare_fields,
    coverage,
    doctor,
    evidence_detail,
    field_leases,
    field_options,
    pipeline_detail,
    platform_detail,
    production_comparison,
    provenance,
    raw_well_records,
    search_approvals,
    search_evidence,
    search_pipelines,
    search_platforms,
    search_wells,
    well_applications_page,
    well_documents_page,
    well_relationships,
    well_timeline_event,
    well_timeline_page,
)
from well_research_decom import build_decom_research
from well_research_evidence import build_field_audit


SCHEMA_VERSION = 1
MAP_FIELD_PARTS = (
    "latitude",
    "longitude",
    "geometry",
    "geojson",
    "easting",
    "northing",
    "x_location",
    "y_location",
    "x_coordinate",
    "y_coordinate",
    "bathymetry",
    "continental_shelf",
    "east_offset",
    "north_offset",
    "surf_e_w",
    "surf_n_s",
    "nad_year",
    "proj_code",
)


def _bounded_int(minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        parsed = int(value)
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(
                f"must be between {minimum} and {maximum}"
            )
        return parsed

    return parse


def _api(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) not in {11, 12}:
        raise argparse.ArgumentTypeError("API well number must contain 11 or 12 digits")
    return digits


def _api_values(values: list[str]) -> list[str]:
    parsed: list[str] = []
    for value in values:
        for item in value.replace(";", ",").split(","):
            cleaned = item.strip()
            if cleaned:
                parsed.append(_api(cleaned))
    return list(dict.fromkeys(parsed))


def _common_search(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    parser.add_argument("--page-size", type=_bounded_int(1, 100), default=25)
    parser.add_argument("--match-mode", choices=["exact", "fuzzy"], default="exact")
    parser.add_argument("--threshold", type=_bounded_int(60, 100), default=90)
    parser.add_argument(
        "--partial",
        action=argparse.BooleanOptionalAction,
        default=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-limit", type=_bounded_int(1, 100), default=10)
    commands = parser.add_subparsers(dest="group", required=True)

    commands.add_parser("doctor", help="Validate required and optional data contracts.")

    wells = commands.add_parser("wells")
    wells_commands = wells.add_subparsers(dest="action", required=True)
    wells_search = wells_commands.add_parser("search")
    wells_search.add_argument("query", nargs="?", default="")
    wells_search.add_argument("--operator")
    wells_search.add_argument("--field")
    wells_search.add_argument("--status")
    wells_search.add_argument("--area")
    wells_search.add_argument("--block")
    wells_search.add_argument("--platform")
    wells_search.add_argument("--lease")
    _common_search(wells_search)
    wells_search.add_argument(
        "--sort-by",
        choices=[
            "api_well_number",
            "well_name",
            "operator",
            "field",
            "lease",
            "area",
            "block",
            "platform",
            "status",
        ],
        default="api_well_number",
    )
    wells_search.add_argument("--sort-direction", choices=["asc", "desc"], default="asc")

    evidence = commands.add_parser("evidence")
    evidence_commands = evidence.add_subparsers(dest="action", required=True)
    evidence_search = evidence_commands.add_parser("search")
    evidence_search.add_argument("query", nargs="?")
    evidence_search.add_argument("--incident", choices=sorted(INCIDENT_TERMS))
    _common_search(evidence_search)
    evidence_search.add_argument("--sort-by", choices=["matches", "recent"], default="matches")
    evidence_detail_parser = evidence_commands.add_parser("detail")
    evidence_detail_parser.add_argument("api_well_number", type=_api)
    evidence_detail_parser.add_argument("query", nargs="?")
    evidence_detail_parser.add_argument("--incident", choices=sorted(INCIDENT_TERMS))
    evidence_detail_parser.add_argument("--war-page", type=_bounded_int(1, 1_000_000), default=1)
    evidence_detail_parser.add_argument(
        "--attachment-page",
        type=_bounded_int(1, 1_000_000),
        default=1,
    )
    evidence_detail_parser.add_argument("--page-size", type=_bounded_int(1, 100), default=25)
    evidence_detail_parser.add_argument(
        "--match-mode",
        choices=["exact", "fuzzy"],
        default="exact",
    )
    evidence_detail_parser.add_argument("--threshold", type=_bounded_int(60, 100), default=90)
    evidence_detail_parser.add_argument(
        "--partial",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    well = commands.add_parser("well")
    well_commands = well.add_subparsers(dest="action", required=True)
    dossier = well_commands.add_parser("dossier")
    dossier.add_argument("api_well_number", type=_api)
    dossier.add_argument("--sections", help="Comma-separated section names.")
    dossier.add_argument("--min-step", type=float, default=100.0)
    raw = well_commands.add_parser("raw")
    raw.add_argument("api_well_number", type=_api)
    raw.add_argument("dataset", choices=sorted(RAW_DATASETS))
    raw.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    raw.add_argument("--page-size", type=_bounded_int(1, 100), default=25)
    for section in (
        "summary",
        "availability",
        "relationships",
        "ownership",
        "production",
        "trajectory",
        "wellbore",
        "casing",
        "war",
        "permits",
        "files",
    ):
        section_parser = well_commands.add_parser(section)
        section_parser.add_argument("api_well_number", type=_api)
    applications_parser = well_commands.add_parser("applications")
    applications_parser.add_argument("api_well_number", type=_api)
    applications_parser.add_argument("--source")
    applications_parser.add_argument("--status")
    applications_parser.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    applications_parser.add_argument("--page-size", type=_bounded_int(1, 100), default=50)
    documents_parser = well_commands.add_parser("documents")
    documents_parser.add_argument("api_well_number", type=_api)
    documents_parser.add_argument("--source")
    documents_parser.add_argument("--query")
    documents_parser.add_argument("--availability")
    documents_parser.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    documents_parser.add_argument("--page-size", type=_bounded_int(1, 100), default=50)
    timeline_parser = well_commands.add_parser("timeline")
    timeline_parser.add_argument("api_well_number", type=_api)
    timeline_parser.add_argument("--source")
    timeline_parser.add_argument("--category")
    timeline_parser.add_argument("--date-from")
    timeline_parser.add_argument("--date-to")
    timeline_parser.add_argument("--has-documents", action=argparse.BooleanOptionalAction)
    timeline_parser.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    timeline_parser.add_argument("--page-size", type=_bounded_int(1, 100), default=50)
    timeline_detail = well_commands.add_parser("timeline-detail")
    timeline_detail.add_argument("api_well_number", type=_api)
    timeline_detail.add_argument("event_id")

    fields = commands.add_parser("fields")
    fields_commands = fields.add_subparsers(dest="action", required=True)
    fields_commands.add_parser("list")
    fields_compare = fields_commands.add_parser("compare")
    fields_compare.add_argument("fields", nargs="+")
    fields_compare.add_argument("--audit", action="store_true")
    fields_wells = fields_commands.add_parser("wells")
    fields_wells.add_argument("fields", nargs="+")
    fields_leases = fields_commands.add_parser("leases")
    fields_leases.add_argument("fields", nargs="+")
    fields_lease_context = fields_commands.add_parser("lease-context")
    fields_lease_context.add_argument("fields", nargs="+")

    production = commands.add_parser("production")
    production_commands = production.add_subparsers(dest="action", required=True)
    production_compare = production_commands.add_parser("compare")
    production_compare.add_argument("api_well_numbers", nargs="+")
    production_compare.add_argument(
        "--group-by",
        choices=["well", "completion", "product", "interval"],
        default="well",
    )

    approvals = commands.add_parser("approvals")
    approvals_commands = approvals.add_subparsers(dest="action", required=True)
    approvals_search = approvals_commands.add_parser("search")
    approvals_search.add_argument("--query")
    approvals_search.add_argument("--asset-type")
    approvals_search.add_argument("--asset-identifier")
    approvals_search.add_argument("--business-process")
    approvals_search.add_argument("--approval-type")
    approvals_search.add_argument("--date-from")
    approvals_search.add_argument("--date-to")
    approvals_search.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    approvals_search.add_argument("--page-size", type=_bounded_int(1, 100), default=50)
    approvals_commands.add_parser("options")

    platforms = commands.add_parser("platforms")
    platform_commands = platforms.add_subparsers(dest="action", required=True)
    platform_search = platform_commands.add_parser("search")
    platform_search.add_argument("--query")
    platform_search.add_argument("--status", choices=["active", "removed"])
    platform_search.add_argument("--company")
    platform_search.add_argument("--lease")
    platform_search.add_argument("--area")
    platform_search.add_argument("--block")
    platform_search.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    platform_search.add_argument("--page-size", type=_bounded_int(1, 100), default=50)
    platform_detail_parser = platform_commands.add_parser("detail")
    platform_detail_parser.add_argument("complex_id", type=int)
    platform_detail_parser.add_argument("structure_number", type=int)

    pipelines = commands.add_parser("pipelines")
    pipeline_commands = pipelines.add_subparsers(dest="action", required=True)
    pipeline_search = pipeline_commands.add_parser("search")
    pipeline_search.add_argument("--query")
    pipeline_search.add_argument("--status")
    pipeline_search.add_argument("--product")
    pipeline_search.add_argument("--company")
    pipeline_search.add_argument("--page", type=_bounded_int(1, 1_000_000), default=1)
    pipeline_search.add_argument("--page-size", type=_bounded_int(1, 100), default=50)
    pipeline_detail_parser = pipeline_commands.add_parser("detail")
    pipeline_detail_parser.add_argument("segment_number")
    pipeline_detail_parser.add_argument(
        "--history-page",
        type=_bounded_int(1, 1_000_000),
        default=1,
    )
    pipeline_detail_parser.add_argument(
        "--history-page-size",
        type=_bounded_int(1, 100),
        default=50,
    )

    bulk = commands.add_parser("bulk")
    bulk_commands = bulk.add_subparsers(dest="action", required=True)
    bulk_files_parser = bulk_commands.add_parser("files")
    bulk_files_parser.add_argument("api_well_numbers", nargs="+")
    bulk_war_parser = bulk_commands.add_parser("war")
    bulk_war_parser.add_argument("api_well_numbers", nargs="+")

    casing = commands.add_parser("casing")
    casing_commands = casing.add_subparsers(dest="action", required=True)
    casing_search = casing_commands.add_parser("search")
    casing_search.add_argument("sizes")
    casing_search.add_argument("--source", choices=["any", "apd", "war"], default="any")
    casing_search.add_argument("--match", choices=["all", "any"], default="all")
    casing_search.add_argument("--tolerance", type=float, default=0.01)
    casing_search.add_argument("--filter")
    casing_search.add_argument("--latest-only", action="store_true")

    decommissioning = commands.add_parser("decommissioning")
    decommissioning_commands = decommissioning.add_subparsers(dest="action", required=True)
    decom_search = decommissioning_commands.add_parser("search")
    decom_search.add_argument("--lease")
    decom_search.add_argument("--api", type=_api)
    decom_search.add_argument("--area")
    decom_search.add_argument("--block")
    decom_search.add_argument("--min-cost", type=float)
    decom_search.add_argument(
        "--cost-case",
        choices=["p50", "p70", "p90", "dtr"],
        default="p90",
    )
    decom_search.add_argument("--pa-adjustment", choices=["Y", "N", "y", "n"])

    tables = commands.add_parser("tables")
    table_commands = tables.add_subparsers(dest="action", required=True)
    table_commands.add_parser("list")
    table_describe = table_commands.add_parser("describe")
    table_describe.add_argument("table")
    table_rank = table_commands.add_parser("rank")
    table_rank.add_argument("table")
    table_rank.add_argument("rank_by")
    table_rank.add_argument("--direction", choices=["asc", "desc"], default="desc")

    return parser


def _is_map_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return (
        normalized in {"geom", "wkt", "wkb", "shape"}
        or any(part in normalized for part in MAP_FIELD_PARTS)
    )


def _strip_map_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_map_data(item)
            for key, item in value.items()
            if not _is_map_field(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [
            _strip_map_data(item)
            for item in value
            if not (
                isinstance(item, dict)
                and "name" in item
                and "unit" in item
                and "aliases" in item
                and _is_map_field(str(item["name"]))
            )
        ]
    return value


def _envelope(
    command: str,
    query: dict[str, Any],
    data: Any,
    *,
    data_dir: Path,
    datasets: list[str],
    source_family: str,
    join_identifier: str,
    warnings: list[str] | None = None,
    units: dict[str, str] | None = None,
    derived_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    coverage_rows = coverage(data_dir, datasets)
    automatic_warnings = [
        f"Missing optional dataset: {row['source']}; coverage is partial."
        for row in coverage_rows
        if row["status"] == "missing" and not row["required"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "query": to_jsonable(query),
        "data": to_jsonable(_strip_map_data(data)),
        "provenance": provenance(
            datasets,
            source_family,
            join_identifier,
            units=units,
            derived_fields=derived_fields,
        ),
        "coverage": coverage_rows,
        "warnings": list(dict.fromkeys([*(warnings or []), *automatic_warnings])),
    }


def _section_warnings(data: Any) -> list[str]:
    warnings: list[str] = []
    if isinstance(data, dict):
        value = data.get("warnings")
        if isinstance(value, list):
            warnings.extend(str(item) for item in value)
        for child in data.values():
            warnings.extend(_section_warnings(child))
    elif isinstance(data, list):
        for child in data:
            warnings.extend(_section_warnings(child))
    return list(dict.fromkeys(warnings))


def _dossier_datasets(sections: list[str] | None) -> list[str]:
    if not sections:
        return list(DATASET_CATALOG)
    groups = {
        "relationships": {"boreholes", "structures", "lease_data"},
        "ownership": {
            "boreholes",
            "lease_data",
            "lease_owner",
            "lease_owner_designated_operator",
            "lease_owner_remarks",
            "company_all",
        },
        "lease_information": {
            "boreholes",
            "lease_data",
            "lease_owner",
            "lease_owner_designated_operator",
            "lease_owner_remarks",
            "company_all",
        },
        "production": {"production", "boreholes"},
        "trajectory": {"boreholes", "points", "azimuth", "wellpath_metrics"},
        "azimuth_dls": {"azimuth"},
        "wellpath_metrics": {"wellpath_metrics"},
        "casing": {
            "apd_main",
            "apd_casing_intervals",
            "apd_casing_sections",
            "war_main",
            "war_tubular",
            "war_tubular_prop",
        },
        "apd_casing": {"apd_main", "apd_casing_intervals", "apd_casing_sections"},
        "war_casing": {"war_main", "war_tubular", "war_tubular_prop"},
        "casing_comparison": {
            "apd_main",
            "apd_casing_intervals",
            "apd_casing_sections",
            "war_main",
            "war_tubular",
            "war_tubular_prop",
        },
        "war": {"war_main", "war_text"},
        "war_remarks": {"war_main", "war_text"},
        "applications": {"apd_main", "apm_applications", "application_attachments"},
        "permits": {"apd_main", "apm_applications", "application_attachments"},
        "documents": {"frs", "application_attachments"},
        "approvals": {"asset_approvals"},
        "timeline": {
            "apd_main",
            "war_main",
            "eor_main",
            "boreholes",
            "apm_events",
            "asset_approvals",
            "bhp",
            "api_well_completions",
            "api_changes",
            "directional_surveys",
            "well_potential_tests",
            "decom_prop_well",
            "decom_spud_well",
        },
        "wellbore_evidence": {
            "eor_main",
            "eor_geomarkers",
            "eor_perf",
            "bhp",
            "open_hole_runs",
            "open_hole_tools",
            "azimuth",
            "wellpath_metrics",
        },
        "completion_reconciliation": {"production", "eor_completions"},
        "decommissioning": {
            key
            for key in DATASET_CATALOG
            if key.startswith("decom_")
        },
        "raw_dataset_counts": {
            key for key, _ in RAW_DATASETS.values()
        },
    }
    selected = {"boreholes"}
    for section in sections:
        selected.update(groups.get(section, {section} if section in DATASET_CATALOG else set()))
    return [key for key in DATASET_CATALOG if key in selected]


def run(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo = repo_root_from(args.repo)
    data_dir = (args.data_dir or repo / "data").resolve()
    command = f"{args.group}.{getattr(args, 'action', '')}".rstrip(".")

    if args.group == "doctor":
        data = doctor(data_dir)
        result = _envelope(
            "doctor",
            {"data_dir": str(data_dir)},
            data,
            data_dir=data_dir,
            datasets=list(DATASET_CATALOG),
            source_family="CX O&G published research data",
            join_identifier="Dataset-specific contracts",
        )
        return result, 0 if data["ok"] else 3

    if command == "wells.search":
        data = search_wells(
            data_dir,
            args.query,
            page=args.page,
            page_size=args.page_size,
            sort_by=args.sort_by,
            sort_direction=args.sort_direction,
            match_mode=args.match_mode,
            threshold=args.threshold,
            partial=args.partial,
            filters={
                "operator": args.operator,
                "field": args.field,
                "status": args.status,
                "area": args.area,
                "block": args.block,
                "platform": args.platform,
                "lease": args.lease,
            },
        )
        query = {
            "q": args.query,
            "operator": args.operator,
            "field": args.field,
            "status": args.status,
            "area": args.area,
            "block": args.block,
            "platform": args.platform,
            "lease": args.lease,
            "page": args.page,
            "page_size": args.page_size,
            "sort_by": args.sort_by,
            "sort_direction": args.sort_direction,
            "match_mode": args.match_mode,
            "threshold": args.threshold,
            "partial": args.partial,
        }
        return _envelope(
            command,
            query,
            data,
            data_dir=data_dir,
            datasets=["boreholes", "structures", "war_main", "war_text", "attachments"],
            source_family="BSEE well, structure, WAR, and attachment data",
            join_identifier="API_WELL_NUMBER; SN_WAR; surface location structure match",
            units={"Water depth (ft)": "ft"},
        ), 0

    if command == "evidence.search":
        query_text = args.query or ""
        if args.incident:
            query_text = ",".join(INCIDENT_TERMS[args.incident])
        if not query_text:
            raise ValueError("Provide a query or --incident")
        data = search_evidence(
            data_dir,
            query_text,
            page=args.page,
            page_size=args.page_size,
            match_mode=args.match_mode,
            threshold=args.threshold,
            partial=args.partial,
            sort_by=args.sort_by,
        )
        query = {
            "q": query_text,
            "incident": args.incident,
            "page": args.page,
            "page_size": args.page_size,
            "match_mode": args.match_mode,
            "threshold": args.threshold,
            "partial": args.partial,
            "sort_by": args.sort_by,
        }
        warnings = (
            [
                f"Incident preset '{args.incident}' is broad operational evidence; "
                "review each preview before labeling a confirmed incident."
            ]
            if args.incident
            else []
        )
        return _envelope(
            command,
            query,
            data,
            data_dir=data_dir,
            datasets=["war_main", "war_text", "attachments", "boreholes"],
            source_family="BSEE WAR remarks and APD/APM attachment inventory",
            join_identifier="SN_WAR to API_WELL_NUMBER; attachment API_WELL_NUMBER",
            warnings=warnings,
        ), 0

    if command == "evidence.detail":
        query_text = args.query or ""
        if args.incident:
            query_text = ",".join(INCIDENT_TERMS[args.incident])
        if not query_text:
            raise ValueError("Provide a query or --incident")
        data = evidence_detail(
            data_dir,
            query_text,
            args.api_well_number,
            war_page=args.war_page,
            attachment_page=args.attachment_page,
            page_size=args.page_size,
            match_mode=args.match_mode,
            threshold=args.threshold,
            partial=args.partial,
        )
        return _envelope(
            command,
            {
                **vars(args),
                "q": query_text,
            },
            data,
            data_dir=data_dir,
            datasets=["war_main", "war_text", "attachments", "boreholes"],
            source_family="BSEE WAR remarks and APD/APM attachment inventory",
            join_identifier="Exact API well number",
        ), 0

    if command == "well.dossier":
        selected = (
            [item.strip() for item in args.sections.split(",") if item.strip()]
            if args.sections
            else None
        )
        data = build_dossier(
            data_dir,
            repo,
            args.api_well_number,
            args.sample_limit,
            sections=selected,
            min_step=args.min_step,
        )
        datasets = _dossier_datasets(selected)
        warnings = _section_warnings(data)
        source_family = (
            "BSEE sources used by the selected well dossier sections"
            if selected
            else "BSEE well, regulatory, production, lease, and decommissioning data"
        )
        return _envelope(
            command,
            {
                "api_well_number": args.api_well_number,
                "sections": selected or "all",
                "sample_limit": args.sample_limit,
                "min_step": args.min_step,
            },
            data,
            data_dir=data_dir,
            datasets=datasets,
            source_family=source_family,
            join_identifier="API well number plus source serial identifiers",
            warnings=warnings,
            derived_fields=(
                {
                    "coverage_scope": (
                        "Only sources used by the requested sections are listed. "
                        "Timeline coverage includes API-linked decommissioning well events."
                    )
                }
                if selected
                else None
            ),
        ), 0

    if command == "well.raw":
        data = raw_well_records(
            data_dir,
            args.api_well_number,
            args.dataset,
            page=args.page,
            page_size=args.page_size,
        )
        key = RAW_DATASETS[args.dataset][0]
        warnings = [data["warning"]] if data.get("warning") else []
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=[key],
            source_family=DATASET_CATALOG[key]["family"],
            join_identifier="API well number or normalized source relationship",
            warnings=warnings,
        ), 0

    if command == "well.summary":
        dossier_data = build_dossier(
            data_dir,
            repo,
            args.api_well_number,
            args.sample_limit,
            sections=["relationships"],
        )
        data = {
            "api_well_number": args.api_well_number,
            "identity": dossier_data["identity"],
        }
        return _envelope(
            command,
            {"api_well_number": args.api_well_number},
            data,
            data_dir=data_dir,
            datasets=["boreholes", "war_main"],
            source_family="BSEE Borehole Raw Data and Well Activity Reports",
            join_identifier="API_WELL_NUMBER",
        ), 0

    if command == "well.availability":
        dossier_data = build_dossier(
            data_dir,
            repo,
            args.api_well_number,
            args.sample_limit,
        )
        data = {
            "api_well_number": args.api_well_number,
            "availability": dossier_data["availability"],
        }
        return _envelope(
            command,
            {"api_well_number": args.api_well_number},
            data,
            data_dir=data_dir,
            datasets=_dossier_datasets(None),
            source_family="BSEE well workspace availability index",
            join_identifier="API well number plus section source identifiers",
            warnings=_section_warnings(data),
        ), 0

    if command == "well.relationships":
        data = well_relationships(data_dir, args.api_well_number, args.sample_limit)
        return _envelope(
            command,
            {"api_well_number": args.api_well_number},
            data,
            data_dir=data_dir,
            datasets=["boreholes", "company_all", "lease_data", "structures"],
            source_family="BSEE Borehole, Company, Leasing, and Platform Structure Data",
            join_identifier="API_WELL_NUMBER; company name; lease number; surface location",
            warnings=_section_warnings(data),
            units={"platform.water_depth_ft": "ft"},
        ), 0

    if command == "well.production":
        data = production_comparison(
            data_dir,
            [args.api_well_number],
            "well",
            args.sample_limit,
        )
        return _envelope(
            command,
            {"api_well_number": args.api_well_number},
            data,
            data_dir=data_dir,
            datasets=["production", "boreholes"],
            source_family="BSEE OGOR-A production data",
            join_identifier="Api Well Number",
            units={
                "oil_bbl": "bbl",
                "gas_mcf": "Mcf",
                "water_bbl": "bbl",
                "oil_bpd": "bbl/day",
                "gas_mcfpd": "Mcf/day",
                "water_bpd": "bbl/day",
            },
        ), 0

    if command in {
        "well.ownership",
        "well.trajectory",
        "well.wellbore",
        "well.casing",
        "well.war",
    }:
        section_name = {
            "well.ownership": "ownership",
            "well.trajectory": "trajectory",
            "well.wellbore": "wellbore_evidence",
            "well.casing": "casing",
            "well.war": "war",
        }[command]
        dossier_data = build_dossier(
            data_dir,
            repo,
            args.api_well_number,
            args.sample_limit,
            sections=[section_name],
        )
        data = dossier_data["sections"][section_name]
        return _envelope(
            command,
            {
                "api_well_number": args.api_well_number,
                "sample_limit": args.sample_limit,
            },
            data,
            data_dir=data_dir,
            datasets=_dossier_datasets([section_name]),
            source_family="BSEE sources used by the selected well section",
            join_identifier="API well number plus source serial identifiers",
            warnings=_section_warnings(data),
        ), 0

    if command == "well.applications":
        data = well_applications_page(
            data_dir,
            args.api_well_number,
            page=args.page,
            page_size=args.page_size,
            source=args.source,
            status=args.status,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=["apd_main", "apm_applications", "application_attachments"],
            source_family="BSEE APD and eWell APM applications",
            join_identifier="API_WELL_NUMBER",
            warnings=data.get("warnings", []),
        ), 0

    if command == "well.documents":
        data = well_documents_page(
            data_dir,
            repo,
            args.api_well_number,
            page=args.page,
            page_size=args.page_size,
            source=args.source,
            query=args.query,
            availability=args.availability,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=["frs", "application_attachments"],
            source_family="BSEE APD/APM attachment metadata and FRS well file inventory",
            join_identifier="API_WELL_NUMBER / API",
            warnings=data.get("warnings", []),
        ), 0

    if command == "well.timeline":
        data = well_timeline_page(
            data_dir,
            args.api_well_number,
            page=args.page,
            page_size=args.page_size,
            source=args.source,
            category=args.category,
            date_from=args.date_from,
            date_to=args.date_to,
            has_documents=args.has_documents,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=[
                "apd_main",
                "apm_events",
                "war_main",
                "eor_main",
                "asset_approvals",
                "boreholes",
                "bhp",
                "api_well_completions",
                "api_changes",
                "directional_surveys",
                "well_potential_tests",
                "decom_prop_well",
                "decom_spud_well",
            ],
            source_family="BSEE directly well-linked dated records",
            join_identifier="Exact normalized API well number",
            warnings=data.get("warnings", []),
        ), 0

    if command == "well.timeline-detail":
        data = well_timeline_event(
            data_dir,
            args.api_well_number,
            args.event_id,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=[
                "apd_main",
                "apm_events",
                "war_main",
                "eor_main",
                "asset_approvals",
                "boreholes",
            ],
            source_family="BSEE directly well-linked dated records",
            join_identifier="Exact API well number and event identifier",
            warnings=data.get("warnings", []),
        ), 0

    if command == "well.permits":
        data = well_applications_page(
            data_dir,
            args.api_well_number,
            page=1,
            page_size=args.sample_limit,
            source="APD",
        )
        return _envelope(
            command,
            {"api_well_number": args.api_well_number},
            data,
            data_dir=data_dir,
            datasets=["apd_main", "application_attachments"],
            source_family="BSEE APD permit and attachment data",
            join_identifier="API_WELL_NUMBER",
            warnings=data.get("warnings", []),
        ), 0

    if command == "well.files":
        data = well_documents_page(
            data_dir,
            repo,
            args.api_well_number,
            page=1,
            page_size=args.sample_limit,
            source="FRS",
        )
        return _envelope(
            command,
            {"api_well_number": args.api_well_number},
            data,
            data_dir=data_dir,
            datasets=["frs"],
            source_family="BSEE FRS Well File Inventory",
            join_identifier="API",
            warnings=data.get("warnings", []),
        ), 0

    if command == "fields.list":
        data = field_options(data_dir)
        return _envelope(
            command,
            {},
            data,
            data_dir=data_dir,
            datasets=["boreholes", "azimuth"],
            source_family="BSEE borehole and directional survey data",
            join_identifier="API_WELL_NUMBER",
        ), 0

    if command == "fields.compare":
        data = compare_fields(data_dir, args.fields, args.sample_limit)
        if args.audit:
            data["audit"] = build_field_audit(
                data_dir,
                ",".join(args.fields),
                args.sample_limit,
            )
        return _envelope(
            command,
            {"fields": args.fields, "audit": args.audit},
            data,
            data_dir=data_dir,
            datasets=["boreholes", "azimuth", "structures"],
            source_family="BSEE field, well, trajectory, and structure data",
            join_identifier="FIELD and API_WELL_NUMBER",
            units={
                "water_depth_ft": "ft",
                "first_md_ft": "ft",
                "final_md_ft": "ft",
                "max_tvd_ft": "ft",
            },
        ), 0

    if command == "fields.wells":
        data = compare_fields(data_dir, args.fields, args.sample_limit)
        return _envelope(
            command,
            {"fields": args.fields},
            data,
            data_dir=data_dir,
            datasets=["boreholes", "azimuth", "structures"],
            source_family="BSEE field, well, trajectory, and structure data",
            join_identifier="FIELD and API_WELL_NUMBER",
            units={
                "water_depth_ft": "ft",
                "first_md_ft": "ft",
                "final_md_ft": "ft",
                "max_tvd_ft": "ft",
            },
        ), 0

    if command in {"fields.leases", "fields.lease-context"}:
        data = field_leases(data_dir, args.fields, args.sample_limit)
        return _envelope(
            command,
            {"fields": args.fields},
            data,
            data_dir=data_dir,
            datasets=["boreholes"],
            source_family="BSEE borehole field and bottom-location data",
            join_identifier="FIELD with bottom lease, area, and block",
        ), 0

    if command == "production.compare":
        values = _api_values(args.api_well_numbers)
        data = production_comparison(
            data_dir,
            values,
            args.group_by,
            args.sample_limit,
        )
        return _envelope(
            command,
            {"api_well_numbers": values, "group_by": args.group_by},
            data,
            data_dir=data_dir,
            datasets=["production", "boreholes"],
            source_family="BSEE OGOR-A production data",
            join_identifier="Api Well Number",
            units={
                "oil_bbl": "bbl",
                "gas_mcf": "Mcf",
                "water_bbl": "bbl",
                "oil_bpd": "bbl/day",
                "gas_mcfpd": "Mcf/day",
                "water_bpd": "bbl/day",
            },
        ), 0

    if command == "approvals.search":
        data = search_approvals(
            data_dir,
            page=args.page,
            page_size=args.page_size,
            query=args.query,
            asset_type=args.asset_type,
            asset_identifier=args.asset_identifier,
            business_process=args.business_process,
            approval_type=args.approval_type,
            date_from=args.date_from,
            date_to=args.date_to,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=["asset_approvals"],
            source_family="BSEE alternate compliance, departures, and time extensions",
            join_identifier="Exact source asset identifiers",
        ), 0

    if command == "approvals.options":
        data = approval_options(data_dir)
        return _envelope(
            command,
            {},
            data,
            data_dir=data_dir,
            datasets=["asset_approvals"],
            source_family="BSEE regulatory approvals",
            join_identifier="Distinct normalized attributes",
        ), 0

    if command == "platforms.search":
        data = search_platforms(
            data_dir,
            query=args.query,
            status=args.status,
            company=args.company,
            lease=args.lease,
            area=args.area,
            block=args.block,
            page=args.page,
            page_size=args.page_size,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=["structures"],
            source_family="BSEE platform source attributes with structure enrichment",
            join_identifier="COMPLEX_ID_NUM plus STRUCTURE_NUMBER",
            warnings=_section_warnings(data),
            units={"water_depth_ft": "ft"},
        ), 0

    if command == "platforms.detail":
        data = platform_detail(
            data_dir,
            args.complex_id,
            args.structure_number,
            args.sample_limit,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=[
                "structures",
                "platform_approvals",
                "platform_removals",
                "asset_approvals",
            ],
            source_family="BSEE platform source attributes, approvals, and removals",
            join_identifier="COMPLEX_ID_NUM plus STRUCTURE_NUMBER; exact location/name approvals",
            warnings=_section_warnings(data),
        ), 0

    if command == "pipelines.search":
        data = search_pipelines(
            data_dir,
            status=args.status,
            product=args.product,
            company=args.company,
            query=args.query,
            page=args.page,
            page_size=args.page_size,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=["pipeline_permit_segments"],
            source_family="BSEE pipeline source attributes with permit enrichment",
            join_identifier="segment_number",
            warnings=_section_warnings(data),
            units={
                "segment_length_ft": "ft",
                "max_water_depth_ft": "ft",
                "maop_psi": "psi",
            },
        ), 0

    if command == "pipelines.detail":
        data = pipeline_detail(
            data_dir,
            args.segment_number,
            history_page=args.history_page,
            history_page_size=args.history_page_size,
            sample_limit=args.sample_limit,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=[
                "pipeline_permit_segments",
                "pipeline_submittals",
                "structures",
                "asset_approvals",
            ],
            source_family="BSEE pipeline source attributes, permits, submittals, structures, and approvals",
            join_identifier="segment_number and exact endpoint keys",
            warnings=_section_warnings(data),
        ), 0

    if command in {"bulk.files", "bulk.war"}:
        values = _api_values(args.api_well_numbers)
        data = (
            bulk_files(data_dir, values, args.sample_limit)
            if command == "bulk.files"
            else bulk_war(data_dir, values, args.sample_limit)
        )
        datasets = ["attachments", "frs"] if command == "bulk.files" else ["war_main", "war_text"]
        return _envelope(
            command,
            {"api_well_numbers": values},
            data,
            data_dir=data_dir,
            datasets=datasets,
            source_family="BSEE bulk well evidence",
            join_identifier="API well number",
        ), 0

    if command == "casing.search":
        sizes = parse_casing_sizes(args.sizes)
        if not sizes:
            raise ValueError("Provide at least one numeric casing size")
        data = build_global_casing_search(
            data_dir,
            sizes,
            args.source,
            args.match,
            args.tolerance,
            args.filter,
            args.latest_only,
            args.sample_limit,
        )
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=[
                "apd_main",
                "apd_casing_intervals",
                "apd_casing_sections",
                "war_main",
                "war_tubular",
                "war_tubular_prop",
            ],
            source_family="BSEE APD planned and WAR actual casing data",
            join_identifier="SN_APD and SN_WAR source identifiers",
            units={"casing_size": "in", "depth": "ft"},
        ), 0

    if command == "decommissioning.search":
        data = build_decom_research(
            data_dir=data_dir,
            lease=args.lease,
            api=args.api,
            area=args.area,
            block=args.block,
            min_cost=args.min_cost,
            cost_case=args.cost_case,
            pa_adjustment=args.pa_adjustment.upper() if args.pa_adjustment else None,
            limit=args.sample_limit,
        )
        datasets = [
            "decom_estimates",
            "decom_inst_pipe",
            "decom_inst_plat",
            "decom_prop_pipe",
            "decom_prop_plat",
            "decom_prop_well",
            "decom_spud_well",
            "decom_totals",
        ]
        return _envelope(
            command,
            vars(args),
            data,
            data_dir=data_dir,
            datasets=datasets,
            source_family="BSEE decommissioning inventory and cost estimates",
            join_identifier="API well, lease/auth, area, and block identifiers",
            warnings=_section_warnings(data),
            units={"cost": "USD"},
        ), 0

    if command == "tables.list":
        data = [
            {
                "key": key,
                **spec,
                "available": (data_dir / spec["filename"]).is_file(),
            }
            for key, spec in DATASET_CATALOG.items()
        ]
        return _envelope(
            command,
            {},
            data,
            data_dir=data_dir,
            datasets=list(DATASET_CATALOG),
            source_family="CX O&G dataset catalog",
            join_identifier="Dataset-specific",
        ), 0

    if command == "tables.describe":
        data = describe_table(data_dir, args.table, args.sample_limit)
        key = data["table"]
        return _envelope(
            command,
            {"table": args.table},
            data,
            data_dir=data_dir,
            datasets=[key],
            source_family=DATASET_CATALOG[key]["family"],
            join_identifier="Dataset-specific",
        ), 0

    if command == "tables.rank":
        data = build_ranked_dataset(
            data_dir,
            args.table,
            args.rank_by,
            args.sample_limit,
            descending=args.direction == "desc",
        )
        key = data["table"]
        return _envelope(
            command,
            {
                "table": args.table,
                "rank_by": args.rank_by,
                "direction": args.direction,
            },
            data,
            data_dir=data_dir,
            datasets=[key],
            source_family=DATASET_CATALOG[key]["family"],
            join_identifier="Dataset-specific",
        ), 0

    raise ValueError(f"Unsupported command: {command}")


def _markdown(result: dict[str, Any]) -> str:
    command = result["command"]
    data = result["data"]
    lines = [f"# {command}", "", "## Query", "", "```json"]
    lines.append(json.dumps(result["query"], ensure_ascii=False, indent=2))
    lines.extend(["```", "", "## Result", "", "```json"])
    lines.append(json.dumps(data, ensure_ascii=False, indent=2))
    lines.extend(["```", "", "## Provenance", "", "```json"])
    lines.append(json.dumps(result["provenance"], ensure_ascii=False, indent=2))
    lines.append("```")
    if result["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
    return "\n".join(lines) + "\n"


def emit(result: dict[str, Any], output_format: str, output: Path | None) -> None:
    serializable = to_jsonable(result)
    text = (
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n"
        if output_format == "json"
        else _markdown(serializable)
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        stream = getattr(sys.stdout, "buffer", None)
        if stream is not None:
            stream.write(text.encode("utf-8", errors="replace"))
            stream.flush()
        else:
            sys.stdout.write(text)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result, status = run(args)
        emit(result, args.format, args.output)
        return status
    except (ResearchDataError, FileNotFoundError) as error:
        emit(
            {
                "schema_version": SCHEMA_VERSION,
                "command": "error",
                "query": {},
                "data": None,
                "provenance": {},
                "coverage": [],
                "warnings": [str(error)],
            },
            args.format,
            args.output,
        )
        return 3
    except ValueError as error:
        parser.print_usage(sys.stderr)
        print(f"{parser.prog}: error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"{parser.prog}: unexpected error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
