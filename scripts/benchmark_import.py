"""Reproducible import timing; run with PYTHONPATH pointing at the tested checkout."""
import argparse
import csv
import hashlib
import json
import platform
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path

from openpyxl import Workbook
from petrolab.import_workspace import ImportWorkspaceStore


OXIDES = ("SiO2", "TiO2", "Al2O3", "FeO", "MnO", "MgO", "CaO", "Na2O", "K2O", "Cr2O3", "NiO", "P2O5")


def rows(count):
    yield ["Analysis", *[f"{oxide} [wt.%]" for oxide in OXIDES]]
    for index in range(count):
        yield [f"A{index + 1:07}", *[f"{(index + col) % 50 + 1}.{col:02}" for col in range(len(OXIDES))]]


def fixture(directory, count, fmt):
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / f"synthetic-{count}.{fmt}"
    if not source.exists():
        if fmt == "csv":
            with source.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream).writerows(rows(count))
        else:
            book = Workbook(write_only=True)
            sheet = book.create_sheet("Analyses")
            for row in rows(count):
                sheet.append(row)
            book.save(source)
    return source


def timed(operation):
    start = time.perf_counter()
    value = operation()
    return value, round(time.perf_counter() - start, 6)


def benchmark(source, count):
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "project.sqlite"
        store = ImportWorkspaceStore()
        current, create = timed(lambda: store.command("create", {
            "project_database_path": str(database), "sources": [{"staged_path": str(source)}]}))
        session = current["session"]
        readiness = session["readiness"]
        if not readiness["ready_to_commit"]:
            raise RuntimeError(f"Fixture not ready: {readiness}")
        params = {"workspace_id": session["workspace_id"], "source_id": session["active_source_id"],
                  "expected_revision": session["draft_revision"]}
        sheet = session["sources"][0]["sheets"][0]["physical_sheet_name"]
        _, get = timed(lambda: store.command("get", params))
        times = []
        for start_row in (2, max(2, count // 2), max(2, count - 25), 2, 3):
            window, duration = timed(lambda: store.command("preview_window", {
                **params, "sheet_name": sheet, "start_row": start_row, "row_count": 30}))
            assert window["rows"], window
            times.append(duration)
        payload_bytes = len(json.dumps(current, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        try:
            from petrolab.ndjson_service import compact_workspace_review
        except ImportError:
            compact_payload_bytes = payload_bytes
        else:
            packed, pack_s = timed(lambda: compact_workspace_review(current))
            compact_payload_bytes = len(json.dumps(packed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            del packed
        reference = {"source_id": session["active_source_id"], "plan_fingerprint": session["plans"][0]["plan_fingerprint"]}
        activated, activate = timed(lambda: store.command("apply_decision", {**params,
            "decision": {"kind": "activate", "block_id": session["active_block_id"]},
            "known_active_plan": reference}))
        activation_payload = len(json.dumps(activated, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if "plan_reference" in activated["active"]:
            assert activated["active"]["plan_reference"] == reference
            assert "plan" not in activated["active"]
        else:
            assert activated["active"]["plan"] == current["active"]["plan"]
        assert activated["session"]["readiness"] == readiness
        params["expected_revision"] = activated["session"]["draft_revision"]
        del current, activated
        saved, commit = timed(lambda: store.command("commit", params))
        assert saved["analysis_count"] == count, saved["analysis_count"]
        assert saved["measurement_count"] == count * len(OXIDES), saved["measurement_count"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        connection = sqlite3.connect(database)
        try:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA foreign_key_check").fetchone() is None
            observed = hashlib.sha256()
            for row in connection.execute("""SELECT a.sheet_name, m.source_row_number, m.physical_source_column_index,
                m.canonical_field, m.unit, m.raw_token, m.value_status, m.reported_fe_form, m.fe_handling
                FROM measurement m JOIN analysis a ON a.analysis_id = m.analysis_id
                ORDER BY a.sheet_name, m.source_row_number, m.physical_source_column_index, m.canonical_field"""):
                observed.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            provenance = hashlib.sha256()
            for query in (
                """SELECT a.sheet_name, p.source_row_number, p.source_column_index, p.source_cell,
                          p.source_header, p.raw_token, p.qualifier, p.value_status
                   FROM source_cell_provenance p JOIN analysis a ON a.analysis_id = p.analysis_id
                   ORDER BY a.sheet_name, p.source_row_number, p.source_column_index, p.source_header""",
                """SELECT a.sheet_name, p.row_number, p.source_column_name, p.raw_token,
                          p.normalized_token, p.qualifier, p.value_status
                   FROM source_row_provenance p JOIN analysis a ON a.analysis_id = p.analysis_id
                   ORDER BY a.sheet_name, p.row_number, p.source_column_name""",
                """SELECT a.sheet_name, a.source_row_number, s.sample_association_json,
                          s.reported_mineral_json, s.mineral_assignment_json,
                          s.mineral_verification_json, s.analytical_method_json
                   FROM analysis_import_semantics s JOIN analysis a ON a.analysis_id = s.analysis_id
                   ORDER BY a.sheet_name, a.source_row_number""",
            ):
                for row in connection.execute(query):
                    provenance.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            for table in ("source_row_provenance", "source_cell_provenance"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == saved["measurement_count"]
        finally:
            connection.close()
        return {"rows": count, "format": source.suffix[1:], "source_sha256": before,
                "provenance_sha256": provenance.hexdigest(),
                "measurement_sha256": observed.hexdigest(), "measurements": saved["measurement_count"],
                "create_s": create, "get_s": get, "preview_samples_s": times,
                "preview_median_s": statistics.median(times), "activate_s": activate, "activate_payload_bytes": activation_payload, "commit_s": commit,
                "review_payload_bytes": payload_bytes, "compact_review_payload_bytes": compact_payload_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--rows", type=int, nargs="+", default=[1000, 10000])
    parser.add_argument("--formats", choices=["csv", "xlsx"], nargs="+", default=["csv", "xlsx"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for fmt in args.formats:
        for count in args.rows:
            result = benchmark(fixture(args.fixtures, count, fmt), count)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"python": platform.python_version(), "platform": platform.platform(),
                                      "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
