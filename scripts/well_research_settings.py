"""Per-machine data-directory settings for the CX O&G research CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path


DATA_DIR_ENV = "CX_OG_DATA_DIR"


def config_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cx-og-well-research" / "config.json"


def saved_data_dir() -> Path | None:
    path = config_path()
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("data_dir")
    except (OSError, ValueError, TypeError):
        return None
    return Path(value).expanduser() if value else None


def resolve_data_dir(explicit: Path | None = None) -> Path:
    configured = explicit
    source = "--data-dir"
    if configured is None and os.environ.get(DATA_DIR_ENV):
        configured = Path(os.environ[DATA_DIR_ENV])
        source = DATA_DIR_ENV
    if configured is None:
        configured = saved_data_dir()
        source = str(config_path())
    if configured is None:
        raise FileNotFoundError(
            "CX O&G data folder is not configured. Ask the user for the folder "
            "containing the CX Parquet files, then run the configure command."
        )

    resolved = configured.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(
            f"The CX O&G data folder configured by {source} is unavailable: {resolved}. "
            "Ask the user for its current location, then run the configure command again."
        )
    return resolved


def save_data_dir(data_dir: Path) -> Path:
    destination = config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"data_dir": str(data_dir.resolve())}, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination
