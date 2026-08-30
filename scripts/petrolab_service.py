"""PyInstaller entry point for the local PetroLab scientific service."""

from __future__ import annotations

import sys
from pathlib import Path

import petrolab.import_apply as import_apply


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    import_apply.MIGRATIONS = Path(sys._MEIPASS) / "migrations"

from petrolab.ndjson_service import serve  # noqa: E402


if __name__ == "__main__":
    serve()
