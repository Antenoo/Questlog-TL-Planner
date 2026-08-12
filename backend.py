from __future__ import annotations

import json
import logging
import time
import threading
import uuid
import zipfile
import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from scraper_engine import DiskCache, QuestlogScraper, ScanCancelled
from config_bootstrap import load_config
from release_metadata import load_release_metadata

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DATA = ROOT / "data"
CACHE_DIR = DATA / "cache"
EXPORT_DIR = DATA / "exports"
PLANNER_STATE_FILE = DATA / "planner_state.json"
SCAN_HISTORY_FILE = DATA / "scan_history.json"
HEALTH_REPORT_FILE = DATA / "health_report.json"
USER_KNOWLEDGE_DIR = DATA / "user_knowledge"
KNOWLEDGE_ROUTES_FILE = USER_KNOWLEDGE_DIR / "routes.json"
FRONTEND_LOG_FILE = DATA / "frontend_errors.log"
UPDATES_DIR = DATA / "updates"
LIVE_UPDATE_DOWNLOAD_FILE = DATA / "live_update_download.json"
LIVE_UPDATE_RESULT_FILE = DATA / "live_update_result.json"
LIVE_UPDATE_RESTART_LOG_FILE = DATA / "live_update_restart.log"

# Empty directories are not guaranteed to survive ZIP extraction,
# so always create runtime data folders when the app starts.
CACHE_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
USER_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
UPDATES_DIR.mkdir(parents=True, exist_ok=True)

CONFIG = load_config()
RELEASE_METADATA = load_release_metadata()
APP_VERSION = RELEASE_METADATA["version"]

LOG_FILE = DATA / "app.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("questlog-farm-planner")

CACHE = DiskCache(CACHE_DIR, ttl_hours=CONFIG["cache_ttl_hours"])
app = FastAPI(title="Questlog TL Farm Planner")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

JOBS = {}
LOCK = threading.Lock()
STATE_LOCK = threading.Lock()
KNOWLEDGE_LOCK = threading.Lock()



def default_knowledge_routes():
    """Return an empty local knowledge store without publishing player data."""
    return {
        "schema_version": 1,
        "updated_at_utc": None,
        "routes": [],
    }


def _normalize_knowledge_routes(data):
    clean = data if isinstance(data, dict) else default_knowledge_routes()
    clean.setdefault("schema_version", 1)
    raw_routes = clean.get("routes")
    if not isinstance(raw_routes, list):
        raw_routes = []

    allowed_sources = {"in-game-confirmed", "manual-needs-verification"}
    routes = []
    for raw in raw_routes:
        if not isinstance(raw, dict):
            continue

        route = dict(raw)
        route["id"] = str(route.get("id") or f"route-{uuid.uuid4()}")
        route["target_name"] = str(route.get("target_name") or "").strip()
        route["target_url"] = str(route.get("target_url") or "").strip()
        route["route_label"] = str(route.get("route_label") or "").strip()
        route["notes"] = str(route.get("notes") or "").strip()
        route["source_type"] = (
            route.get("source_type")
            if route.get("source_type") in allowed_sources
            else "manual-needs-verification"
        )

        aliases = route.get("aliases")
        route["aliases"] = [
            str(x).strip() for x in aliases
            if str(x).strip()
        ] if isinstance(aliases, list) else []

        steps = []
        for step in route.get("steps") or []:
            if isinstance(step, str):
                name = step.strip()
                note = ""
            elif isinstance(step, dict):
                name = str(step.get("name") or "").strip()
                note = str(step.get("note") or "").strip()
            else:
                continue
            if name:
                steps.append({"name": name, "note": note})
        route["steps"] = steps

        if route["target_name"] or route["target_url"]:
            routes.append(route)

    clean["routes"] = routes
    return clean


def load_knowledge_routes():
    if not KNOWLEDGE_ROUTES_FILE.exists():
        data = default_knowledge_routes()
        save_knowledge_routes(data)
        return data

    try:
        data = json.loads(KNOWLEDGE_ROUTES_FILE.read_text(encoding="utf-8"))
        return _normalize_knowledge_routes(data)
    except Exception:
        LOGGER.exception("Could not read user knowledge routes; preserving file and using empty in-memory fallback")
        return {"schema_version": 1, "updated_at_utc": None, "routes": []}


def save_knowledge_routes(data):
    clean = _normalize_knowledge_routes(data)
    now = datetime.now(timezone.utc).isoformat()
    clean["updated_at_utc"] = now

    for route in clean["routes"]:
        route.setdefault("created_at_utc", now)
        route["updated_at_utc"] = now

    USER_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = KNOWLEDGE_ROUTES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(KNOWLEDGE_ROUTES_FILE)
    return clean


def default_planner_state():
    return {
        "schema_version": 1,
        "updated_at_utc": None,
        "settings": {},
        "builds": {},
    }


