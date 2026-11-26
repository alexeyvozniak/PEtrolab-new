"""Portable project archives with verified, isolated restore."""

from contextlib import closing, nullcontext
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
from stat import FILE_ATTRIBUTE_REPARSE_POINT
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from .import_apply import _source_path_for_revision, open_project
from .import_preview import ImportCommandError
from .media_display import _publish_new_file


_LEVELS = {"project", "project_sources", "full"}
_DB = "project.sqlite"
_MANIFEST = "manifest.json"
_FILE_PATH = re.compile(r"(?:sources|media)/[0-9a-f-]{36}\.[A-Za-z0-9]{1,12}", re.ASCII)
_SIZE_LIMIT = 20 * 1024 ** 3
_CHUNK = 1024 * 1024


def _archive_error(message, code="PROJECT_ARCHIVE_INVALID"):
    raise ImportCommandError(code, message)


def _portable_asset_path(directory, identifier, source):
    extension = source.suffix.lower()
    name = f"{directory}/{identifier}{extension}"
    if not _FILE_PATH.fullmatch(name):
        _archive_error("Формат имени исходного файла не поддерживается для переноса.")
    return name


def _copy_and_hash(source, destination=None):
    fingerprint = sha256()
    size = 0
    while block := source.read(_CHUNK):
        if destination is not None:
            destination.write(block)
        fingerprint.update(block)
        size += len(block)
    return fingerprint.hexdigest(), size


def _record_file(archive, path, relative, expected=None):
    if not path.is_file():
        _archive_error(f"Файл недоступен: {path.name}.", "PROJECT_ARCHIVE_SOURCE_UNAVAILABLE")
    with path.open("rb") as source, archive.open(relative, "w", force_zip64=True) as output:
        fingerprint, size = _copy_and_hash(source, output)
    if expected is not None and fingerprint != expected:
        _archive_error(f"Файл изменился: {path.name}.", "PROJECT_ARCHIVE_SOURCE_CHANGED")
    return {"path": relative, "sha256": fingerprint, "size": size}


def _managed_path(database_path, relative, directory):
    root = (database_path.parent / directory).resolve()
    source = (database_path.parent / relative).resolve()
    if root not in source.parents:
        _archive_error("Файл в проекте находится за пределами ожидаемого каталога.")
    return source


def _bundle_inputs(connection, database_path, archive, level):
    entries = []
    if level in {"project_sources", "full"}:
        for row in connection.execute("SELECT * FROM source_file ORDER BY source_id").fetchall():
            identifier = row["source_id"]
            source = _source_path_for_revision(database_path, row)
            if row["source_kind"] == "managed_copy":
                source = _managed_path(database_path, row["managed_relative_path"], "sources")
            relative = _portable_asset_path("sources", identifier, source)
            entries.append(_record_file(archive, source, relative, row["source_fingerprint_sha256"]))
            connection.execute("""
                UPDATE source_file SET source_kind = 'managed_copy', linked_path = NULL, managed_relative_path = ?, state = 'current'
                WHERE source_id = ?
            """, (relative, identifier))
    if level == "full":
        for row in connection.execute("SELECT * FROM media_asset ORDER BY media_asset_id").fetchall():
            identifier = row["media_asset_id"]
            source = (_managed_path(database_path, row["managed_relative_path"], "media")
                      if row["source_kind"] == "managed_copy" else Path(row["linked_path"]))
            relative = _portable_asset_path("media", identifier, source)
            entries.append(_record_file(archive, source, relative, row["source_fingerprint_sha256"]))
            connection.execute("""
                UPDATE media_asset SET source_kind = 'managed_copy', linked_path = NULL, managed_relative_path = ?
                WHERE media_asset_id = ?
            """, (relative, identifier))
    return entries


