"""Compare pre-migration project content read-only, without printing user records."""
import argparse
import json
from pathlib import Path
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('database', type=Path)
parser.add_argument('--backup', type=Path)
args = parser.parse_args()

def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'

with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as current:
    result = {'integrity': current.execute('PRAGMA integrity_check').fetchone()[0],
              'schema': current.execute('SELECT project_schema_version FROM project_meta').fetchone()[0],
              'analysis_rows': current.execute('SELECT count(*) FROM analysis').fetchone()[0]}
    if args.backup:
        changed, checked = [], []
        with sqlite3.connect(args.backup.resolve().as_uri() + '?mode=ro', uri=True) as previous:
            for (table,) in previous.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                if table in {'project_meta', 'schema_migration'}:
                    continue
                columns = ','.join(quote(row[1]) for row in previous.execute('PRAGMA table_info(' + quote(table) + ')'))
                query = 'SELECT ' + columns + ' FROM ' + quote(table) + ' ORDER BY rowid'
                if current.execute(query).fetchall() != previous.execute(query).fetchall():
                    changed.append(table)
                checked.append(table)
        result.update(checked_tables=checked, changed_tables=changed)
    print(json.dumps(result, indent=2))
    if result['integrity'] != 'ok' or result.get('changed_tables'):
        raise SystemExit(1)
