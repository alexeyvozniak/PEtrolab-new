from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from petrolab.import_preview import inspect_source  # noqa: E402


REGISTRY_PATH = ROOT / "fixtures" / "import" / "real-corpus.registry.json"
DEFAULT_CORPUS_DIR = ROOT / "fixtures" / "import" / "real-private"
BASELINE_NAME = "real-corpus.baseline.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(registry: dict) -> list[dict]:
    if registry.get("corpus_version") != 1:
        raise SystemExit("real-corpus.registry.json must use corpus_version=1")
    if registry.get("authority") != "real_source_workbooks":
        raise SystemExit("Real import corpus must declare real_source_workbooks as its authority")
    if registry.get("storage") != "external_private":
        raise SystemExit("Raw real workbooks must remain in external_private storage")

    cases = registry.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SystemExit("Real import corpus registry must contain cases")

    case_ids: set[str] = set()
    accepted_names: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.startswith("real-"):
            raise SystemExit(f"Invalid real corpus case_id: {case_id!r}")
        if case_id in case_ids:
            raise SystemExit(f"Duplicate real corpus case_id: {case_id}")
        case_ids.add(case_id)

        names = case.get("accepted_names")
        if not isinstance(names, list) or not names or not all(isinstance(name, str) and name for name in names):
            raise SystemExit(f"{case_id}: accepted_names must contain at least one real workbook name")
        for name in names:
            lowered = name.casefold()
            if lowered in accepted_names:
                raise SystemExit(f"Workbook name is registered more than once: {name}")
            accepted_names.add(lowered)
            if Path(name).suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
                raise SystemExit(f"{case_id}: unsupported real workbook extension in {name}")

        focus = case.get("regression_focus")
        if not isinstance(focus, list) or not focus or not all(isinstance(item, str) and item for item in focus):
            raise SystemExit(f"{case_id}: regression_focus must be non-empty")
        if case.get("required") is not True:
            raise SystemExit(f"{case_id}: every normative real workbook must be required")

    if len(cases) < 6:
        raise SystemExit("Normative real import corpus must contain at least six real workbooks")
    return cases