def load_planner_state():
    if not PLANNER_STATE_FILE.exists():
        return default_planner_state()
    try:
        data = json.loads(PLANNER_STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("planner state must be an object")
        data.setdefault("schema_version", 1)
        data.setdefault("settings", {})
        data.setdefault("builds", {})
        return data
    except Exception:
        LOGGER.exception("Could not read planner state; returning empty state")
        return default_planner_state()


def save_planner_state(state):
    clean = state if isinstance(state, dict) else default_planner_state()
    clean.setdefault("schema_version", 1)
    clean.setdefault("settings", {})
    clean.setdefault("builds", {})
    clean["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = PLANNER_STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PLANNER_STATE_FILE)
    return clean


def _item_identity(item):
    return (item or {}).get("item_url") or (item or {}).get("item_name") or ""


def _stable_item_evidence(item):
    item = item or {}
    return {
        "item_url": item.get("item_url"),
        "acquisition": item.get("acquisition", []),
        "container_contents": item.get("container_contents", []),
        "crafting_recipes": item.get("crafting_recipes", []),
    }


def _evidence_tokens(item):
    tokens = set()
    for rel in (item or {}).get("acquisition", []):
        kind = rel.get("kind", "")
        for row in rel.get("rows", []):
            row_key = json.dumps({
                "kind": kind,
                "Name": row.get("Name"),
                "Type": row.get("Type"),
                "Difficulty": row.get("Difficulty"),
                "Quantity": row.get("Quantity"),
                "Probability": row.get("Probability"),
                "Drop Type": row.get("Drop Type"),
            }, ensure_ascii=False, sort_keys=True)
            tokens.add(row_key)
    for rel in (item or {}).get("container_contents", []):
        for row in rel.get("rows", []):
            row_key = json.dumps({
                "kind": "Container Contents",
                "Name": row.get("Name"),
                "Quantity": row.get("Quantity"),
                "Probability": row.get("Probability"),
                "Drop Type": row.get("Drop Type"),
            }, ensure_ascii=False, sort_keys=True)
            tokens.add(row_key)
    return tokens


def summarize_scan_diff(previous, current):
    if not previous:
        return {
            "baseline": True,
            "equipment_changes": [],
            "data_changed_items": [],
            "evidence_added": 0,
            "evidence_removed": 0,
            "summary": "Baseline scan saved; future scans can be compared against it.",
        }

    prev_by_slot = {int(x.get("slot_index", -1)): x for x in previous.get("items", [])}
    cur_by_slot = {int(x.get("slot_index", -1)): x for x in current.get("items", [])}
    slots = sorted(set(prev_by_slot) | set(cur_by_slot))

    equipment_changes = []
    data_changed_items = []
    evidence_added = 0
    evidence_removed = 0

    for slot in slots:
        a = prev_by_slot.get(slot)
        b = cur_by_slot.get(slot)
        aid = _item_identity(a)
        bid = _item_identity(b)
        if aid != bid:
            equipment_changes.append({
                "slot_index": slot,
                "before": (a or {}).get("item_name"),
                "after": (b or {}).get("item_name"),
            })
            continue
        if not a or not b:
            continue

        if json.dumps(_stable_item_evidence(a), ensure_ascii=False, sort_keys=True) != json.dumps(_stable_item_evidence(b), ensure_ascii=False, sort_keys=True):
            data_changed_items.append(b.get("item_name") or a.get("item_name") or f"Slot {slot}")

        at = _evidence_tokens(a)
        bt = _evidence_tokens(b)
        evidence_added += len(bt - at)
        evidence_removed += len(at - bt)

    if not equipment_changes and not data_changed_items and evidence_added == 0 and evidence_removed == 0:
        text = "No build or Questlog evidence changes detected."
    else:
        parts = []
        if equipment_changes:
            parts.append(f"{len(equipment_changes)} equipment slot change(s)")
        if data_changed_items:
            parts.append(f"{len(data_changed_items)} item data change(s)")
        if evidence_added or evidence_removed:
            parts.append(f"{evidence_added} evidence row(s) added / {evidence_removed} removed")
        text = "; ".join(parts) + "."

    return {
        "baseline": False,
        "equipment_changes": equipment_changes,
        "data_changed_items": data_changed_items,
        "evidence_added": evidence_added,
        "evidence_removed": evidence_removed,
        "summary": text,
    }


def load_previous_scan_for_build(build_url):
    scans = sorted(EXPORT_DIR.glob("farm_scan_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    for path in scans:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("build_url") == build_url:
                return data, path.name
        except Exception:
            LOGGER.exception("Could not inspect previous scan %s", path)
    return None, None


def append_scan_history(entry):
    history = []
    if SCAN_HISTORY_FILE.exists():
        try:
            history = json.loads(SCAN_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("Could not read scan history; starting a new history file")
            history = []
    if not isinstance(history, list):
        history = []
    history.append(entry)
    history = history[-60:]
    tmp = SCAN_HISTORY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SCAN_HISTORY_FILE)


class ScanRequest(BaseModel):
    build_url: str
    show_browser: bool = True
    force_refresh: bool = False
    refresh_mode: str = "normal"
    stale_after_hours: int | None = None
    recursive_depth: int = 2


class ConfigUpdateRequest(BaseModel):
    cache_ttl_hours: int | None = None


class FrontendLogRequest(BaseModel):
    kind: str = "error"
    message: str = ""
    source: str = ""
    line: int | None = None
    column: int | None = None
    stack: str = ""
    app_version: str = ""


class UpdateRepositoryRequest(BaseModel):
    repository: str


@app.get("/")
def index():
    template = (STATIC / "index.html").read_text(encoding="utf-8")
    placeholder = "__PLANNER_VERSION__"
    if placeholder not in template:
        raise HTTPException(status_code=500, detail="Frontend version placeholder is missing.")
    return HTMLResponse(
        template.replace(placeholder, APP_VERSION),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
GITHUB_API_VERSION = "2026-03-10"
UPDATE_ASSET_STABLE_NAME = "Questlog_TL_Farm_Planner_UPDATE.zip"
UPDATE_CHECK_CACHE_SECONDS = 5 * 60
UPDATE_CHECK_FALLBACK_BACKOFF_SECONDS = 60
UPDATE_CHECK_LOCK = threading.Lock()
UPDATE_CHECK_CACHE = {}
UPDATE_CHECK_BACKOFF = {}


class GitHubRateLimitError(RuntimeError):
    def __init__(self, message, retry_at):
        super().__init__(message)
        self.retry_at = float(retry_at)


def _version_tuple(value):
    nums = [int(x) for x in re.findall(r"\d+", str(value or ""))]
    while len(nums) < 4:
        nums.append(0)
    return tuple(nums[:4])


def _normalize_repository(repository):
    value = str(repository or "").strip().strip("/")
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/"):].strip("/")
    if value.endswith(".git"):
        value = value[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise HTTPException(
            status_code=400,
            detail="GitHub repository must look like OWNER/REPOSITORY.",
        )
    return value


def _github_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": f"Questlog-TL-Farm-Planner/{APP_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(2_000_000)
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HTTPException(
                status_code=404,
                detail="No public latest GitHub Release was found for that repository.",
            )
        if exc.code in {403, 429}:
            now = time.time()
            retry_at = now + UPDATE_CHECK_FALLBACK_BACKOFF_SECONDS
            headers = exc.headers or {}

            try:
                retry_after = int(headers.get("Retry-After") or 0)
            except (TypeError, ValueError):
                retry_after = 0
            try:
                rate_reset = int(headers.get("X-RateLimit-Reset") or 0)
            except (TypeError, ValueError):
                rate_reset = 0

            if retry_after > 0:
                retry_at = max(retry_at, now + retry_after)
            if str(headers.get("X-RateLimit-Remaining") or "").strip() == "0" and rate_reset > 0:
                retry_at = max(retry_at, float(rate_reset) + 1)

            retry_time = datetime.fromtimestamp(retry_at).astimezone()
            offset_minutes = int((retry_time.utcoffset() or timedelta()).total_seconds() // 60)
            offset_sign = "+" if offset_minutes >= 0 else "-"
            offset_minutes = abs(offset_minutes)
            retry_zone = f"UTC{offset_sign}{offset_minutes // 60:02d}:{offset_minutes % 60:02d}"
            retry_text = retry_time.strftime("%Y-%m-%d %H:%M")
            raise GitHubRateLimitError(
                "GitHub temporarily limited public update checks after too many requests. "
                f"The installed planner is unaffected; try again after {retry_text} {retry_zone} (local time).",
                retry_at,
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"GitHub update check failed with HTTP {exc.code}.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach GitHub for update check: {exc}",
        )


def _select_release_asset(release):
    assets = release.get("assets") or []
    version = str(release.get("tag_name") or "").lstrip("vV")
    version_token = version.replace(".", "_").lower()

    zip_assets = [
        a for a in assets
        if str(a.get("name") or "").lower().endswith(".zip")
        and str(a.get("browser_download_url") or "").startswith("https://github.com/")
    ]

    for asset in zip_assets:
        if asset.get("name") == UPDATE_ASSET_STABLE_NAME:
            return asset

    for asset in zip_assets:
        name = str(asset.get("name") or "").lower()
        if (
            name.startswith("questlog_tl_farm_planner_update_v")
            and version_token
            and version_token in name
        ):
            return asset

    matching = [
        a for a in zip_assets
        if str(a.get("name") or "").lower().startswith("questlog_tl_farm_planner_update")
    ]
    return matching[0] if len(matching) == 1 else None


def _latest_release(repository):
    repo = _normalize_repository(repository)
    cache_key = repo.lower()
    now = time.time()

    with UPDATE_CHECK_LOCK:
        cached = UPDATE_CHECK_CACHE.get(cache_key)
        if cached and now < cached["expires_at"]:
            return dict(cached["result"])

        blocked = UPDATE_CHECK_BACKOFF.get(cache_key)
        if blocked and now < blocked["retry_at"]:
            raise HTTPException(status_code=429, detail=blocked["message"])
        if blocked:
            UPDATE_CHECK_BACKOFF.pop(cache_key, None)

    try:
        release = _github_json(f"https://api.github.com/repos/{repo}/releases/latest")
    except GitHubRateLimitError as exc:
        message = str(exc)
        with UPDATE_CHECK_LOCK:
            UPDATE_CHECK_BACKOFF[cache_key] = {
                "retry_at": exc.retry_at,
                "message": message,
            }
        raise HTTPException(status_code=429, detail=message) from exc

    asset = _select_release_asset(release)

    tag = str(release.get("tag_name") or "").strip()
    latest_version = tag.lstrip("vV")
    digest = str((asset or {}).get("digest") or "")
    verified = digest.lower().startswith("sha256:") and len(digest.split(":", 1)[-1]) == 64

    result = {
        "repository": repo,
        "release_id": release.get("id"),
        "tag_name": tag,
        "version": latest_version,
        "name": release.get("name") or tag,
        "notes": str(release.get("body") or "")[:12000],
        "html_url": release.get("html_url"),
        "published_at": release.get("published_at"),
        "asset": {
            "id": asset.get("id"),
            "name": asset.get("name"),
            "size": asset.get("size"),
            "download_url": asset.get("browser_download_url"),
            "digest": digest,
            "verified": verified,
        } if asset else None,
        "update_available": bool(latest_version) and _version_tuple(latest_version) > _version_tuple(APP_VERSION),
        "current_version": APP_VERSION,
    }
    with UPDATE_CHECK_LOCK:
        UPDATE_CHECK_CACHE[cache_key] = {
            "expires_at": time.time() + UPDATE_CHECK_CACHE_SECONDS,
            "result": result,
        }
        UPDATE_CHECK_BACKOFF.pop(cache_key, None)
    return dict(result)


def _validate_update_zip(path):
    required_payload = False
    required_update_manager = False
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = name.split("/")
            if name.startswith("/") or ".." in parts:
                raise HTTPException(status_code=400, detail=f"Unsafe path in update ZIP: {name}")
            if name.startswith("_update_payload/") and not info.is_dir():
                required_payload = True
            if name == "update_manager.py":
                required_update_manager = True

    if not required_payload or not required_update_manager:
        raise HTTPException(
            status_code=400,
            detail="Update ZIP is missing required planner update files.",
        )


def _download_latest_update(repository):
    release = _latest_release(repository)
    if not release["update_available"]:
        raise HTTPException(status_code=409, detail="No newer release is available.")

    asset = release.get("asset")
    if not asset:
        raise HTTPException(
            status_code=409,
            detail="The latest GitHub Release has no recognized planner update ZIP asset.",
        )
    if not asset.get("verified"):
        raise HTTPException(
            status_code=409,
            detail="The release asset has no SHA-256 digest, so live install was refused. Manual ZIP installation remains available.",
        )

    url = asset["download_url"]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise HTTPException(status_code=400, detail="Update asset URL is not a GitHub HTTPS release URL.")

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", asset["name"] or "planner_update.zip")
    destination = UPDATES_DIR / safe_name
    temp = destination.with_suffix(destination.suffix + ".part")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"Questlog-TL-Farm-Planner/{APP_VERSION}"},
    )

    sha = hashlib.sha256()
    total = 0
    max_bytes = 100 * 1024 * 1024

    try:
        with urllib.request.urlopen(request, timeout=30) as response, temp.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError("Update download exceeded the 100 MB safety limit.")
                sha.update(chunk)
                out.write(chunk)
    except Exception as exc:
        try:
            temp.unlink()
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=f"Could not download the update: {exc}")

    actual = sha.hexdigest().lower()
    expected = asset["digest"].split(":", 1)[1].lower()
    if actual != expected:
        try:
            temp.unlink()
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail="Downloaded update failed SHA-256 verification.",
        )

    temp.replace(destination)
    _validate_update_zip(destination)

    state = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository": release["repository"],
        "release_id": release["release_id"],
        "version": release["version"],
        "tag_name": release["tag_name"],
        "asset_name": asset["name"],
        "zip_path": str(destination),
        "sha256": actual,
        "verified": True,
    }
    LIVE_UPDATE_DOWNLOAD_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return release, state


@app.get("/api/update/status")
def update_status(repository: str):
    return _latest_release(repository)


@app.post("/api/update/download")
def update_download(req: UpdateRepositoryRequest):
    release, state = _download_latest_update(req.repository)
    return {
        "ok": True,
        "release": release,
        "download": {
            "version": state["version"],
            "asset_name": state["asset_name"],
            "sha256": state["sha256"],
            "verified": state["verified"],
        },
    }


@app.post("/api/update/apply")
def update_apply(req: UpdateRepositoryRequest):
    repo = _normalize_repository(req.repository)

    if not LIVE_UPDATE_DOWNLOAD_FILE.exists():
        raise HTTPException(status_code=409, detail="No verified update has been downloaded yet.")

    try:
        state = json.loads(LIVE_UPDATE_DOWNLOAD_FILE.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=409, detail="Downloaded update state is unreadable.")

    if state.get("repository") != repo or not state.get("verified"):
        raise HTTPException(status_code=409, detail="Downloaded update does not match this repository.")

    zip_path = Path(state.get("zip_path") or "")
    if not zip_path.exists():
        raise HTTPException(status_code=409, detail="Verified update ZIP is missing.")

    # Re-check SHA immediately before handing the ZIP to the external updater.
    sha = hashlib.sha256()
    with zip_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    if sha.hexdigest().lower() != str(state.get("sha256") or "").lower():
        raise HTTPException(status_code=400, detail="Staged update no longer matches its verified SHA-256.")

    helper = ROOT / "LIVE_UPDATE_HELPER.py"
    if not helper.exists():
        raise HTTPException(status_code=500, detail="LIVE_UPDATE_HELPER.py is missing.")

    runtime_helper = UPDATES_DIR / f"live_update_helper_{uuid.uuid4().hex}.py"
    shutil.copy2(helper, runtime_helper)

    command = [
        sys.executable,
        str(runtime_helper),
        "--root", str(ROOT),
        "--zip", str(zip_path),
        "--pid", str(os.getpid()),
        "--version", str(state.get("version") or ""),
    ]

    kwargs = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)

    try:
        subprocess.Popen(command, **kwargs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not start live updater: {exc}")

    # Give FastAPI enough time to send the response, then release the port.
    def stop_for_update():
        time.sleep(1.25)
        os._exit(0)

    threading.Thread(target=stop_for_update, daemon=True).start()

    return {
        "ok": True,
        "restarting": True,
        "version": state.get("version"),
        "message": "Verified update is being applied. The server will restart automatically.",
    }


@app.post("/api/frontend-log")
def frontend_log(req: FrontendLogRequest):
    def clean(value, limit):
        text = str(value or "").replace("\x00", "")
        return text[:limit]

    entry = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": clean(req.kind, 40),
        "message": clean(req.message, 2000),
        "source": clean(req.source, 1000),
        "line": req.line,
        "column": req.column,
        "stack": clean(req.stack, 8000),
        "app_version": clean(req.app_version, 40),
    }

    try:
        FRONTEND_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with FRONTEND_LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Keep the file bounded. UI errors should help diagnosis, not grow forever.
        if FRONTEND_LOG_FILE.stat().st_size > 512_000:
            lines = FRONTEND_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            FRONTEND_LOG_FILE.write_text(
                "\n".join(lines[-250:]) + ("\n" if lines else ""),
                encoding="utf-8",
            )
    except Exception:
        LOGGER.exception("Could not persist frontend error report")

    return {"ok": True}


@app.get("/api/config")
def config():
    return {
        "default_build_url": CONFIG["default_build_url"],
        "cache_ttl_hours": CONFIG["cache_ttl_hours"],
        "default_recursive_depth": CONFIG["default_recursive_depth"],
        "default_stale_after_hours": min(72, int(CONFIG["cache_ttl_hours"])),
        "cache_ttl_min_hours": 1,
        "cache_ttl_max_hours": 720,
    }


@app.put("/api/config")
def config_update(req: ConfigUpdateRequest):
    changed = {}

    if req.cache_ttl_hours is not None:
        ttl = max(1, min(int(req.cache_ttl_hours), 720))
        CONFIG["cache_ttl_hours"] = ttl
        CACHE.ttl = timedelta(hours=ttl)
        changed["cache_ttl_hours"] = ttl

    if changed:
        config_path = ROOT / "config.json"
        tmp = config_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(config_path)

    return {
        "ok": True,
        "changed": changed,
        "cache_ttl_hours": CONFIG["cache_ttl_hours"],
    }


@app.get("/api/planner-state")
def planner_state():
    with STATE_LOCK:
        return {"state": load_planner_state(), "file": str(PLANNER_STATE_FILE.name)}


@app.put("/api/planner-state")
def planner_state_save(state: dict):
    with STATE_LOCK:
        saved = save_planner_state(state)
    return {"ok": True, "updated_at_utc": saved.get("updated_at_utc")}


@app.get("/api/knowledge-routes")
def knowledge_routes():
    with KNOWLEDGE_LOCK:
        data = load_knowledge_routes()
    return {
        "data": data,
        "file": str(KNOWLEDGE_ROUTES_FILE.relative_to(DATA)),
    }


@app.put("/api/knowledge-routes")
def knowledge_routes_save(data: dict):
    with KNOWLEDGE_LOCK:
        saved = save_knowledge_routes(data)
    return {
        "ok": True,
        "updated_at_utc": saved.get("updated_at_utc"),
        "route_count": len(saved.get("routes", [])),
    }


@app.get("/api/scan-history")
def scan_history(limit: int = 12):
    limit = max(1, min(int(limit), 50))
    if not SCAN_HISTORY_FILE.exists():
        return {"entries": []}
    try:
        data = json.loads(SCAN_HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        LOGGER.exception("Could not read scan history")
        data = []
    return {"entries": list(reversed(data[-limit:]))}



def _latest_scan_file():
    scans = sorted(
        EXPORT_DIR.glob("farm_scan_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in scans:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return path, data
        except Exception:
            LOGGER.exception("Could not inspect scan for freshness: %s", path)
    return None, None


def _page_relationship_kinds(record):
    kinds = set()
    for rel in (record or {}).get("acquisition", []) or []:
        kind = str(rel.get("kind") or "").strip()
        if kind:
            kinds.add(kind)
    if (record or {}).get("container_contents"):
        kinds.add("Container Contents")
    return kinds


def _freshness_url_categories(scan):
    categories = {
        "equipment": {"label": "Equipped item DB pages", "urls": set()},
        "expanded": {"label": "Expanded route pages", "urls": set()},
        "direct": {"label": "Direct-drop evidence", "urls": set()},
        "dungeon": {"label": "Dungeon-source evidence", "urls": set()},
        "containers": {"label": "Container contents", "urls": set()},
        "recipes": {"label": "Crafting recipe costs", "urls": set()},
    }

    def classify(url, record, base_category):
        if not url:
            return
        categories[base_category]["urls"].add(url)
        kinds = _page_relationship_kinds(record)
        if "Direct Drops" in kinds:
            categories["direct"]["urls"].add(url)
        if "Dungeon Sources" in kinds:
            categories["dungeon"]["urls"].add(url)
        if "Container Contents" in kinds:
            categories["containers"]["urls"].add(url)

    for item in (scan or {}).get("items", []) or []:
        item_record = {
            "acquisition": item.get("acquisition", []),
            "container_contents": item.get("container_contents", []),
        }
        classify(item.get("item_url"), item_record, "equipment")

        for node in (item.get("expanded_nodes") or {}).values():
            classify(node.get("url") or node.get("identity_url"), node, "expanded")

        for recipe in item.get("crafting_recipes", []) or []:
            url = recipe.get("recipe_url")
            if url:
                categories["recipes"]["urls"].add(url)

    return categories


def _freshness_category_payload(category, stale_after_hours):
    urls = sorted(category["urls"])
    entries = []
    for url in urls:
        meta = CACHE.metadata(url)
        entries.append({
            "url": url,
            "exists": bool(meta.get("exists")),
            "cached_at": meta.get("cached_at"),
            "age_hours": meta.get("age_hours"),
        })

    cached = [e for e in entries if e["exists"] and e["age_hours"] is not None]
    missing = [e for e in entries if not e["exists"]]
    stale = [
        e for e in cached
        if float(e["age_hours"]) >= float(stale_after_hours)
    ]

    ages = [float(e["age_hours"]) for e in cached]
    oldest_age = max(ages) if ages else None
    newest_age = min(ages) if ages else None

    if not urls:
        status = "empty"
    elif missing:
        status = "missing"
    elif stale:
        status = "stale"
    elif oldest_age is not None and oldest_age >= float(stale_after_hours) * 0.5:
        status = "aging"
    else:
        status = "fresh"

    return {
        "label": category["label"],
        "url_count": len(urls),
        "cached_count": len(cached),
        "missing_count": len(missing),
        "stale_count": len(stale),
        "oldest_age_hours": oldest_age,
        "newest_age_hours": newest_age,
        "status": status,
        "entries": entries,
    }


@app.get("/api/freshness")
def freshness(stale_after_hours: int = 72):
    threshold = max(1, min(int(stale_after_hours), 720))
    scan_path, scan = _latest_scan_file()

    if scan is None:
        return {
            "available": False,
            "stale_after_hours": threshold,
            "summary": {
                "unique_urls": 0,
                "cached_urls": 0,
                "stale_urls": 0,
                "missing_urls": 0,
            },
            "categories": {},
            "stale_pages": [],
            "build_scan": None,
            "knowledge_routes": None,
        }

    raw_categories = _freshness_url_categories(scan)
    categories = {
        key: _freshness_category_payload(value, threshold)
        for key, value in raw_categories.items()
    }

    url_to_categories = {}
    for key, category in raw_categories.items():
        for url in category["urls"]:
            url_to_categories.setdefault(url, set()).add(key)

    all_urls = sorted(url_to_categories)
    stale_pages = []
    cached_count = 0
    stale_count = 0
    missing_count = 0

    for url in all_urls:
        meta = CACHE.metadata(url)
        exists = bool(meta.get("exists"))
        age = meta.get("age_hours")
        if exists:
            cached_count += 1
        else:
            missing_count += 1

        is_stale = bool(
            exists
            and age is not None
            and float(age) >= float(threshold)
        )
        if is_stale:
            stale_count += 1

        if is_stale or not exists:
            stale_pages.append({
                "url": url,
                "cached_at": meta.get("cached_at"),
                "age_hours": age,
                "missing": not exists,
                "categories": sorted(url_to_categories.get(url, [])),
            })

    stale_pages.sort(
        key=lambda e: (
            0 if e["missing"] else 1,
            -(float(e["age_hours"]) if e["age_hours"] is not None else 999999),
        )
    )

    scan_generated = scan.get("generated_at_utc")
    scan_age_hours = None
    try:
        generated = datetime.fromisoformat(scan_generated)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        scan_age_hours = max(
            0.0,
            (datetime.now(timezone.utc) - generated).total_seconds() / 3600.0,
        )
    except Exception:
        pass

    knowledge = load_knowledge_routes()
    knowledge_updated = knowledge.get("updated_at_utc")
    knowledge_age_hours = None
    try:
        updated = datetime.fromisoformat(knowledge_updated)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        knowledge_age_hours = max(
            0.0,
            (datetime.now(timezone.utc) - updated).total_seconds() / 3600.0,
        )
    except Exception:
        if KNOWLEDGE_ROUTES_FILE.exists():
            knowledge_age_hours = max(
                0.0,
                (time.time() - KNOWLEDGE_ROUTES_FILE.stat().st_mtime) / 3600.0,
            )

    return {
        "available": True,
        "stale_after_hours": threshold,
        "summary": {
            "unique_urls": len(all_urls),
            "cached_urls": cached_count,
            "stale_urls": stale_count,
            "missing_urls": missing_count,
        },
        "categories": categories,
        "stale_pages": stale_pages[:80],
        "build_scan": {
            "filename": scan_path.name if scan_path else None,
            "generated_at_utc": scan_generated,
            "age_hours": scan_age_hours,
            "scan_mode": scan.get("scan_mode", "legacy"),
        },
        "knowledge_routes": {
            "updated_at_utc": knowledge_updated,
            "age_hours": knowledge_age_hours,
            "route_count": len(knowledge.get("routes", [])),
            "source": "app-owned manual/in-game knowledge",
        },
    }


def _health_check(check_id, label, status, detail, category="Backend"):
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "detail": detail,
        "category": category,
    }


def run_backend_self_test():
    checks = []

    checks.append(_health_check(
        "backend_version", "Backend version", "pass",
        f"Backend v{APP_VERSION} is responding."
    ))

    required_config = {"default_build_url", "cache_ttl_hours", "default_recursive_depth"}
    missing_config = sorted(required_config - set(CONFIG))
    checks.append(_health_check(
        "config", "Configuration",
        "fail" if missing_config else "pass",
        f"Missing config key(s): {', '.join(missing_config)}"
        if missing_config else f"config.json contains the required planner settings; cache TTL is {CONFIG['cache_ttl_hours']}h."
    ))

    probe = DATA / ".health_write_test.tmp"
    try:
        payload = f"questlog-health-{uuid.uuid4()}"
        probe.write_text(payload, encoding="utf-8")
        if probe.read_text(encoding="utf-8") != payload:
            raise RuntimeError("write/read round-trip did not match")
        checks.append(_health_check(
            "data_writable", "App data folder", "pass",
            "data/ is writable and readable."
        ))
    except Exception as exc:
        checks.append(_health_check(
            "data_writable", "App data folder", "fail",
            f"Could not write/read data/: {exc}"
        ))
    finally:
        try:
            probe.unlink(missing_ok=True)
        except Exception:
            pass

    try:
        state = load_planner_state()
        schema_ok = (
            isinstance(state, dict)
            and isinstance(state.get("settings"), dict)
            and isinstance(state.get("builds"), dict)
        )
        checks.append(_health_check(
            "planner_state_read", "Planner state",
            "pass" if schema_ok else "fail",
            f"planner_state.json is readable; {len(state.get('builds', {}))} build state(s) stored."
            if schema_ok else "Planner state does not match the expected schema."
        ))
    except Exception as exc:
        state = default_planner_state()
        checks.append(_health_check(
            "planner_state_read", "Planner state", "fail",
            f"Could not read planner state: {exc}"
        ))

    state_probe = DATA / ".planner_state_health.tmp"
    try:
        state_probe.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        parsed = json.loads(state_probe.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise RuntimeError("round-trip did not return an object")
        checks.append(_health_check(
            "planner_state_writable", "Planner state write safety", "pass",
            "Planner state can be serialized and written safely."
        ))
    except Exception as exc:
        checks.append(_health_check(
            "planner_state_writable", "Planner state write safety", "fail",
            f"Planner-state write test failed: {exc}"
        ))
    finally:
        try:
            state_probe.unlink(missing_ok=True)
        except Exception:
            pass

    scans = sorted(EXPORT_DIR.glob("farm_scan_*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not scans:
        checks.append(_health_check(
            "latest_scan", "Latest scan export", "warn",
            "No farm_scan_*.json export exists yet."
        ))
    else:
        latest = scans[0]
        try:
            scan = json.loads(latest.read_text(encoding="utf-8"))
            items = scan.get("items")
            ok = isinstance(scan, dict) and isinstance(items, list) and len(items) > 0
            checks.append(_health_check(
                "latest_scan", "Latest scan export",
                "pass" if ok else "fail",
                f"{latest.name} is valid and contains {len(items)} build item(s)."
                if ok else f"{latest.name} is missing the expected items list."
            ))
        except Exception as exc:
            checks.append(_health_check(
                "latest_scan", "Latest scan export", "fail",
                f"Could not parse {latest.name}: {exc}"
            ))

    if not SCAN_HISTORY_FILE.exists():
        checks.append(_health_check(
            "scan_history", "Scan history", "pass",
            "No scan_history.json yet; it will be created after a successful scan."
        ))
    else:
        try:
            history = json.loads(SCAN_HISTORY_FILE.read_text(encoding="utf-8"))
            ok = isinstance(history, list)
            checks.append(_health_check(
                "scan_history", "Scan history",
                "pass" if ok else "fail",
                f"scan_history.json is valid with {len(history)} entr{'y' if len(history)==1 else 'ies'}."
                if ok else "scan_history.json exists but is not a list."
            ))
        except Exception as exc:
            checks.append(_health_check(
                "scan_history", "Scan history", "fail",
                f"Could not parse scan_history.json: {exc}"
            ))

    try:
        knowledge = load_knowledge_routes()
        routes = knowledge.get("routes", [])
        valid_sources = {"in-game-confirmed", "manual-needs-verification"}
        bad_sources = [
            r.get("id", "unknown")
            for r in routes
            if r.get("source_type") not in valid_sources
        ]
        checks.append(_health_check(
            "knowledge_routes",
            "In-game knowledge routes",
            "fail" if bad_sources else "pass",
            (
                f"Invalid source type on route(s): {', '.join(bad_sources)}"
                if bad_sources
                else f"user_knowledge/routes.json is valid with {len(routes)} supplemental route(s)."
            ),
        ))
    except Exception as exc:
        checks.append(_health_check(
            "knowledge_routes",
            "In-game knowledge routes",
            "fail",
            f"Could not read supplemental route data: {exc}",
        ))

    try:
        cache_count = len(list(CACHE_DIR.glob("*.json")))
        checks.append(_health_check(
            "cache", "Questlog cache", "pass",
            f"Cache directory is available with {cache_count} cached page file(s); freshness metadata is available."
        ))
    except Exception as exc:
        checks.append(_health_check(
            "cache", "Questlog cache", "fail",
            f"Could not inspect cache directory: {exc}"
        ))

    live_result_detail = "No live update has been applied yet."
    live_result_status = "pass"
    if LIVE_UPDATE_RESULT_FILE.exists():
        try:
            live_result = json.loads(LIVE_UPDATE_RESULT_FILE.read_text(encoding="utf-8"))
            if live_result.get("ok"):
                live_result_detail = f"Last live update completed successfully to v{live_result.get('version', '?')}."
            else:
                live_result_status = "warn"
                live_result_detail = f"Last live update reported an error: {live_result.get('error', 'unknown error')}"
        except Exception:
            live_result_status = "warn"
            live_result_detail = "Live-update result file exists but could not be parsed."
    checks.append(_health_check(
        "live_updater",
        "Live updater",
        live_result_status,
        live_result_detail,
    ))

    required_update_files = [
        "APPLY_UPDATE.bat", "START_APP.bat", "OPEN_APP.bat",
        "ROLLBACK_LAST_UPDATE.bat", "update_manager.py",
        "LAUNCH_PLANNER.ps1", "INSTALL_APP_SHORTCUT.bat",
        "REMOVE_APP_SHORTCUT.bat", "BUILD_LAUNCHER_EXE.bat",
        "assets/Questlog_TL_Farm_Planner.ico", "LIVE_UPDATE_HELPER.py"
    ]
    missing = [name for name in required_update_files if not (ROOT / name).exists()]
    checks.append(_health_check(
        "update_files", "Update & recovery files",
        "fail" if missing else "pass",
        f"Missing: {', '.join(missing)}"
        if missing else "Updater, launcher, opener, and rollback files are present."
    ))

    passed = sum(c["status"] == "pass" for c in checks)
    warned = sum(c["status"] == "warn" for c in checks)
    failed = sum(c["status"] == "fail" for c in checks)
    report = {
        "ok": failed == 0,
        "app_version": APP_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(checks),
            "passed": passed,
            "warned": warned,
            "failed": failed,
        },
        "checks": checks,
    }

    try:
        tmp = HEALTH_REPORT_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(HEALTH_REPORT_FILE)
    except Exception:
        LOGGER.exception("Could not save health report")

    return report


@app.get("/api/health")
def health():
    return {"ok": True, "app_version": APP_VERSION}


@app.get("/api/self-test")
def self_test():
    return run_backend_self_test()


@app.post("/api/cache/clear")
def clear_cache():
    count = CACHE.clear()
    return {"deleted": count}


def update_job(job_id, **kwargs):
    """Update a job while preserving partial progress fields.

    Scraper progress events are intentionally small. Merging them prevents a later
    message like {"message": "Opening ..."} from erasing current_item or stats.
    """
    with LOCK:
        job = JOBS[job_id]
        progress_update = kwargs.pop("progress", None)
        if progress_update is not None:
            merged = dict(job.get("progress") or {})
            # Preserve nested scanner statistics too.
            if "stats" in progress_update:
                stats = dict(merged.get("stats") or {})
                stats.update(progress_update.get("stats") or {})
                progress_update = dict(progress_update)
                progress_update["stats"] = stats
            merged.update(progress_update)
            job["progress"] = merged
        job.update(kwargs)


def run_scan(job_id: str, req: ScanRequest):
    try:
        def progress(**info):
            update_job(job_id, progress=info)

        def should_cancel():
            with LOCK:
                return bool(JOBS.get(job_id, {}).get("cancel_requested"))

        scraper = QuestlogScraper(CONFIG, CACHE, progress=progress, should_cancel=should_cancel)

        requested_mode = str(req.refresh_mode or "normal").strip().lower()
        if requested_mode not in {"normal", "stale", "force"}:
            requested_mode = "normal"

        force_refresh = bool(req.force_refresh or requested_mode == "force")
        stale_after_hours = None
        if requested_mode == "stale" and not force_refresh:
            stale_after_hours = max(
                1,
                min(
                    int(req.stale_after_hours or min(72, int(CONFIG["cache_ttl_hours"]))),
                    720,
                ),
            )

        result = scraper.scan(
            build_url=req.build_url,
            show_browser=req.show_browser,
            force_refresh=force_refresh,
            recursive_depth=max(0, min(req.recursive_depth, 4)),
            stale_after_hours=stale_after_hours,
        )

        previous, previous_filename = load_previous_scan_for_build(req.build_url)
        change_summary = summarize_scan_diff(previous, result)
        result["change_summary"] = change_summary

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_path = EXPORT_DIR / f"farm_scan_{stamp}_{job_id[:8]}.json"
        export_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        append_scan_history({
            "generated_at_utc": result.get("generated_at_utc"),
            "build_url": req.build_url,
            "filename": export_path.name,
            "previous_filename": previous_filename,
            "scan_mode": result.get("scan_mode", "normal"),
            "stale_after_hours": result.get("stale_after_hours"),
            "stats": dict(scraper.stats),
            "summary": change_summary,
        })

        LOGGER.info("Scan complete job=%s export=%s", job_id, export_path.name)
        update_job(
            job_id,
            status="done",
            result=result,
            export_file=export_path.name,
            finished_at=time.time(),
            progress={
                "message": "Scan complete.",
                "phase": "done",
                "current_item": None,
                "stats": dict(scraper.stats),
            },
        )
    except ScanCancelled:
        LOGGER.info("Scan cancelled job=%s", job_id)
        update_job(
            job_id,
            status="cancelled",
            finished_at=time.time(),
            error=None,
            progress={"message": "Scan cancelled.", "phase": "cancelled"},
        )
    except Exception as e:
        LOGGER.exception("Scan failed job=%s", job_id)
        update_job(
            job_id,
            status="error",
            finished_at=time.time(),
            error=str(e),
            progress={"message": f"Error: {e}", "phase": "error"},
        )


@app.post("/api/scan")
def scan(req: ScanRequest):
    job_id = uuid.uuid4().hex
    with LOCK:
        JOBS[job_id] = {
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "progress": {
                "message": "Starting scan...",
                "phase": "start",
                "current": 0,
                "total": 1,
                "current_item": None,
                "stats": {"pages_requested": 0, "pages_cache_hit": 0, "pages_downloaded": 0, "pages_stale_refreshed": 0},
            },
            "error": None,
            "result": None,
            "export_file": None,
            "cancel_requested": False,
        }

    t = threading.Thread(target=run_scan, args=(job_id, req), daemon=True)
    t.start()
    return {"job_id": job_id}



@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with LOCK:
        data = JOBS.get(job_id)
        if not data:
            raise HTTPException(404, "Unknown job.")
        if data.get("status") != "running":
            return {"ok": False, "status": data.get("status")}
        data["cancel_requested"] = True
        data["progress"] = {
            **(data.get("progress") or {}),
            "message": "Cancellation requested…",
            "phase": "cancelling",
        }
        return {"ok": True, "status": "cancelling"}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    with LOCK:
        data = JOBS.get(job_id)
        if not data:
            raise HTTPException(404, "Unknown job.")
        return data




@app.get("/api/latest-scan")
def latest_scan():
    """Load the most recent successful farm-scan export without scraping Questlog."""
    scans = sorted(
        EXPORT_DIR.glob("farm_scan_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in scans:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {
                "available": True,
                "filename": p.name,
                "modified_at": p.stat().st_mtime,
                "data": data,
            }
        except Exception:
            LOGGER.exception("Could not read prior scan export %s", p)
    return {"available": False, "filename": None, "modified_at": None, "data": None}


@app.post("/api/diagnostics/bundle")
def diagnostic_bundle(job_id: str | None = None):
    """Create a small support bundle the user can upload back into chat.

    Includes:
    - app/config metadata
    - recent app log
    - selected/current job status
    - latest scan JSON export when available
    - cache statistics (counts only, never the cached page bodies)
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_name = f"questlog_diagnostic_bundle_{stamp}.zip"
    bundle_path = EXPORT_DIR / bundle_name

    selected_job = None
    selected_job_id = None
    if job_id:
        with LOCK:
            selected_job = JOBS.get(job_id)
            selected_job_id = job_id

    if selected_job is None:
        with LOCK:
            # Prefer the most recent completed job, otherwise the most recent job of any state.
            items = list(JOBS.items())
            completed = [(jid, j) for jid, j in items if j.get("status") == "done"]
            if completed:
                selected_job_id, selected_job = completed[-1]
            elif items:
                selected_job_id, selected_job = items[-1]

    cache_files = list(CACHE_DIR.glob("*.json"))
    cache_stats = {
        "cache_file_count": len(cache_files),
        "cache_ttl_hours": CONFIG["cache_ttl_hours"],
    }

    support_meta = {
        "app_version": APP_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_job_id": selected_job_id,
        "selected_job_status": selected_job.get("status") if selected_job else None,
        "selected_export_file": selected_job.get("export_file") if selected_job else None,
    }

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("support_meta.json", json.dumps(support_meta, indent=2))
        z.writestr("config.json", json.dumps(CONFIG, indent=2))
        z.writestr("cache_stats.json", json.dumps(cache_stats, indent=2))

        if selected_job:
            safe_job = {
                "status": selected_job.get("status"),
                "progress": selected_job.get("progress"),
                "error": selected_job.get("error"),
                "export_file": selected_job.get("export_file"),
            }
            z.writestr("job_status.json", json.dumps(safe_job, indent=2, ensure_ascii=False))

            export_name = selected_job.get("export_file")
            if export_name:
                export_path = EXPORT_DIR / export_name
                if export_path.exists():
                    z.write(export_path, arcname=f"scan/{export_name}")

        if PLANNER_STATE_FILE.exists():
            z.write(PLANNER_STATE_FILE, arcname="planner/planner_state.json")
        if SCAN_HISTORY_FILE.exists():
            z.write(SCAN_HISTORY_FILE, arcname="planner/scan_history.json")
        if HEALTH_REPORT_FILE.exists():
            z.write(HEALTH_REPORT_FILE, arcname="planner/health_report.json")
        if KNOWLEDGE_ROUTES_FILE.exists():
            z.write(KNOWLEDGE_ROUTES_FILE, arcname="planner/user_knowledge/routes.json")
        if FRONTEND_LOG_FILE.exists():
            z.write(FRONTEND_LOG_FILE, arcname="logs/frontend_errors.log")
        if LIVE_UPDATE_DOWNLOAD_FILE.exists():
            z.write(LIVE_UPDATE_DOWNLOAD_FILE, arcname="updates/live_update_download.json")
        if LIVE_UPDATE_RESULT_FILE.exists():
            z.write(LIVE_UPDATE_RESULT_FILE, arcname="updates/live_update_result.json")
        if LIVE_UPDATE_RESTART_LOG_FILE.exists():
            z.write(LIVE_UPDATE_RESTART_LOG_FILE, arcname="updates/live_update_restart.log")
        if LOG_FILE.exists():
            z.write(LOG_FILE, arcname="logs/app.log")

    LOGGER.info("Diagnostic bundle created %s", bundle_name)
    return {"filename": bundle_name}


@app.get("/api/exports/{filename}")
def export(filename: str):
    p = (EXPORT_DIR / filename).resolve()
    if EXPORT_DIR.resolve() not in p.parents or not p.exists():
        raise HTTPException(404, "Export not found.")
    return FileResponse(p, filename=filename, media_type="application/json")
