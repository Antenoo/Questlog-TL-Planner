from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"

EXPECTED_KEYS = {
    "default_build_url",
    "page_timeout_ms",
    "after_load_wait_ms",
    "slot_change_wait_ms",
    "max_scroll_steps",
    "scroll_wait_ms",
    "after_scroll_wait_ms",
    "between_pages_seconds",
    "cache_ttl_hours",
    "default_recursive_depth",
    "show_browser_default",
}


def _read_json_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required configuration file is missing: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Configuration file is not valid JSON: {path.name}") from exc

    if not isinstance(value, dict):
        raise RuntimeError(f"Configuration file must contain a JSON object: {path.name}")
    return value


def load_safe_defaults(example_path: Path = EXAMPLE_PATH) -> dict:
    defaults = _read_json_object(example_path)
    keys = set(defaults)
    if keys != EXPECTED_KEYS:
        missing = sorted(EXPECTED_KEYS - keys)
        extra = sorted(keys - EXPECTED_KEYS)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected: {', '.join(extra)}")
        raise RuntimeError("config.example.json has an unsafe schema (" + "; ".join(details) + ")")

    if defaults.get("default_build_url") != "":
        raise RuntimeError("config.example.json must keep default_build_url empty")
    return defaults


def ensure_local_config(
    config_path: Path = CONFIG_PATH,
    example_path: Path = EXAMPLE_PATH,
) -> bool:
    """Create a missing config exclusively; never replace an existing local config."""
    if config_path.exists():
        return False

    serialized = json.dumps(load_safe_defaults(example_path), indent=2) + "\n"
    try:
        with config_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
    except FileExistsError:
        return False
    return True


def load_config(config_path: Path = CONFIG_PATH, example_path: Path = EXAMPLE_PATH) -> dict:
    ensure_local_config(config_path, example_path)
    return _read_json_object(config_path)


if __name__ == "__main__":
    created = ensure_local_config()
    print("Created config.json from safe defaults." if created else "Existing config.json preserved.")
