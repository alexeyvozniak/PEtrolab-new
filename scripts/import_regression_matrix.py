"""Read-only import corpus evidence. Print JSON; never apply imports to projects."""
import argparse
from collections import Counter
import hashlib
import json
import sys
from pathlib import Path

from petrolab.desktop_workflow import suggest_import_recipe, bulk_unit_scopes, bulk_ignore_scopes
from petrolab.import_preview import inspect_source, create_import_plan
from petrolab.import_recognition import MEASUREMENT_FIELDS, field_token, normalized
from petrolab.analyte_dictionary import recognize_analyte, DICTIONARY_VERSION
from petrolab.mineral_verification import verify_record

parser = argparse.ArgumentParser()
sys.stdout.reconfigure(encoding='utf-8')
parser.add_argument('roots', nargs='*', default=['fixtures/import/real-world'])
args = parser.parse_args()
result = {'dictionary_version': DICTIONARY_VERSION, 'files': [], 'rows': [], 'new_headers': [],
          'ground_truth': 'Sample merge/split and mineral truth require owner labels; counts are not ground truth.'}
seen = set()
for root in map(Path, args.roots):
    for source in sorted(root.rglob('*')):
        if source.suffix.lower() not in {'.xls', '.xlsx'} or not source.is_file():
            continue
        fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        try:
            inspection = inspect_source(source)
            suggestion = suggest_import_recipe(source)
            recipe = suggestion['recipe']
            plan = create_import_plan(inspection, recipe)
            file_data = {'name': source.name, 'sha256': fingerprint, 'source_format': inspection.source_format,
                'sheets': len(inspection.sheets), 'blocks': len(recipe['sections']),
                'planned_analyses': plan['summary']['planned_analysis_count'],
                'planned_measurements': plan['summary']['planned_measurement_count'],
                'unresolved_fields': sum(w.get('code') in {'UNIT_REQUIRES_REVIEW', 'UNMAPPED_FIELD_REQUIRES_REVIEW'} for w in suggestion['warnings']),
                'bulk_unit_scopes': len(bulk_unit_scopes(source, recipe)['scopes']),
                'bulk_ignore_scopes': len(bulk_ignore_scopes(source, recipe)['scopes']),
                'duplicate_groups': plan['summary']['duplicate_candidate_groups']}
            result['files'].append(file_data)
            for section in recipe['sections']:
                records = [r for r in plan['planned_records'] if r['block_id'] == section['block_id']]
                fields = section['mappings']
                recognized = [recognize_analyte(f.get('source_header') or '') for f in fields]
                samples = [r['sample_association']['reported'] for r in records]
                minerals = Counter(verify_record(r)['status'] for r in records)
                for field, match in zip(fields, recognized):
                    header = field.get('source_header') or ''
                    prior = MEASUREMENT_FIELDS.get(normalized(header)) or MEASUREMENT_FIELDS.get(field_token(header))
                    if match['automatic'] and prior != match['canonical_field']:
                        result['new_headers'].append({'file': source.name, 'sheet': section['sheet_name'], 'header': header,
                            'old_component': prior, 'canonical': match['canonical_field'], 'confidence': match['confidence'], 'unit': field.get('unit')})
                result['rows'].append({'file': source.name, 'sheet': section['sheet_name'], 'block': section['block_id'],
                    'analyses': len(records), 'samples_detected': len({s['value'] for s in samples if s}),
                    'inferred_samples': sum(bool(s and s['origin'] == 'automatically_inferred') for s in samples),
                    'unresolved_samples': sum(s is None for s in samples),
                    'unlinked_sample_entities': len(records), 'automatic_sample_entity_merges': 0,
                    'analytes_auto_identified': sum(m['automatic'] for m in recognized),
                    'analytes_auto_mapped': sum(f['target_role'] == 'measurement' for f in fields),
                    'aliases': [m['raw_header'] for m in recognized if m['confidence'] in {'known_alias', 'project_alias'}],
                    'unresolved_headers': [f['source_header'] for f in fields if f.get('review_decision') == 'unresolved'],
                    'mineral_results': dict(minerals), 'mineral_conflicts': minerals['conflict'],
                    'sample_ground_truth': 'UNVERIFIED',
                    'integrity': 'PASS' if hashlib.sha256(source.read_bytes()).hexdigest() == fingerprint else 'FAIL'})
        except Exception as error:
            result['files'].append({'name': source.name, 'error': str(error), 'integrity': 'FAIL'})
print(json.dumps(result, ensure_ascii=False, indent=2))
