"""Prepare only the dedicated empty native QA project; never a user's project."""
import os
import argparse
import hashlib
import json
import subprocess
import uuid
from contextlib import closing
from pathlib import Path

from petrolab.desktop_workflow import list_project_mineral_identifications, decide_project_mineral_assignment
from petrolab.import_apply import apply_import_plan, open_project
from petrolab.import_workspace import ImportWorkspaceStore


def verify_executable(executable, database, source):
    """Repeatable sidecar acceptance against only this dedicated QA project."""
    records = list_project_mineral_identifications(database)['identifications']
    assert len(records) == 100
    ids = [r['analysis_id'] for r in records]
    original = source.read_bytes()
    with closing(open_project(database)) as connection:
        before = [tuple(r) for r in connection.execute('SELECT * FROM measurement ORDER BY rowid')]
        run_count = connection.execute('SELECT COUNT(*) FROM formula_run').fetchone()[0]
    service = subprocess.Popen([str(executable.resolve())], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    def send(command, **extra):
        payload = {'project_database_path': str(database), 'analysis_ids': ids,
            'method_id': 'olivine.oxygen4', 'method_version': '1.0.0',
            'parameters': {'fe_mode': 'all_fe2'}, **extra}
        service.stdin.write(json.dumps({'protocol_version': '1.0', 'request_id': str(uuid.uuid4()),
            'command': command, 'payload': payload}) + '\n')
        service.stdin.flush()
        line = service.stdout.readline()
        if not line:
            raise AssertionError('Packaged service exited before responding')
        return json.loads(line)
    try:
        catalog = send('formula.methods.list')['result']
        assert catalog['analysis_ids'] == ids
        assert [m['method_id'] for m in catalog['methods']] == ['olivine.oxygen4']
        preview = send('formula.preview')['result']
        assert not preview['can_save'] and len(preview['results']) == 100
        assert [r['status'] for r in preview['results']].count('current') == 98
        assert [r['status'] for r in preview['results']].count('failed') == 2
        for result in preview['results']:
            if result['status'] == 'current':
                assert abs(result['values']['Fo'] - 50) < 1e-10
        refused = send('formula.save', preview_fingerprint=preview['input_fingerprint'])
        assert refused['error']['code'] == 'FORMULA_INPUT_INVALID'
        exact = send('project.mineral_identification.list', analysis_ids=[ids[-1]], offset=500)['result']
        assert [r['analysis_id'] for r in exact['identifications']] == [ids[-1]]
    finally:
        service.stdin.close()
        try:
            service.wait(timeout=10)
        except subprocess.TimeoutExpired:
            service.kill(); service.wait()
    with closing(open_project(database)) as connection:
        assert before == [tuple(r) for r in connection.execute('SELECT * FROM measurement ORDER BY rowid')]
        assert connection.execute('SELECT COUNT(*) FROM formula_run').fetchone()[0] == run_count
        assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert source.read_bytes() == original
    print(json.dumps({'service': 'packaged', 'scope': 100, 'ready': 98, 'failed': 2,
        'atomic_refusal': True, 'exact_unloaded_review': True,
        'source_sha256': hashlib.sha256(original).hexdigest(), 'measurements_unchanged': True}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify-executable', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    database = Path(os.environ['APPDATA']) / 'org.petrolab.formula-batch-qa' / 'petrolab-v2.sqlite'
    source = root / 'fixtures/formula/olivine_batch_100.csv'
    if args.verify_executable:
        verify_executable(args.verify_executable, database, source)
        return
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(open_project(database)) as connection:
        if connection.execute('SELECT COUNT(*) FROM analysis').fetchone()[0]:
            raise SystemExit('QA project already contains analyses; not overwriting or reimporting.')
    recipe = ImportWorkspaceStore().command('create', {'sources': [{'staged_path': str(source)}]})['active']['recipe']
    apply_import_plan(database, source, recipe)
    records = list_project_mineral_identifications(database)['identifications']
    assert len(records) == 100
    for record in records:
        decide_project_mineral_assignment(database, record['analysis_id'], 'olivine',
            record['input_fingerprint'], record['ruleset_version'],
            'AT-49 QA fixture: explicit interpretation, not chemical QC; last two Si=0 intentionally invalid')
    print('Prepared 100 explicit assignments in isolated QA project:', database)


if __name__ == '__main__':
    main()