def export_project_archive(database_path, output_path, level):
    if (not isinstance(output_path, str) or not output_path or Path(output_path).suffix.lower() != ".petrolab"
            or not isinstance(level, str) or level not in _LEVELS):
        raise ValueError("project_archive")
    database_path, destination = Path(database_path), Path(output_path)
    if not database_path.is_file():
        _archive_error("База проекта не найдена.", "PROJECT_ARCHIVE_SOURCE_UNAVAILABLE")
    temporary = None
    try:
        with TemporaryDirectory(dir=destination.parent, prefix="petrolab-archive-") as staging:
            snapshot = Path(staging) / _DB
            source_uri = database_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(source_uri, uri=True)) as original, closing(sqlite3.connect(snapshot)) as copy:
                original.backup(copy)
            with closing(open_project(snapshot)):
                pass
            with NamedTemporaryFile(dir=destination.parent, suffix=".petrolab.tmp", delete=False) as stream:
                temporary = Path(stream.name)
            with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
                with closing(sqlite3.connect(snapshot)) as copied, copied:
                    copied.row_factory = sqlite3.Row
                    entries = _bundle_inputs(copied, database_path, archive, level)
                    project = copied.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()[0]
                    schema = copied.execute("SELECT project_schema_version FROM project_meta WHERE singleton = 1").fetchone()[0]
                entries.insert(0, _record_file(archive, snapshot, _DB))
                if sum(entry["size"] for entry in entries) > _SIZE_LIMIT:
                    _archive_error("Архив превышает предел 20 ГиБ.", "PROJECT_ARCHIVE_TOO_LARGE")
                manifest = {"schema_version": 1, "project_id": project, "project_schema_version": schema,
                            "level": level, "files": entries}
                archive.writestr(_MANIFEST, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
            _publish_new_file(temporary, destination)
    except FileExistsError as error:
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Архив уже существует. Выберите новое имя.") from error
    except (OSError, sqlite3.Error) as error:
        raise ImportCommandError("PROJECT_ARCHIVE_FAILED", "Не удалось сохранить переносимую копию проекта.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(destination), "manifest": manifest}


def _archive_manifest(archive):
    records = {item.filename: item for item in archive.infolist()}
    if len(records) != len(archive.infolist()) or _MANIFEST not in records or records[_MANIFEST].file_size > 12 * 1024 ** 2:
        _archive_error("Архив содержит дублирующиеся записи или недоступный manifest.")
    try:
        manifest = json.loads(archive.read(_MANIFEST))
    except (UnicodeDecodeError, ValueError):
        _archive_error("Manifest архива повреждён.")
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "project_id", "project_schema_version", "level", "files"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or not isinstance(manifest["level"], str) or manifest["level"] not in _LEVELS or not isinstance(manifest["files"], list)):
        _archive_error("Версия или структура архива не поддерживается.")
    members = set()
    total = 0
    for entry in manifest["files"]:
        if (not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}
                or not isinstance(entry["path"], str) or not isinstance(entry["sha256"], str)
                or type(entry["size"]) is not int or entry["size"] < 0):
            _archive_error("Manifest содержит недопустимое описание файла.")
        path = entry["path"]
        expected_level = "full" if path.startswith("media/") else "project_sources"
        if (path in members or path not in records or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                or (path != _DB and (not _FILE_PATH.fullmatch(path)
                                    or (manifest["level"] != "full" and manifest["level"] != expected_level)))
                or records[path].file_size != entry["size"] or records[path].is_dir()
                or (records[path].external_attr >> 16) & 0o170000 == 0o120000):
            _archive_error("Запись архива не соответствует manifest или использует недопустимый путь.")
        members.add(path)
        total += entry["size"]
    if _DB not in members or set(records) != members | {_MANIFEST} or total > _SIZE_LIMIT:
        _archive_error("Архив содержит неподтверждённые файлы или превышает допустимый объём.")
    return manifest, total


