"""Persist one manual analysis and its point link in the same transaction."""

from contextlib import closing
import csv
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from .import_apply import _now, _persist_import, _persist_samples, _validated_import, open_project
from .import_preview import ImportCommandError, _preview_id, _qualifier, inspect_source, semantic_fingerprint, value_status
from .media_import import _text, _uuid, write_point_journal


FIELDS = ("SiO2", "MgO", "TiO2", "Al2O3", "FeO")
METHODS = {"EPMA", "SEM-EDS"}


def create_manual_analysis(database_path, point_id, entry):
    _uuid(point_id, "point_id")
    if not isinstance(entry, dict):
        raise ValueError("entry")
    identity = _text(entry.get("identity"), "identity", 120)
    actor = _text(entry.get("operator"), "operator", 120)
    method = entry.get("method")
    if not isinstance(method, str) or method not in METHODS:
        raise ImportCommandError("INVALID_MANUAL_METHOD", "Выберите метод измерения оксидов.")
    try:
        observed_date = date.fromisoformat(entry.get("measurement_date", "")).isoformat()
    except (TypeError, ValueError) as exc:
        raise ImportCommandError("INVALID_MANUAL_DATE", "Укажите дату измерения.") from exc
    comment = entry.get("comment", "")
    if not isinstance(comment, str) or len(comment) > 200:
        raise ValueError("comment")
    values = entry.get("measurements")
    if not isinstance(values, dict) or not values or not values.keys() <= set(FIELDS):
        raise ImportCommandError("INVALID_MANUAL_MEASUREMENT", "Укажите хотя бы один компонент из формы.")
    for field, token in values.items():
        if not isinstance(token, str) or len(token) > 64 or value_status(token) not in {"numeric", "below_detection_limit"}:
            raise ImportCommandError("INVALID_MANUAL_MEASUREMENT", f"{field}: введите число или значение ниже предела обнаружения.")
        if _qualifier(token) == ("below_detection_limit", None) and token.strip().lower() not in {"<dl", "<dl>", "bdl"}:
            raise ImportCommandError("INVALID_MANUAL_MEASUREMENT", f"{field}: укажите конечное числовое значение предела обнаружения.")

    managed_files = []
    with TemporaryDirectory(prefix="petrolab-manual-") as temporary, closing(open_project(database_path)) as connection:
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                sample = connection.execute("""
                    SELECT sample_id, sample_name FROM analytical_point JOIN sample USING (sample_id)
                    WHERE analytical_point_id = ?
                """, (point_id,)).fetchone()
                if sample is None:
                    raise ImportCommandError("POINT_UNAVAILABLE", "Аналитическая точка недоступна.")
                existing = connection.execute("""
                    SELECT 1 FROM import_batch b JOIN analysis a USING (import_batch_id)
                    LEFT JOIN import_batch_retraction r USING (import_batch_id)
                    WHERE r.import_batch_id IS NULL
                          AND json_extract(b.plan_json, '$.manual_entry.point_id') = ?
                          AND json_extract(b.plan_json, '$.manual_entry.method') = ?
                          AND json_extract(a.identity_json, '$[0]') = ?
                """, (point_id, method, identity)).fetchone()
                if existing:
                    raise ImportCommandError("MANUAL_ANALYSIS_EXISTS", "У этой точки уже есть ручная запись с таким методом и номером.")
                source = Path(temporary) / "Ручной ввод.csv"
                timestamp = _now()
                recipe = _write_source(source, sample, identity, method, actor, observed_date, comment, values, timestamp)
                inspection, plan = _validated_import(source, recipe)
                plan["manual_entry"] = {"point_id": point_id, "method": method, "operator": actor,
                                        "measurement_date": observed_date, "comment": comment}
                _persist_samples(connection, plan["planned_records"], timestamp)
                persisted = _persist_import(connection, database_path, source, recipe, inspection, plan, managed_files)
                analysis_id = connection.execute("SELECT analysis_id FROM analysis WHERE import_batch_id = ?",
                                                 (persisted["import_batch_id"],)).fetchone()[0]
                connection.execute("INSERT INTO analytical_point_analysis VALUES (?, ?, 'same_point', ?)",
                                   (point_id, analysis_id, timestamp))
                journal = write_point_journal(connection, point_id, [analysis_id], actor, "link_analytical_point", "same_point")
                return {"analysis_id": analysis_id, "source_id": persisted["source_id"], "journal": journal}
        except Exception:
            for path in managed_files:
                path.unlink(missing_ok=True)
            raise


def _write_source(source, sample, identity, method, actor, observed_date, comment, values, timestamp):
    fields = [field for field in FIELDS if field in values]
    headers = ["Analysis", "Sample", "Method", "Operator", "Date", "Comment", *[f"{field} (wt.%)" for field in fields]]
    with source.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerow([identity, sample["sample_name"], method, actor, observed_date, comment, *[values[field] for field in fields]])
    inspection = inspect_source(source)
    sheet = inspection.sheets[0].name
    block = "manual-analysis"
    mappings = []
    for index, (header, field) in enumerate(zip(headers, [*headers[:6], *fields], strict=True)):
        role = "identity" if index == 0 else "metadata" if index < 6 else "measurement"
        mappings.append({"source_column_index": index, "source_header": header, "target_role": role,
                         "canonical_field": field, "unit": "wt.%" if role == "measurement" else None,
                         "measurement_semantics": "measured" if role == "measurement" else role})
    preview_id = _preview_id(inspection.fingerprint, sheet, 2, block, "rows_are_analyses")
    recipe = {"source_file_sha256": inspection.fingerprint, "source_format": "csv", "ownership_mode": "managed_copy",
              "sections": [{"sheet_name": sheet, "block_id": block, "header_row": 1, "data_start_row": 2, "data_end_row": 2,
                            "mappings": mappings}],
              "global_decisions": {"fe_semantics": "separate_fe2_fe3", "duplicate_policy": "keep_all",
                  "unit_policy": "explicit_per_measurement_column", "censored_value_policy": "preserve_original_token_and_detection_limit",
                  "sample_assignments": {preview_id: {"sample_id": sample["sample_id"], "sample_name": sample["sample_name"],
                                                        "mode": "existing", "decided_at": timestamp}}}}
    recipe["semantic_fingerprint"] = semantic_fingerprint(recipe)
    return recipe
