from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath


def safe_members(zf: zipfile.ZipFile):
    files = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        p = PurePosixPath(name)
        if info.is_dir():
            continue
        if p.is_absolute() or ".." in p.parts:
            raise RuntimeError(f"Unsafe ZIP path: {name}")
        files.append((info, p))
    return files


def wait_for_pid(pid: int, timeout: float = 20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if str(pid) not in result.stdout:
                    return
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                return
        time.sleep(0.25)


def destination_for(root: Path, path: PurePosixPath):
    parts = list(path.parts)
    if not parts:
        return None

    if parts[0] == "_update_payload":
        if len(parts) == 1:
            return None
        return root.joinpath(*parts[1:])

    # Root-level files are updater/launcher infrastructure.
    # UPDATE_README is informational and need not live in the installation.
    if len(parts) == 1 and parts[0] != "UPDATE_README.txt":
        return root / parts[0]

    return None


def _restart_log(root: Path, message: str):
    try:
        log = root / "data" / "live_update_restart.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except Exception:
        pass


def _server_ready(timeout_seconds: float = 15.0):
    import urllib.request

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            request = urllib.request.Request(
                "http://127.0.0.1:8765/api/health",
                headers={"User-Agent": "Questlog-TL-Farm-Planner-Live-Updater"},
            )
            with urllib.request.urlopen(request, timeout=1.0) as response:
                if 200 <= int(response.status) < 300:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def restart(root: Path):
    python_exe = root / ".venv" / "Scripts" / "python.exe"
    launcher = root / "launcher.py"
    starter = root / "START_APP.bat"

    _restart_log(root, "Restart requested after live update.")

    if os.name == "nt" and python_exe.exists() and launcher.exists():
        try:
            flags = (
                getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
            subprocess.Popen(
                [str(python_exe), str(launcher)],
                cwd=str(root),
                creationflags=flags,
                close_fds=False,
            )
            _restart_log(root, "Started launcher.py directly with venv Python.")

            if _server_ready(12.0):
                _restart_log(root, "Server readiness check passed after direct restart.")
                return

            _restart_log(root, "Direct restart did not become ready; trying START_APP.bat fallback.")
        except Exception as exc:
            _restart_log(root, f"Direct restart failed: {exc}")

    if not starter.exists():
        raise RuntimeError("START_APP.bat is missing after update.")

    if os.name == "nt":
        # Use an explicit quoted /c command string so paths with spaces are safe.
        command = f'call "{starter}"'
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            ["cmd.exe", "/d", "/s", "/c", command],
            cwd=str(root),
            creationflags=flags,
            close_fds=False,
        )
        _restart_log(root, "START_APP.bat fallback launched.")
    else:
        subprocess.Popen(
            ["bash", str(starter)],
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if _server_ready(15.0):
        _restart_log(root, "Server readiness check passed after fallback restart.")
        return

    _restart_log(root, "Server readiness check FAILED after all restart attempts.")
    raise RuntimeError("Planner files updated, but the local server did not restart successfully.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--zip", required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    zip_path = Path(args.zip).resolve()
    data = root / "data"
    backups = data / "update_backups"
    result_file = data / "live_update_result.json"
    state_file = data / "update_state.json"

    result_file.parent.mkdir(parents=True, exist_ok=True)
    wait_for_pid(args.pid)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backups / stamp
    copied = []
    added = []
    backed_up = []

    try:
        if not zip_path.exists():
            raise RuntimeError(f"Downloaded update ZIP is missing: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            members = safe_members(zf)

            mapped = []
            for info, path in members:
                dst = destination_for(root, path)
                if dst is not None:
                    mapped.append((info, path, dst))

            payload_count = sum(1 for _, path, _ in mapped if path.parts[0] == "_update_payload")
            if payload_count < 1:
                raise RuntimeError("Update package contains no _update_payload files.")

            # Back up every file the live updater will replace, including root-level
            # updater infrastructure. This is stronger than the old manual workflow.
            for _, path, dst in mapped:
                rel = dst.relative_to(root)
                if dst.exists():
                    b = backup / rel
                    b.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, b)
                    backed_up.append(str(rel))
                else:
                    added.append(str(rel))

            for info, path, dst in mapped:
                dst.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, dst.open("wb") as out:
                    shutil.copyfileobj(src, out)
                try:
                    date_time = info.date_time
                    # ZIP timestamps are local/no timezone; preserving them is optional.
                    _ = date_time
                except Exception:
                    pass
                copied.append(str(dst.relative_to(root)))

        state_file.write_text(
            json.dumps(
                {
                    "last_backup": str(backup),
                    "changed_files": copied,
                    "backed_up_files": backed_up,
                    "added_files": added,
                    "updated_at": stamp,
                    "source": "live-update",
                    "version": args.version,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result_file.write_text(
            json.dumps(
                {
                    "ok": True,
                    "version": args.version,
                    "updated_at": stamp,
                    "backup": str(backup),
                    "changed_files": copied,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    except Exception as exc:
        # Restore files already backed up and remove files newly introduced by
        # the failed update. Then bring the old server back.
        try:
            if backup.exists():
                for src in backup.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(backup)
                        dst = root / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
            for rel in added:
                p = root / rel
                try:
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        result_file.write_text(
            json.dumps(
                {
                    "ok": False,
                    "version": args.version,
                    "updated_at": stamp,
                    "error": str(exc),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        if not args.no_restart:
            try:
                restart(root)
            except Exception:
                pass
        return 1

    if not args.no_restart:
        restart(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
