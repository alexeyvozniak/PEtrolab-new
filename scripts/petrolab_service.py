"""PyInstaller entry point for the local PetroLab scientific service."""

from __future__ import annotations

import sys
from pathlib import Path

import petrolab.import_apply as import_apply


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    import_apply.MIGRATIONS = Path(sys._MEIPASS) / "migrations"

from petrolab.ndjson_service import serve  # noqa: E402


def _force_utf8_stdio() -> None:
    """Keep the desktop NDJSON protocol independent from Windows code pages."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="strict")
            except (OSError, ValueError):
                # The Tauri launcher also sets PYTHONUTF8/PYTHONIOENCODING.
                # Reconfigure is extra hardening for frozen PyInstaller builds.
                pass


if __name__ == "__main__":
    _force_utf8_stdio()
    serve()