def locate_case_file(corpus_dir: Path, case: dict) -> Path | None:
    for name in case["accepted_names"]:
        direct = corpus_dir / name
        if direct.is_file():
            return direct
    for name in case["accepted_names"]:
        matches = [path for path in corpus_dir.rglob(name) if path.is_file()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit(f"{case['case_id']}: multiple copies found for {name}; keep exactly one normative source")
    return None


def snapshot_workbook(path: Path) -> dict:
    before = sha256_file(path)
    inspection = inspect_source(path)
    after = sha256_file(path)
    if before != after:
        raise SystemExit(f"Import inspection mutated normative source workbook: {path}")
    if inspection.fingerprint != before:
        raise SystemExit(f"PetroLab source fingerprint differs from SHA-256 for {path}")

    projection = inspection.projection()
    warnings = projection.get("warnings", [])
    warning_codes = sorted({warning.get("code") for warning in warnings if warning.get("code")})
    return {
        "sha256": before,
        "file_name": path.name,
        "source_format": path.suffix.lower().lstrip("."),
        "sheets": [
            {
                "name": sheet.name,
                "physical_row_count": len(sheet.rows),
            }
            for sheet in inspection.sheets
        ],
        "candidate_block_count": len(projection.get("candidate_blocks", [])),
        "warning_codes": warning_codes,
    }


def compare_snapshot(case_id: str, observed: dict, expected: dict) -> None:
    keys = ("sha256", "source_format", "sheets", "candidate_block_count", "warning_codes")
    differences = [key for key in keys if observed.get(key) != expected.get(key)]
    if differences:
        details = "\n".join(
            f"  {key}: expected={expected.get(key)!r} observed={observed.get(key)!r}"
            for key in differences
        )
        raise SystemExit(f"{case_id}: normative real-workbook baseline changed:\n{details}")


def write_candidate_baseline(corpus_dir: Path, cases: list[dict]) -> Path:
    missing: list[str] = []
    snapshots: dict[str, dict] = {}
    for case in cases:
        source = locate_case_file(corpus_dir, case)
        if source is None:
            missing.append(f"{case['case_id']} ({' | '.join(case['accepted_names'])})")
            continue
        snapshots[case["case_id"]] = snapshot_workbook(source)

    if missing:
        raise SystemExit("Cannot baseline an incomplete real corpus. Missing:\n- " + "\n- ".join(missing))

    baseline = {
        "baseline_version": 1,
        "registry_version": 1,
        "review_status": "candidate",
        "cases": snapshots,
    }
    target = corpus_dir / BASELINE_NAME
    target.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def validate_real_corpus(corpus_dir: Path, cases: list[dict], require_all: bool) -> None:
    found: dict[str, Path] = {}
    missing: list[str] = []
    for case in cases:
        source = locate_case_file(corpus_dir, case)
        if source is None:
            missing.append(f"{case['case_id']} ({' | '.join(case['accepted_names'])})")
        else:
            found[case["case_id"]] = source

    if require_all and missing:
        raise SystemExit("Normative real import corpus is incomplete. Missing:\n- " + "\n- ".join(missing))
    if not found:
        if require_all:
            raise SystemExit("Normative real import corpus directory contains no registered workbooks")
        print(f"Real corpus not mounted at {corpus_dir}; registry validation passed.")
        return

    baseline_path = corpus_dir / BASELINE_NAME
    baseline = load_json(baseline_path) if baseline_path.is_file() else None
    if require_all:
        if baseline is None:
            raise SystemExit(
                f"Missing approved private baseline {baseline_path}. "
                "Create a candidate with --write-candidate-baseline, review it, then set review_status to approved."
            )
        if baseline.get("baseline_version") != 1 or baseline.get("registry_version") != 1:
            raise SystemExit("Private real-corpus baseline version does not match the registry")
        if baseline.get("review_status") != "approved":
            raise SystemExit("Private real-corpus baseline must be explicitly reviewed and marked approved")

    expected_cases = baseline.get("cases", {}) if baseline else {}
    for case in cases:
        source = found.get(case["case_id"])
        if source is None:
            continue
        observed = snapshot_workbook(source)
        expected = expected_cases.get(case["case_id"])
        if require_all and not isinstance(expected, dict):
            raise SystemExit(f"Approved baseline is missing {case['case_id']}")
        if isinstance(expected, dict):
            compare_snapshot(case["case_id"], observed, expected)
        print(
            f"PASS {case['case_id']}: {source.name}; "
            f"sheets={len(observed['sheets'])}; blocks={observed['candidate_block_count']}; "
            f"sha256={observed['sha256'][:12]}…"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate PetroLab's private normative corpus of real import workbooks.")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path(os.environ.get("PETROLAB_REAL_IMPORT_CORPUS_DIR", DEFAULT_CORPUS_DIR)),
        help="Directory containing the private real Excel corpus.",
    )
    parser.add_argument("--manifest-only", action="store_true", help="Validate only the committed safe registry.")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Fail unless every registered real workbook and an approved private baseline are present.",
    )
    parser.add_argument(
        "--write-candidate-baseline",
        action="store_true",
        help="Inspect every real workbook and write a private candidate baseline for review.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_json(REGISTRY_PATH)
    cases = validate_registry(registry)
    print(f"Real import registry: {len(cases)} required workbooks")

    if args.manifest_only:
        return

    corpus_dir = args.corpus_dir.expanduser().resolve()
    if args.write_candidate_baseline:
        target = write_candidate_baseline(corpus_dir, cases)
        print(f"Candidate baseline written to {target}. Review it before marking review_status=approved.")
        return

    validate_real_corpus(corpus_dir, cases, require_all=args.require_all)


if __name__ == "__main__":
    main()
