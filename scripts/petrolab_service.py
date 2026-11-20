"""PyInstaller entry point for the local PetroLab scientific service."""

from __future__ import annotations

import sys
import argparse
import json
from pathlib import Path

import petrolab.import_apply as import_apply


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    import_apply.MIGRATIONS = Path(sys._MEIPASS) / "migrations"

from petrolab.ndjson_service import serve  # noqa: E402
from petrolab.import_preview import ImportCommandError  # noqa: E402
from petrolab.project_archive import export_project_archive, restore_project_archive  # noqa: E402


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


def main() -> int:
    _force_utf8_stdio()
    if len(sys.argv) == 1:
        serve()
        return 0

    parser = argparse.ArgumentParser(description="PetroLab Desktop")
    commands = parser.add_subparsers(dest="command", required=True)
    archive = commands.add_parser("archive", help="Перенос проекта")
    actions = archive.add_subparsers(dest="action", required=True)
    export = actions.add_parser("export", help="Создать переносимый архив")
    export.add_argument("database", type=Path, help="Существующая база SQLite PetroLab")
    export.add_argument("output", type=Path, help="Новый файл .petrolab")
    export.add_argument("--level", choices=("project", "project_sources", "full"), required=True)
    restore = actions.add_parser("restore", help="Восстановить в новый каталог")
    restore.add_argument("archive", type=Path)
    restore.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "export":
            if not args.database.is_file():
                parser.error("Указанная база проекта не найдена.")
            result = export_project_archive(str(args.database), str(args.output), args.level)
        else:
            result = restore_project_archive(str(args.archive), str(args.destination))
    except ImportCommandError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    except ValueError:
        parser.error("Проверьте пути, расширение архива и уровень переноса.")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
