from __future__ import annotations

import re
import subprocess
from pathlib import Path

try:
    from .build_web_database import _write_generated_modules
except ImportError:
    from build_web_database import _write_generated_modules


WORKER_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = WORKER_ROOT.parent / "quest_viewer" / "VERSION"
SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump_patch(version: str) -> str:
    match = SEMVER_PATTERN.fullmatch(version)
    if not match:
        raise ValueError(f"无效的网站版本号：{version!r}")
    major, minor, patch = map(int, match.groups())
    return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    previous_version = VERSION_FILE.read_text(encoding="utf-8").strip()
    next_version = bump_patch(previous_version)
    VERSION_FILE.write_text(next_version + "\n", encoding="utf-8")
    try:
        _write_generated_modules()
        subprocess.run(
            ["uv", "run", "pywrangler", "deploy"],
            cwd=WORKER_ROOT,
            check=True,
        )
    except BaseException:
        VERSION_FILE.write_text(previous_version + "\n", encoding="utf-8")
        _write_generated_modules()
        raise
    print(f"Cloudflare 已同步：v{previous_version} → v{next_version}")


if __name__ == "__main__":
    main()
