"""Create one isolated native QA project; refuse to touch an existing database."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path

from petrolab.desktop_workflow import decide_project_mineral_assignment, list_project_mineral_identifications
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_workspace import ImportWorkspaceStore


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'fixtures/formula/orthopyroxene_tariat2018.csv'
    database = Path(os.environ['APPDATA']) / 'org.petrolab.opx-qa-20261108' / 'petrolab-v2.sqlite'
    if database.exists():
        raise SystemExit('The dedicated Opx QA database already exists; refusing to overwrite it.')
    original = source.read_bytes()
    database.parent.mkdir(parents=True, exist_ok=True)
    recipe = ImportWorkspaceStore().command('create', {'sources': [
        {'staged_path': str(source)}]})['active']['recipe']
    apply_import_plan(database, source, recipe)
    records = list_project_mineral_identifications(database)['identifications']
    if len(records) != 1:
        raise AssertionError('Expected exactly one Opx reference analysis')
    record = records[0]
    decide_project_mineral_assignment(database, record['analysis_id'], 'enstatite',
        record['input_fingerprint'], record['ruleset_version'],
        'AT-50 native QA: published Tariat mean; explicit interpretation, not QC')
    with closing(open_project(database)) as connection:
        measurements = [tuple(row) for row in connection.execute('SELECT * FROM measurement ORDER BY rowid')]
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert source.read_bytes() == original
    print(json.dumps({'database': str(database), 'analysis_id': record['analysis_id'],
        'source_sha256': hashlib.sha256(original).hexdigest(),
        'measurements_sha256': hashlib.sha256(json.dumps(measurements, ensure_ascii=False,
                                  separators=(',', ':')).encode('utf-8')).hexdigest(),
        'measurements': len(measurements)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
