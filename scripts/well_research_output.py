"""Markdown, JSON, and stdout formatting helpers."""

from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from well_research_core import clean_text, to_jsonable


def print_search(result: dict[str, Any]) -> None:
    print(f"# Keyword Discovery: {result['keyword']}")
    if result.get("filter"):
        print(f"\nFilter: `{result['filter']}`")
    print(f"\n- WAR hit records: {result['war_hit_records']}")
    print(f"- Attachment hit records: {result['attachment_hit_records']}")
    print("\n## Wells")
    if not result["wells"]:
        print("- No wells found in WAR remarks.")
    for row in result["wells"]:
        print(
            f"- {row['API_WELL_NUMBER']}: {row.get('well_name') or ''}, "
            f"{row.get('field') or ''}, hits={row['war_hits']}, "
            f"{row.get('first_date')} to {row.get('last_date')}: {row.get('sample_remark')}"
        )
    print("\n## WAR Samples")
    for row in result["war_samples"]:
        if "TEXT_REMARK" in row:
            row["TEXT_REMARK"] = clean_text(row["TEXT_REMARK"])
        print(f"- {json.dumps(to_jsonable(row), ensure_ascii=False)}")
    print("\n## Attachment Samples")
    for row in result["attachment_samples"]:
        print(f"- {json.dumps(to_jsonable(row), ensure_ascii=False)}")


def print_field_audit(audit: dict[str, Any]) -> None:
    print(f"# Field Audit: {audit['field_query']}")
    print(f"\n- Wells matched: {audit['well_count']}")
    if "availability_counts" in audit:
        print(f"- Availability counts: {json.dumps(to_jsonable(audit['availability_counts']), ensure_ascii=False)}")
    print("\n## Ranked Wells")
    if not audit["wells"]:
        print("- No matching wells.")
    for row in audit["wells"]:
        print(
            f"- {row['API_WELL_NUMBER']}: {row.get('WELL_NAME') or ''} {row.get('WELL_NAME_SUFFIX') or ''}, "
            f"{row.get('OPERATOR FIELD') or row.get('FIELD') or ''}, score={row['data_score']}, "
            f"availability={json.dumps(to_jsonable(row['availability']), ensure_ascii=False)}"
        )


def print_casing_search(result: dict[str, Any]) -> None:
    query = result["query"]
    print("# Global Casing Search")
    print(f"\n- Sizes: {', '.join(str(size) for size in query['sizes'])}")
    print(f"- Source: {query['source']}")
    print(f"- Match mode: {query['match_mode']}")
    print(f"- Tolerance: +/- {query['tolerance']} in")
    print(f"- Latest only: {query['latest_only']}")
    if query.get("filter"):
        print(f"- Filter: `{query['filter']}`")
    if result.get("units"):
        print(f"- Units: {json.dumps(result['units'], ensure_ascii=False)}")
    print(f"- Records scanned: {result['records_scanned']}")
    print(f"- Wells matched: {result['well_count']}")
    print("\n## Wells")
    if not result["wells"]:
        print("- No matching wells.")
    for row in result["wells"]:
        location = ", ".join(str(row.get(col)) for col in ["OPERATOR FIELD", "AREA", "BLOCK"] if row.get(col))
        print(
            f"- {row['API_WELL_NUMBER']}: {row.get('WELL_NAME') or ''} {row.get('WELL_NAME_SUFFIX') or ''}, "
            f"{location}, matched={row['matched_sizes']}, missing={row['missing_sizes']}, "
            f"sources={row['sources_available']}, records={row['record_count']}, "
            f"max_depth_ft={row.get('max_depth_ft')}"
        )
        sample = row.get("sample") or []
        if sample:
            print("  - sample:")
            for sample_row in sample:
                print(f"    - {json.dumps(to_jsonable(sample_row), ensure_ascii=False, default=str)}")


def print_decom_research(result: dict[str, Any]) -> None:
    filters = result["filters"]
    print("# Decommissioning Research")
    print("\n## Filters")
    for key, value in filters.items():
        if value is not None:
            print(f"- {key}: {value}")
    print("\n## Summary")
    for name, count in result["summary"].items():
        print(f"- {name}: {count}")
    for name, section in result["sections"].items():
        print(f"\n## {name.replace('_', ' ').title()}")
        print(f"- records: {section['records']}")
        if section.get("cost_columns"):
            print(f"- cost_columns: {json.dumps(section['cost_columns'], ensure_ascii=False)}")
        if section.get("cost_units"):
            print(f"- cost_units: {json.dumps(section['cost_units'], ensure_ascii=False)}")
        if section.get("cost_sum"):
            print(f"- cost_sum: {json.dumps(to_jsonable(section['cost_sum']), ensure_ascii=False)}")
        if section.get("cost_max"):
            print(f"- cost_max: {json.dumps(to_jsonable(section['cost_max']), ensure_ascii=False)}")
        sample = section.get("sample") or []
        if sample:
            print("- sample:")
            for row in sample:
                print(f"  - {json.dumps(to_jsonable(row), ensure_ascii=False, default=str)}")


