"""XLSX export of a snapshot of explicitly selected project analyses."""

from contextlib import closing
import csv
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.writer.excel import ExcelWriter

from .import_preview import ImportCommandError


def _append_projection(workbook, name, cursor):
    sheet = workbook.create_sheet(name)
    sheet.append([column[0] for column in cursor.description])
    sheet.freeze_panes = "A2"
    for row_number, row in enumerate(cursor, start=2):
        if row_number > 1_048_576:
            raise ImportCommandError("EXPORT_XLSX_LIMIT", f"Превышен предел строк XLSX на листе {name}.")
        for column_number, value in enumerate(row, start=1):
            if isinstance(value, str):
                if len(value.encode("utf-16-le")) > 65_534 or ILLEGAL_CHARACTERS_RE.search(value):
                    raise ImportCommandError("EXPORT_XLSX_LIMIT", f"Значение на листе {name} нельзя записать в XLSX без потерь.")
                cell = sheet.cell(row_number, column_number, value)
                cell.data_type = "s"
            elif value is not None:
                sheet.cell(row_number, column_number, value)
    sheet.auto_filter.ref = sheet.dimensions


def _selection_workbook(database_path, analysis_ids):
    if (not isinstance(analysis_ids, list) or not analysis_ids
            or not all(isinstance(item, str) and str(UUID(item)) == item for item in analysis_ids)
            or len(set(analysis_ids)) != len(analysis_ids)):
        raise ValueError("analysis_ids")
    parameters = (json.dumps(analysis_ids),)
    selected = "WITH selected AS (SELECT key AS position, value AS analysis_id FROM json_each(?))"
    workbook = Workbook()
    workbook.remove(workbook.active)
    try:
        uri = Path(database_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("BEGIN")
            unavailable = connection.execute(selected + """
                SELECT COUNT(*) FROM selected
                LEFT JOIN analysis a ON a.analysis_id = selected.analysis_id
                LEFT JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                LEFT JOIN import_batch_retraction r ON r.import_batch_id = a.import_batch_id
                WHERE a.analysis_id IS NULL OR b.status != 'applied' OR r.import_batch_id IS NOT NULL
            """, parameters).fetchone()[0]
            if unavailable:
                raise ImportCommandError("EXPORT_ANALYSES_UNAVAILABLE", "Часть выбранных анализов недоступна. Экспорт отменён.",
                                         {"unavailable_count": unavailable})

            _append_projection(workbook, "Analyses", connection.execute(selected + """
                SELECT a.analysis_id, a.identity_json, a.source_id, s.display_name AS source_name,
                       b.source_fingerprint_sha256 AS source_sha256, a.import_batch_id, b.recipe_revision_id,
                       r.semantic_fingerprint_sha256 AS recipe_sha256, a.sheet_name, a.source_row_number,
                       a.source_column_number, a.source_orientation, a.block_id, b.applied_at,
                       evidence.sample_association_json, evidence.analytical_method_json
                FROM selected
                JOIN analysis a USING (analysis_id)
                JOIN source_file s ON s.source_id = a.source_id
                JOIN import_batch b ON b.import_batch_id = a.import_batch_id
                JOIN import_recipe_revision r ON r.recipe_revision_id = b.recipe_revision_id
                LEFT JOIN analysis_import_semantics evidence ON evidence.analysis_id = a.analysis_id
                ORDER BY selected.position
            """, parameters))
            _append_projection(workbook, "Measurements", connection.execute(selected + """
                SELECT m.analysis_id, m.measurement_id, m.canonical_field, m.raw_token, m.unit,
                       m.value_status, m.qualifier, m.detection_limit, m.source_column_name AS source_header,
                       m.source_row_number, m.physical_source_column_index, m.source_cell,
                       m.measurement_set, m.method, m.reported_fe_form, m.fe_handling
                FROM selected JOIN measurement m USING (analysis_id)
                ORDER BY selected.position, m.source_column_index, m.rowid
            """, parameters))
            _append_projection(workbook, "Source metadata", connection.execute(selected + """
                SELECT m.analysis_id, m.canonical_field, m.raw_token, m.source_header, m.source_row_number,
                       m.source_column_index, m.source_cell
                FROM selected JOIN analysis_source_metadata m USING (analysis_id)
                ORDER BY selected.position, m.source_column_index, m.rowid
            """, parameters))

    except BaseException:
        workbook.close()
        raise
    return workbook


def selection_xlsx_bytes(database_path, analysis_ids):
    """Serialize identical selected data to identical workbook bytes across runs."""
    with closing(_selection_workbook(database_path, analysis_ids)) as workbook:
        epoch = datetime(1980, 1, 1, tzinfo=timezone.utc)
        workbook.properties.created = workbook.properties.modified = epoch
        source = BytesIO()
        ExcelWriter(workbook, ZipFile(source, "w", compression=ZIP_DEFLATED)).save()
        result = BytesIO()
        with ZipFile(source) as original, ZipFile(result, "w") as stable:
            for name in original.namelist():
                member = ZipInfo(name)
                member.compress_type = ZIP_DEFLATED
                stable.writestr(member, original.read(name))
        return result.getvalue()


def _write_selection_csv(workbook, path):
    analyses = iter(workbook["Analyses"].values)
    analysis_header = next(analyses)
    measurements = iter(workbook["Measurements"].values)
    measurement_header = next(measurements)
    current = next(measurements, None)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow((*analysis_header, *(f"measurement_{name}" if name in analysis_header else name
                                              for name in measurement_header[1:])))
        for analysis in analyses:
            if current is None or current[0] != analysis[0]:
                writer.writerow((*analysis, *([None] * (len(measurement_header) - 1))))
                continue
            while current is not None and current[0] == analysis[0]:
                writer.writerow((*analysis, *current[1:]))
                current = next(measurements, None)


def _export_selection(database_path, analysis_ids, output_path, format_name):
    if not isinstance(output_path, str) or not output_path.strip() or Path(output_path).suffix.lower() != f".{format_name}":
        raise ValueError("output_path")
    destination = Path(output_path).resolve()
    if destination.exists():
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Файл уже существует. Выберите новое имя для экспорта.")
    temporary = None
    try:
        with closing(_selection_workbook(database_path, analysis_ids)) as workbook:
            with NamedTemporaryFile(dir=destination.parent, suffix=f".{format_name}.tmp", delete=False) as stream:
                temporary = Path(stream.name)
            if format_name == "csv":
                _write_selection_csv(workbook, temporary)
            else:
                workbook.save(temporary)
        if os.name == "nt":
            temporary.rename(destination)
        else:
            os.link(temporary, destination)
    except FileExistsError as error:
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Файл уже существует. Выберите новое имя для экспорта.") from error
    except (OSError, sqlite3.Error) as error:
        raise ImportCommandError("EXPORT_FAILED", f"Не удалось выгрузить отбор в {format_name.upper()}.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output_path": str(destination), "analysis_count": len(analysis_ids)}


def export_selection_xlsx(database_path, analysis_ids, output_path):
    return _export_selection(database_path, analysis_ids, output_path, "xlsx")


def export_selection_csv(database_path, analysis_ids, output_path):
    return _export_selection(database_path, analysis_ids, output_path, "csv")