def _verify_database(database, manifest):
    try:
        with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as connection:
            connection.execute("PRAGMA trusted_schema = OFF")
            if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or connection.execute("PRAGMA foreign_key_check").fetchone():
                _archive_error("Проверка целостности SQLite не пройдена.")
            project = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()
            version = connection.execute("SELECT project_schema_version FROM project_meta WHERE singleton = 1").fetchone()
            if project != (manifest["project_id"],) or version != (manifest["project_schema_version"],):
                _archive_error("Идентификатор или версия SQLite не совпадают с manifest.")
            expected = {}
            tables = []
            if manifest["level"] in {"project_sources", "full"}:
                tables.append(("source_file", "sources"))
            if manifest["level"] == "full":
                tables.append(("media_asset", "media"))
            for table, directory in tables:
                for kind, path, fingerprint in connection.execute(
                    f"SELECT source_kind, managed_relative_path, source_fingerprint_sha256 FROM {table}"
                ):
                    if (kind != "managed_copy" or not isinstance(path, str) or not path.startswith(directory + "/")
                            or not _FILE_PATH.fullmatch(path) or path in expected):
                        _archive_error("Ссылки на включённые файлы в базе не соответствуют формату переноса.")
                    expected[path] = fingerprint
            included = {entry["path"]: entry["sha256"] for entry in manifest["files"] if entry["path"] != _DB}
            if expected != included:
                _archive_error("Список включённых файлов не совпадает со ссылками в базе.")
        with closing(open_project(database)):
            pass
    except sqlite3.Error as error:
        raise ImportCommandError("PROJECT_ARCHIVE_INVALID", "База SQLite в архиве повреждена.") from error


def _unpack_verified(archive, manifest, directory, *, include_assets):
    for entry in manifest["files"]:
        target = nullcontext()
        if include_assets or entry["path"] == _DB:
            path = directory.joinpath(*PurePosixPath(entry["path"]).parts)
            path.parent.mkdir(exist_ok=True, parents=True)
            target = path.open("xb")
        with target as output, archive.open(entry["path"]) as source:
            fingerprint, size = _copy_and_hash(source, output)
        if fingerprint != entry["sha256"] or size != entry["size"]:
            _archive_error("Контрольная сумма одного из файлов не совпадает.")
    _verify_database(directory / _DB, manifest)