def print_data_dir_check(validation: dict[str, Any]) -> None:
    print("# Data Directory Check")
    print(f"\n- Data dir: `{validation['data_dir']}`")
    print(f"- OK: {validation['ok']}")
    print(f"- Present datasets: {validation['present_count']}")
    missing_required = ", ".join(validation["missing_required"]) if validation["missing_required"] else "None"
    print(f"- Missing required: {missing_required}")


def print_table_description(result: dict[str, Any]) -> None:
    print(f"# Table Description: {result['table']}")
    print(f"\n- Source: {result['source']}")
    print(f"- Total records: {result['total_records']}")
    if result.get("metric_aliases"):
        print(f"- Metric aliases: {json.dumps(result['metric_aliases'], ensure_ascii=False)}")
    print("\n## Columns")
    for column in result["columns"]:
        unit = f", unit={column['unit']}" if column.get("unit") else ""
        aliases = f", aliases={column['aliases']}" if column.get("aliases") else ""
        print(f"- {column['name']}{unit}{aliases}")
    if result.get("sample"):
        print("\n## Sample")
        for row in result["sample"]:
            print(f"- {json.dumps(to_jsonable(row), ensure_ascii=False, default=str)}")


def print_ranked_dataset(result: dict[str, Any]) -> None:
    print("# Ranked Dataset")
    print(f"\n- Table: {result['table']}")
    print(f"- Source: {result['source']}")
    if result.get("rank_alias"):
        print(f"- Requested rank by: {result['requested_rank_by']}")
    print(f"- Rank by: {result['rank_by']}")
    if result.get("rank_unit"):
        print(f"- Rank unit: {result['rank_unit']}")
    print(f"- Direction: {result['direction']}")
    print(f"- Records returned: {result['records']}")
    print("\n## Rows")
    if not result["sample"]:
        print("- No rows found.")
    for row in result["sample"]:
        print(f"- {json.dumps(to_jsonable(row), ensure_ascii=False, default=str)}")


def print_dossier(dossier: dict[str, Any]) -> None:
    print(f"# Well Research Dossier: {dossier['api_query']}")
    print(f"\nData dir: `{dossier['data_dir']}`")
    if dossier["identity"]:
        print("\n## Executive Summary")
        fields = [
            "API_WELL_NUMBER",
            "WELL_NAME",
            "WELL_NAME_SUFFIX",
            "COMPANY_NAME",
            "OPERATOR FIELD",
            "FIELD",
            "AREA",
            "BLOCK",
            "LEASE",
            "BH_TOTAL_MD",
            "WELL_BORE_TVD",
            "WATER_DEPTH",
        ]
        for field in fields:
            if field in dossier["identity"]:
                print(f"- {field}: {dossier['identity'][field]}")

    print("\n## Data Availability")
    for name, count in dossier["availability"].items():
        print(f"- {name}: {count}")

    for name, section in dossier["sections"].items():
        print(f"\n## {name.replace('_', ' ').title()}")
        for key, value in section.items():
            if key == "sample":
                continue
            if key == "time_series":
                group_by = value.get("group_by", {}) if isinstance(value, dict) else {}
                groups = value.get("groups", []) if isinstance(value, dict) else []
                print(
                    f"- time_series: records={value.get('records', 0)}, "
                    f"group_by={group_by.get('source_column')}, "
                    f"groups={json.dumps(to_jsonable(groups), ensure_ascii=False)}"
                )
                continue
            print(f"- {key}: {json.dumps(to_jsonable(value), ensure_ascii=False, default=str)}")
        sample = section.get("sample", [])
        if sample:
            print("- sample:")
            for row in sample:
                if "TEXT_REMARK" in row:
                    row["TEXT_REMARK"] = clean_text(row["TEXT_REMARK"])
                print(f"  - {json.dumps(to_jsonable(row), ensure_ascii=False, default=str)}")


def emit_result(
    result: dict[str, Any],
    output_format: str,
    output_path: Path | None,
    markdown_printer,
) -> None:
    if output_format == "json":
        text = json.dumps(to_jsonable(result), indent=2, ensure_ascii=False, default=str) + "\n"
    else:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            markdown_printer(result)
        text = buffer.getvalue()

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        write_stdout(text)


def write_stdout(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="backslashreplace").decode(encoding)
        sys.stdout.write(safe_text)
