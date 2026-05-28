#!/usr/bin/env python
"""Search CX O&G APP records or build a full page-8-style well dossier."""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Pandas requires version .*bottleneck.*")

try:
    import duckdb
except ImportError as exc:
    raise SystemExit(
        "duckdb is required for cx-og-well-research. Use the shared env: "
        "conda activate codex_env && pip install duckdb pandas pyarrow"
    ) from exc

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from well_research_config import INCIDENT_TERMS
from well_research_casing import build_global_casing_search, parse_casing_sizes
from well_research_core import (
    build_ranked_dataset,
    check_data_dir,
    describe_table,
    normalize_production_group_by,
    query_api_dataset,
    repo_root_from,
)
from well_research_decom import build_decom_research
from well_research_dossier import build_dossier
from well_research_evidence import build_field_audit
from well_research_output import (
    emit_result,
    print_casing_search,
    print_data_dir_check,
    print_decom_research,
    print_dossier,
    print_field_audit,
    print_ranked_dataset,
    print_search,
    print_table_description,
)
from well_research_search import search_incident, search_keyword


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="CX O&G APP repo root. Defaults to current directory."
    )
    parser.add_argument("--data-dir", type=Path, help="Parquet data directory. Defaults to <repo>/data.")
    parser.add_argument(
        "--check-data-dir", action="store_true", help="Validate that the Parquet data directory has required files."
    )
    parser.add_argument("--api", help="API well number for full dossier.")
    parser.add_argument("--keyword", help="Keyword discovery across WAR remarks and APD/APM attachment names.")
    parser.add_argument("--incident", help=f"Incident search preset. Known: {', '.join(sorted(INCIDENT_TERMS))}.")
    parser.add_argument("--field", help="Field/operator/name text for field research or audit.")
    parser.add_argument("--filter", help="Optional text filter for keyword discovery, e.g. field/operator/well.")
    parser.add_argument("--casing-sizes", help='Global casing search by size list, e.g. "13.375,9.625".')
    parser.add_argument(
        "--casing-source", choices=["any", "apd", "war"], default="any", help="Casing source for --casing-sizes."
    )
    parser.add_argument(
        "--casing-match", choices=["all", "any"], default="all", help="Require all casing sizes or any one size."
    )
    parser.add_argument("--casing-tolerance", type=float, default=0.01, help="Casing size match tolerance in inches.")
    parser.add_argument(
        "--casing-latest-only", action="store_true", help="Search only the latest APD/WAR casing version per well."
    )
    parser.add_argument(
        "--decom", action="store_true", help="Search decommissioning cost and inventory parquet tables."
    )
    parser.add_argument("--decom-lease", help="Lease/auth number for decommissioning search, e.g. G34454 or 34454.")
    parser.add_argument("--decom-api", help="API well number for decommissioning well cost search.")
    parser.add_argument("--decom-area", help="Area code for decommissioning search.")
    parser.add_argument("--decom-block", help="Block number for decommissioning search.")
    parser.add_argument(
        "--decom-min-cost", type=float, help="Minimum decommissioning cost for selected percentile/case."
    )
    parser.add_argument(
        "--decom-cost-case",
        choices=["p50", "p70", "p90", "dtr"],
        default="p90",
        help="Cost case used for filtering and ranking.",
    )
    parser.add_argument(
        "--decom-pa-adjustment", choices=["Y", "N", "y", "n"], help="Filter lease estimates by PA_ADJUSTMENT_FL."
    )
    parser.add_argument(
        "--include-production", action="store_true", help="Include production history summary in API dossier."
    )
    parser.add_argument(
        "--production-group-by",
        help=(
            "Add plot-ready monthly production points grouped by Completion Name, Product Code, "
            "or Production Interval Code."
        ),
    )
    parser.add_argument(
        "--completion-reconcile",
        action="store_true",
        help="Compare production completion identifiers with EOR physical completion records.",
    )
    parser.add_argument(
        "--casing-compare", action="store_true", help="Add APD planned vs WAR actual casing comparison."
    )
    parser.add_argument(
        "--timeline", action="store_true", help="Add chronological timeline across available well evidence."
    )
    parser.add_argument("--audit", action="store_true", help="Audit data completeness for wells matching --field.")
    parser.add_argument(
        "--describe-table", help="Describe a known dataset key, columns, metric aliases, units, and sample rows."
    )
    parser.add_argument("--rank-table", help="Rank a known dataset key, e.g. wellpath_metrics.")
    parser.add_argument("--rank-by", help="Column name or metric alias to rank by.")
    parser.add_argument(
        "--rank-direction", choices=["desc", "asc"], default="desc", help="Ranking direction. Defaults to desc."
    )
    parser.add_argument("--min-step", type=float, default=100.0, help="Minimum MD spacing in feet for DLS analysis.")
    parser.add_argument("--limit", type=int, default=8, help="Sample row limit.")
    parser.add_argument("--full", action="store_true", help="Return more sample rows.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", type=Path, help="Optional file path for saved JSON or Markdown output.")
    return parser


