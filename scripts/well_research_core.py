"""Core helpers for the well research CLI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from well_research_config import (
    CASING_UNITS,
    DATASETS,
    METRIC_ALIASES,
    MIN_REQUIRED_DATASETS,
    PRODUCTION_GROUP_ALIASES,
    TABLE_UNITS,
)


def norm_api(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def repo_root_from(start: Path) -> Path:
    here = start.resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "config.yaml").exists() and (candidate / "data").exists():
            return candidate
    return here


def sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def normalize_production_group_by(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    normalized = alias_key(value)
    if normalized not in PRODUCTION_GROUP_ALIASES:
        allowed = ", ".join(sorted({column for _, column in PRODUCTION_GROUP_ALIASES.values()}))
        raise ValueError(f"Unsupported production group. Use one of: {allowed}")
    field, source_column = PRODUCTION_GROUP_ALIASES[normalized]
    return {"requested": value, "field": field, "source_column": source_column}


def parquet_path(data_dir: Path, key: str) -> Path:
    return data_dir / DATASETS[key]


def parquet_sql(data_dir: Path, key: str) -> str:
    return f"read_parquet({sql_literal(parquet_path(data_dir, key).as_posix())})"


def columns_sql(columns: list[str] | None) -> str:
    if not columns:
        return "*"
    return ", ".join(f'"{col}"' for col in columns)


def duckdb_df(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with duckdb.connect(database=":memory:") as con:
        return con.execute(sql, params or []).fetchdf()


def api_match_sql(column: str) -> str:
    normalized = f"regexp_replace(CAST(\"{column}\" AS VARCHAR), '[^0-9]', '', 'g')"
    return f"({normalized} = ? OR starts_with({normalized}, ?) OR ends_with({normalized}, ?))"


def query_api_dataset(
    data_dir: Path,
    key: str,
    api_column: str,
    api: str,
    columns: list[str] | None = None,
    order_by: str | None = None,
) -> pd.DataFrame:
    path = parquet_path(data_dir, key)
    if not path.exists():
        return pd.DataFrame()
    target = norm_api(api)
    if not target:
        return pd.DataFrame()
    order_clause = f' ORDER BY "{order_by}"' if order_by else ""
    sql = f"""
        SELECT {columns_sql(columns)}
        FROM {parquet_sql(data_dir, key)}
        WHERE {api_match_sql(api_column)}
        {order_clause}
    """
    return duckdb_df(sql, [target, target, target])


def check_data_dir(data_dir: Path) -> dict[str, Any]:
    present = sorted(key for key, filename in DATASETS.items() if (data_dir / filename).exists())
    missing_required = sorted(key for key in MIN_REQUIRED_DATASETS if not parquet_path(data_dir, key).exists())
    return {
        "data_dir": str(data_dir),
        "ok": not missing_required,
        "present_count": len(present),
        "present": present,
        "missing_required": missing_required,
    }


def read_dataset(data_dir: Path, key: str, columns: list[str] | None = None) -> pd.DataFrame:
    path = data_dir / DATASETS[key]
    if not path.exists():
        return pd.DataFrame()
    return duckdb_df(f"SELECT {columns_sql(columns)} FROM {parquet_sql(data_dir, key)}")


def dataset_columns(data_dir: Path, key: str) -> list[str]:
    path = parquet_path(data_dir, key)
    if not path.exists():
        return []
    with duckdb.connect(database=":memory:") as con:
        description = con.execute(f"SELECT * FROM {parquet_sql(data_dir, key)} LIMIT 0").description
    return [str(column[0]) for column in description]


def resolve_dataset_key(table: str, flag_name: str = "--table") -> str:
    key = alias_key(table)
    if key not in DATASETS:
        raise ValueError(f"Unknown {flag_name} '{table}'. Use one of: {', '.join(sorted(DATASETS))}")
    return key


def resolve_metric_column(key: str, requested: str, columns: list[str]) -> tuple[str, str | None]:
    if requested in columns:
        return requested, None
    requested_alias = alias_key(requested)
    resolved = METRIC_ALIASES.get(key, {}).get(requested_alias)
    if resolved and resolved in columns:
        return resolved, requested_alias
    if resolved:
        raise ValueError(f"Alias '{requested}' resolves to '{resolved}', but that column is not in '{key}'")
    raise ValueError(f"Column or alias '{requested}' is not in '{key}'. Available columns: {', '.join(columns)}")


def available_metric_aliases(key: str, columns: list[str]) -> dict[str, str]:
    return {alias: column for alias, column in METRIC_ALIASES.get(key, {}).items() if column in columns}


def describe_table(data_dir: Path, table: str, limit: int) -> dict[str, Any]:
    key = resolve_dataset_key(table)
    if not parquet_path(data_dir, key).exists():
        raise ValueError(f"Dataset '{key}' is missing: {parquet_path(data_dir, key)}")

    columns = dataset_columns(data_dir, key)
    units = units_for(columns, TABLE_UNITS.get(key, {}))
    aliases = available_metric_aliases(key, columns)
    alias_by_column: dict[str, list[str]] = {}
    for alias, column in aliases.items():
        alias_by_column.setdefault(column, []).append(alias)

    sample_limit = max(limit, 0)
    sample = duckdb_df(f"SELECT * FROM {parquet_sql(data_dir, key)} LIMIT {sample_limit}")
    total_records = duckdb_df(f"SELECT COUNT(*) AS count FROM {parquet_sql(data_dir, key)}")
    return {
        "kind": "table_description",
        "data_dir": str(data_dir),
        "table": key,
        "source": DATASETS[key],
        "total_records": int(total_records.iloc[0]["count"]) if not total_records.empty else 0,
        "columns": [
            {
                "name": column,
                "unit": units.get(column),
                "aliases": sorted(alias_by_column.get(column, [])),
            }
            for column in columns
        ],
        "units": units,
        "metric_aliases": aliases,
        "records_sampled": int(len(sample)),
        "sample": top_rows(sample, None, sample_limit),
    }


def build_ranked_dataset(
    data_dir: Path, table: str, rank_by: str, limit: int, descending: bool = True
) -> dict[str, Any]:
    key = resolve_dataset_key(table, "--rank-table")
    if not parquet_path(data_dir, key).exists():
        raise ValueError(f"Dataset '{key}' is missing: {parquet_path(data_dir, key)}")

    columns = dataset_columns(data_dir, key)
    resolved_rank_by, requested_alias = resolve_metric_column(key, rank_by, columns)
    rank_unit = TABLE_UNITS.get(key, {}).get(resolved_rank_by)

    direction = "DESC" if descending else "ASC"
    null_direction = "NULLS LAST"
    sql = f"""
        SELECT *
        FROM {parquet_sql(data_dir, key)}
        ORDER BY
            TRY_CAST("{resolved_rank_by}" AS DOUBLE) {direction} {null_direction},
            "{resolved_rank_by}" {direction} {null_direction}
        LIMIT ?
    """
    rows = duckdb_df(sql, [max(limit, 0)])
    return {
        "kind": "ranked_dataset",
        "data_dir": str(data_dir),
        "table": key,
        "source": DATASETS[key],
        "requested_rank_by": rank_by,
        "rank_alias": requested_alias,
        "rank_by": resolved_rank_by,
        "rank_unit": rank_unit,
        "direction": "desc" if descending else "asc",
        "records": int(len(rows)),
        "sample": top_rows(rows, None, len(rows)),
    }


def filter_api(df: pd.DataFrame, column: str, api: str) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    normalized = df[column].map(norm_api)
    target = norm_api(api)
    exact_match = normalized == target
    suffix_match = normalized.str.endswith(target, na=False)
    prefix_match = normalized.str.startswith(target, na=False)
    mask = exact_match | suffix_match | prefix_match
    return df.loc[mask].copy()


def clean_text(value: Any, max_chars: int = 450) -> str:
    if value is None or pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def top_rows(df: pd.DataFrame, columns: list[str] | None, limit: int) -> list[dict[str, Any]]:
    if df.empty:
        return []
    use_cols = [c for c in (columns or list(df.columns)) if c in df.columns]
    rows = df[use_cols].head(limit).where(pd.notna(df[use_cols].head(limit)), None)
    return rows.to_dict(orient="records")


def date_range(df: pd.DataFrame, column: str) -> dict[str, str] | None:
    if df.empty or column not in df.columns:
        return None
    dates = parse_datetime(df[column]).dropna()
    if dates.empty:
        return None
    return {"first": dates.min().date().isoformat(), "last": dates.max().date().isoformat()}


def parse_datetime(value: Any) -> pd.Series:
    try:
        return pd.to_datetime(value, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(value, errors="coerce")


def numeric_summary(df: pd.DataFrame, columns: list[str]) -> dict[str, dict[str, float]]:
    out = {}
    for col in columns:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if not s.empty:
                out[col] = {"min": float(s.min()), "max": float(s.max()), "mean": float(s.mean())}
    return out


def units_for(columns: list[str], units: dict[str, str]) -> dict[str, str]:
    return {col: units[col] for col in columns if col in units}


def version_metrics(
    df: pd.DataFrame, version_col: str, date_col: str, depth_col: str, size_col: str = "CASING_SIZE"
) -> list[dict[str, Any]]:
    if df.empty or version_col not in df.columns:
        return []
    out = []
    for version in sorted(df[version_col].dropna().unique()):
        version_df = df[df[version_col] == version]
        metric = {
            "version": version,
            "records": int(len(version_df)),
            "date": version_df[date_col].iloc[0] if date_col in version_df.columns and len(version_df) else None,
        }
        if size_col in version_df.columns:
            s = pd.to_numeric(version_df[size_col], errors="coerce").dropna()
            if not s.empty:
                metric["max_size"] = float(s.max())
        if depth_col in version_df.columns:
            d = pd.to_numeric(version_df[depth_col], errors="coerce").dropna()
            if not d.empty:
                metric["max_depth"] = float(d.max())
        spec_cols = [c for c in ["CASING_SIZE", "CASING_WEIGHT", "CASING_GRADE"] if c in version_df.columns]
        if spec_cols:
            metric["unique_specs"] = int(len(version_df[spec_cols].drop_duplicates()))
        metric["units"] = units_for([size_col, depth_col, "max_size", "max_depth", *spec_cols], CASING_UNITS)
        out.append(metric)
    return out
