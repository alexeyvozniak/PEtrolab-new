from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    corpus_dir = os.environ.get("PETROLAB_REAL_IMPORT_CORPUS_DIR")
    if not corpus_dir:
        raise SystemExit("PETROLAB_REAL_IMPORT_CORPUS_DIR is required for milestone QA")

    run([sys.executable, "scripts/validate_contracts.py"])
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    run([
        sys.executable,
        "scripts/validate_real_import_corpus.py",
        "--require-all",
        "--corpus-dir",
        corpus_dir,
    ])
    print("Core + normative real-workbook milestone gates passed.")
    print("Desktop WebDriver and installer gates are executed by their Windows workflows.")


if __name__ == "__main__":
    main()