def resolve_runtime(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[Path, int, dict[str, str] | None]:
    repo = repo_root_from(args.repo)
    data_dir = args.data_dir or (repo / "data")
    limit = 1000 if args.full else args.limit
    try:
        production_group_by = normalize_production_group_by(args.production_group_by)
    except ValueError as exc:
        parser.error(str(exc))
    return data_dir, limit, production_group_by


def run_data_dir_check(args: argparse.Namespace, data_dir: Path) -> int:
    validation = check_data_dir(data_dir)
    emit_result(validation, args.format, args.output, print_data_dir_check)
    return 0 if validation["ok"] else 2


def run_table_description(args: argparse.Namespace, parser: argparse.ArgumentParser, data_dir: Path, limit: int) -> int:
    try:
        result = describe_table(data_dir, args.describe_table, limit)
    except ValueError as exc:
        parser.error(str(exc))
    emit_result(result, args.format, args.output, print_table_description)
    return 0


def run_ranked_dataset(args: argparse.Namespace, parser: argparse.ArgumentParser, data_dir: Path, limit: int) -> int:
    if not args.rank_table or not args.rank_by:
        parser.error("--rank-table and --rank-by must be used together")
    try:
        result = build_ranked_dataset(
            data_dir,
            args.rank_table,
            args.rank_by,
            limit,
            descending=args.rank_direction == "desc",
        )
    except ValueError as exc:
        parser.error(str(exc))
    emit_result(result, args.format, args.output, print_ranked_dataset)
    return 0


def run_casing_search(args: argparse.Namespace, parser: argparse.ArgumentParser, data_dir: Path, limit: int) -> int:
    try:
        casing_sizes = parse_casing_sizes(args.casing_sizes)
    except ValueError as exc:
        parser.error(f"Invalid --casing-sizes value: {exc}")
    if not casing_sizes:
        parser.error("--casing-sizes requires at least one numeric size")
    result = build_global_casing_search(
        data_dir,
        casing_sizes,
        args.casing_source,
        args.casing_match,
        args.casing_tolerance,
        args.filter or args.field,
        args.casing_latest_only,
        limit,
    )
    emit_result(result, args.format, args.output, print_casing_search)
    return 0


def has_decom_request(args: argparse.Namespace) -> bool:
    return any([args.decom, args.decom_lease, args.decom_api, args.decom_area, args.decom_block]) or (
        args.decom_min_cost is not None
    )


def run_decom_research(args: argparse.Namespace, data_dir: Path, limit: int) -> int:
    result = build_decom_research(
        data_dir=data_dir,
        lease=args.decom_lease,
        api=args.decom_api,
        area=args.decom_area,
        block=args.decom_block,
        min_cost=args.decom_min_cost,
        cost_case=args.decom_cost_case,
        pa_adjustment=args.decom_pa_adjustment.upper() if args.decom_pa_adjustment else None,
        limit=limit,
    )
    emit_result(result, args.format, args.output, print_decom_research)
    return 0


def run_discovery(args: argparse.Namespace, data_dir: Path, limit: int) -> int | None:
    if args.incident and not args.api:
        result = search_incident(data_dir, args.incident, args.filter or args.field, limit)
        emit_result(result, args.format, args.output, print_search)
        return 0
    if args.keyword and not args.api:
        result = search_keyword(data_dir, args.keyword, args.filter, limit)
        emit_result(result, args.format, args.output, print_search)
        return 0
    if args.field and (args.audit or not args.api):
        audit = build_field_audit(data_dir, args.field, limit)
        emit_result(audit, args.format, args.output, print_field_audit)
        return 0
    return None


def run_dossier(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    data_dir: Path,
    limit: int,
    production_group_by: dict[str, str] | None,
) -> int:
    if not args.api:
        parser.error(
            "--api, --keyword, --incident, --field, --casing-sizes, --describe-table, "
            "--rank-table, or --decom is required"
        )

    dossier = build_dossier(
        data_dir,
        args.api,
        limit,
        args.min_step,
        args.keyword,
        include_production=args.include_production,
        production_group_by=production_group_by,
        include_completion_reconcile=args.completion_reconcile,
        include_casing_compare=args.casing_compare,
        include_timeline=args.timeline,
    )
    emit_result(dossier, args.format, args.output, print_dossier)
    return 0


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    data_dir, limit, production_group_by = resolve_runtime(args, parser)
    if args.check_data_dir:
        return run_data_dir_check(args, data_dir)
    if args.describe_table:
        return run_table_description(args, parser, data_dir, limit)
    if args.rank_table or args.rank_by:
        return run_ranked_dataset(args, parser, data_dir, limit)
    if args.casing_sizes:
        return run_casing_search(args, parser, data_dir, limit)
    if has_decom_request(args):
        return run_decom_research(args, data_dir, limit)

    discovery_status = run_discovery(args, data_dir, limit)
    if discovery_status is not None:
        return discovery_status
    return run_dossier(args, parser, data_dir, limit, production_group_by)


def main() -> int:
    parser = build_parser()
    return run(parser.parse_args(), parser)


if __name__ == "__main__":
    raise SystemExit(main())
