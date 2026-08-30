"""Package the local scientific service for a Tauri Windows bundle."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "desktop" / "src-tauri" / "binaries"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "petrolab-service",
            "--paths",
            str(ROOT / "src"),
            "--add-data",
            f"{ROOT / 'migrations'}{os.pathsep}migrations",
            "--distpath",
            str(OUTPUT),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
            "--specpath",
            str(ROOT / "build" / "pyinstaller"),
            str(ROOT / "scripts" / "petrolab_service.py"),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
