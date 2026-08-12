from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "_update_payload"
BACKUPS = ROOT / "data" / "update_backups"
STATE = ROOT / "data" / "update_state.json"


def copy_tree_with_backup():
    if not PAYLOAD.exists():
        print("No _update_payload folder found.")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUPS / stamp
    changed = []

    for src in PAYLOAD.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(PAYLOAD)
        dst = ROOT / rel
        changed.append(str(rel))

        if dst.exists():
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, b)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    STATE.parent.mkdir(parents=True, exist_ok=True)
    added = [rel for rel in changed if not (backup / rel).exists()]
    STATE.write_text(json.dumps({
        "last_backup": str(backup),
        "changed_files": changed,
        "backed_up_files": [rel for rel in changed if (backup / rel).exists()],
        "added_files": added,
        "updated_at": stamp,
        "source": "manual-update"
    }, indent=2), encoding="utf-8")

    shutil.rmtree(PAYLOAD, ignore_errors=True)
    print(f"Update applied. Backup: {backup}")
    print("Your .venv, cache, exports, and other data were preserved.")
    return 0


def rollback():
    if not STATE.exists():
        print("No update state found.")
        return 1
    state = json.loads(STATE.read_text(encoding="utf-8"))
    backup = Path(state["last_backup"])
    if not backup.exists():
        print("Backup folder is missing:", backup)
        return 1

    restored = 0
    for src in backup.rglob("*"):
        if src.is_file():
            rel = src.relative_to(backup)
            dst = ROOT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            restored += 1

    removed = 0
    for rel in state.get("added_files", []) or []:
        dst = ROOT / rel
        try:
            if dst.is_file():
                dst.unlink()
                removed += 1
        except Exception:
            pass

    print(f"Rollback restored {restored} files from {backup} and removed {removed} files introduced by the update.")
    return 0


if __name__ == "__main__":
    mode = (sys.argv[1] if len(sys.argv) > 1 else "apply").lower()
    raise SystemExit(rollback() if mode == "rollback" else copy_tree_with_backup())