def inspect_project_archive(archive_path):
    """Verify every member using a temporary database, without restoring a project."""
    if not isinstance(archive_path, str) or not archive_path:
        raise ValueError("project_archive_inspect")
    try:
        with ZipFile(archive_path) as archive:
            manifest, size = _archive_manifest(archive)
            with TemporaryDirectory(prefix="petrolab-archive-check-") as scratch:
                _unpack_verified(archive, manifest, Path(scratch), include_assets=False)
    except (BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ImportCommandError("PROJECT_ARCHIVE_INVALID", "Архив повреждён или использует неподдерживаемое сжатие.") from error
    except OSError as error:
        raise ImportCommandError("PROJECT_ARCHIVE_FAILED", "Не удалось проверить переносимый архив.") from error
    return {"manifest": manifest, "unpacked_size": size}


def restore_project_archive(archive_path, destination_path):
    if not isinstance(archive_path, str) or not isinstance(destination_path, str) or not archive_path or not destination_path:
        raise ValueError("project_archive_restore")
    destination = Path(destination_path).absolute()
    if destination.exists() or destination.is_symlink():
        _archive_error("Выберите новый каталог. Существующий проект не изменён.", "PROJECT_ARCHIVE_DESTINATION_EXISTS")
    try:
        with ZipFile(archive_path) as archive:
            manifest, size = _archive_manifest(archive)
            if shutil.disk_usage(destination.parent).free < size:
                _archive_error("Недостаточно места для восстановления.", "PROJECT_ARCHIVE_NO_SPACE")
            with TemporaryDirectory(dir=destination.parent, prefix="petrolab-restore-") as scratch:
                extracted = Path(scratch) / "restored"
                extracted.mkdir()
                _unpack_verified(archive, manifest, extracted, include_assets=True)
                if destination.exists() or destination.is_symlink():
                    _archive_error("Каталог назначения уже существует.", "PROJECT_ARCHIVE_DESTINATION_EXISTS")
                extracted.rename(destination)
    except (BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ImportCommandError("PROJECT_ARCHIVE_INVALID", "Архив повреждён или использует неподдерживаемое сжатие.") from error
    except OSError as error:
        raise ImportCommandError("PROJECT_ARCHIVE_FAILED", "Не удалось восстановить проект в новый каталог.") from error
    return {"project_database_path": str(destination / _DB), "manifest": manifest}


def replace_project_from_archive(archive_path, destination_path):
    """Replace an offline portable workspace and retain the entire original directory."""
    destination = Path(destination_path).absolute()
    if (not destination.is_dir() or destination.is_symlink()
            or getattr(destination.lstat(), "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT):
        _archive_error("Для замены выберите отдельный каталог PetroLab с файлом project.sqlite.",
                       "PROJECT_ARCHIVE_REPLACE_TARGET")
    destination = destination.resolve()
    original_database = destination / _DB
    if not original_database.is_file() or original_database.is_symlink():
        _archive_error("Для замены выберите отдельный каталог PetroLab с файлом project.sqlite.",
                       "PROJECT_ARCHIVE_REPLACE_TARGET")
    if Path(archive_path).resolve().is_relative_to(destination.resolve()):
        _archive_error("Перед заменой переместите архив в другой каталог.", "PROJECT_ARCHIVE_REPLACE_TARGET")

    def verify_target():
        if any(original_database.with_name(_DB + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            _archive_error("Закройте проект PetroLab и завершите операции с базой перед заменой.",
                           "PROJECT_ARCHIVE_PROJECT_IN_USE")
        try:
            uri = original_database.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=0)) as connection:
                row = connection.execute("SELECT project_id FROM project_identity WHERE singleton = 1").fetchone()
                if row is None:
                    _archive_error("В каталоге отсутствует идентификатор проекта PetroLab.", "PROJECT_ARCHIVE_REPLACE_TARGET")
                return original_database.stat()
        except (OSError, sqlite3.Error) as error:
            raise ImportCommandError("PROJECT_ARCHIVE_REPLACE_TARGET", "Не удалось проверить существующий проект PetroLab.") from error

    original = verify_target()
    backup = destination.with_name(f"{destination.name}.backup-{uuid4().hex}")
    try:
        with TemporaryDirectory(dir=destination.parent, prefix="petrolab-replacement-") as scratch:
            candidate = Path(scratch) / "verified"
            restored = restore_project_archive(archive_path, str(candidate))
            current = verify_target()
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (
                    original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns):
                _archive_error("Проект изменился во время проверки архива. Замена отменена.", "PROJECT_ARCHIVE_PROJECT_IN_USE")
            destination.rename(backup)
            try:
                candidate.rename(destination)
            except OSError:
                try:
                    if not destination.exists() and not destination.is_symlink():
                        backup.rename(destination)
                except OSError as rollback_error:
                    raise ImportCommandError("PROJECT_ARCHIVE_ROLLBACK_FAILED",
                                             "Не удалось вернуть проект. Исходный каталог сохранён в резервной копии.",
                                             {"backup_path": str(backup)}) from rollback_error
                if backup.exists():
                    raise ImportCommandError("PROJECT_ARCHIVE_ROLLBACK_FAILED",
                                             "Путь назначения занят. Исходный каталог сохранён в резервной копии.",
                                             {"backup_path": str(backup)})
                raise
    except OSError as error:
        raise ImportCommandError("PROJECT_ARCHIVE_FAILED", "Не удалось заменить проект из архива.") from error
    return {**restored, "project_database_path": str(original_database), "backup_path": str(backup)}
