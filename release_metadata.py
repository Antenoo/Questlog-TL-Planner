from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
METADATA_PATH = ROOT / "release" / "publish.json"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
EXPECTED_KEYS = {
    "schema_version",
    "version",
    "publish",
    "prerelease",
    "display_name",
    "notes",
}


def load_release_metadata(path: Path = METADATA_PATH) -> dict:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Release metadata is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Release metadata is not valid JSON: {path}") from exc

    if not isinstance(metadata, dict) or set(metadata) != EXPECTED_KEYS:
        raise RuntimeError("release/publish.json does not match the required schema")
    if metadata["schema_version"] != 1:
        raise RuntimeError("Unsupported release metadata schema_version")
    if not isinstance(metadata["version"], str) or not VERSION_PATTERN.fullmatch(metadata["version"]):
        raise RuntimeError("Release version must use X.Y.Z numeric format")
    if type(metadata["publish"]) is not bool or type(metadata["prerelease"]) is not bool:
        raise RuntimeError("Release publish and prerelease values must be booleans")
    if (
        not isinstance(metadata["display_name"], str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}", metadata["display_name"])
    ):
        raise RuntimeError("Release display_name contains unsafe characters or is too long")
    if (
        not isinstance(metadata["notes"], str)
        or not metadata["notes"].strip()
        or len(metadata["notes"]) > 20_000
        or "\x00" in metadata["notes"]
    ):
        raise RuntimeError("Release notes are empty, unsafe, or too long")
    return metadata
