"""Read-only machine audit; no downloads, inference, or global installs."""
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def command(args):
    try:
        p = subprocess.run(args, capture_output=True, timeout=30)
        raw = p.stdout + p.stderr
        encoding = "utf-16-le" if b"\x00" in raw else "utf-8"
        return {"exit_code": p.returncode, "output": raw.decode(encoding, errors="replace").strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def audit():
    blender = os.environ.get("AFS_BLENDER") or shutil.which("blender")
    if not blender:
        candidates = list((Path.home() / "Tools").glob("blender*/blender.exe"))
        blender = str(sorted(candidates)[-1]) if candidates else None
    disk = shutil.disk_usage(ROOT)
    return {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(), "python": sys.version, "python_executable": sys.executable,
        "ram_bytes": psutil.virtual_memory().total,
        "disk_free_bytes": disk.free,
        "gpu": command(["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"]),
        "wsl": command(["wsl", "--list", "--verbose"]) if os.name == "nt" else {"status": "not_windows"},
        "blender_path": blender,
        "blender": command([blender, "--version"]) if blender else {"status": "NOT_FOUND"},
        "unity_editors": [str(x) for x in Path("C:/Program Files/Unity/Hub/Editor").glob("*/Editor/Unity.exe")],
        "trellis2_existing": str(Path.home() / "Tools/trellis2/code") if (Path.home() / "Tools/trellis2/code").exists() else None,
        "inference_test": "NOT_TESTED",
    }


if __name__ == "__main__":
    result = audit()
    target = ROOT / "docs/evidence/environment.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
