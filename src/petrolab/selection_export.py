"""XLSX export of a snapshot of explicitly selected project analyses."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile
from uuid import UUID

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

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


def export_selection_xlsx(database_path, analysis_ids, output_path):
    if (not isinstance(analysis_ids, list) or not analysis_ids
            or not all(isinstance(item, str) and str(UUID(item)) == item for item in analysis_ids)
            or len(set(analysis_ids)) != len(analysis_ids)):
        raise ValueError("analysis_ids")
    if not isinstance(output_path, str) or not output_path.strip() or Path(output_path).suffix.lower() != ".xlsx":
        raise ValueError("output_path")
    destination = Path(output_path).resolve()
    if destination.exists():
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Файл уже существует. Выберите новое имя для экспорта.")

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

        temporary = None
        try:
            with NamedTemporaryFile(dir=destination.parent, suffix=".xlsx.tmp", delete=False) as stream:
                temporary = Path(stream.name)
            workbook.save(temporary)
            if os.name == "nt":
                temporary.rename(destination)
            else:
                os.link(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except FileExistsError as error:
        raise ImportCommandError("EXPORT_FILE_EXISTS", "Файл уже существует. Выберите новое имя для экспорта.") from error
    except (OSError, sqlite3.Error) as error:
        raise ImportCommandError("EXPORT_FAILED", "Не удалось выгрузить отбор в XLSX.") from error
    finally:
        workbook.close()
    return {"output_path": str(destination), "analysis_count": len(analysis_ids)}
