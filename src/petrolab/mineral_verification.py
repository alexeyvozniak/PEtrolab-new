"""Import-facing checks around the existing versioned PetroLab suggestion rules."""
from dataclasses import asdict
import hashlib
import json
import math

from .mineral_reference import MINERALS
from .alkaline_mineral_reference import ALKALINE_MINERALS
from .mineral_recognition_extended import recognize_mineral_extended, EXTENDED_RULESET_VERSION

INPUT_GATE_VERSION = 'import-wt-percent-complete-core-1'
REQUIRED_CORE = {'SiO2', 'Al2O3', 'MgO', 'CaO', 'Na2O', 'K2O'}
REPORTED_TARGETS = {m.name.casefold(): m.chemical_target for m in (*MINERALS, *ALKALINE_MINERALS)}
REPORTED_TARGETS.update({m.chemical_target.casefold(): m.chemical_target for m in (*MINERALS, *ALKALINE_MINERALS)})


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_record(record, accepted=None):
    evidence = record['measurements']
    inputs = {}
    problems = []
    for measurement in evidence:
        field = measurement['field']
        if measurement['unit'] != 'wt.%':
            continue
        if field in inputs:
            problems.append('duplicate_component')
        if measurement.get('reported_fe_form') == 'unresolved':
            problems.append('unresolved_iron_form')
        if measurement.get('value_status') != 'numeric':
            problems.append('missing_or_censored_input')
            continue
        value = float(str(measurement['raw_token']).replace(',', '.'))
        if not math.isfinite(value) or value < 0:
            problems.append('invalid_numeric_input')
            continue
        inputs[field] = value
    if not REQUIRED_CORE.issubset(inputs) or not ({'FeO', 'FeOt', 'Fe2O3', 'Fe2O3t'} & inputs.keys()):
        problems.append('incomplete_major_element_input')
    if len({'FeO', 'FeOt'} & inputs.keys()) > 1 or len({'Fe2O3', 'Fe2O3t'} & inputs.keys()) > 1:
        problems.append('overlapping_iron_basis')
    input_hash = fingerprint([evidence, record.get('reported_mineral'), record.get('mineral_assignment'),
                              EXTENDED_RULESET_VERSION, INPUT_GATE_VERSION])
    reported = record.get('reported_mineral')
    reported_text = reported.get('value') if reported else None
    result = {'preview_id': record['preview_id'], 'reported_mineral': reported_text,
              'prediction': None, 'confidence': 'unresolved', 'candidates': [],
              'input_fingerprint': input_hash, 'ruleset_version': EXTENDED_RULESET_VERSION,
              'input_gate_version': INPUT_GATE_VERSION, 'accepted': None,
              'issues': sorted(set(problems)), 'status': 'insufficient_input'}
    if not problems:
        prediction = recognize_mineral_extended(inputs)
        result.update(prediction=prediction.target or None, confidence=prediction.confidence,
                      candidates=[asdict(candidate) for candidate in prediction.candidates],
                      reasons=list(prediction.reasons), reference_version=prediction.reference_version,
                      catalog_hash=prediction.catalog_hash)
        reported_target = REPORTED_TARGETS.get((reported_text or '').strip().casefold())
        if not prediction.target or prediction.confidence != 'high':
            result['status'] = 'low_confidence'
        elif not reported_text:
            result['status'] = 'missing_reported'
        elif reported_target == prediction.target:
            result['status'] = 'consistent'
        elif reported_target:
            result['status'] = 'conflict'
        else:
            result['status'] = 'unrecognized_reported'
    if accepted:
        if accepted.get('input_fingerprint') == input_hash and accepted.get('ruleset_version') == EXTENDED_RULESET_VERSION:
            result['accepted'] = accepted
            result['status'] = 'verified'
        else:
            result['issues'].append('accepted_assignment_stale')
    return result


def add_verification(records, recipe):
    accepted = recipe['global_decisions'].get('mineral_acceptances', {})
    for record in records:
        record['mineral_verification'] = verify_record(record, accepted.get(record['preview_id']))


def acceptance_scopes(plan, recipe):
    grouped = {}
    for record in plan['planned_records']:
        verification = record.get('mineral_verification')
        if verification and verification['status'] == 'consistent' and verification['confidence'] == 'high':
            grouped.setdefault(verification['prediction'], []).append(record['preview_id'])
    return [{'scope_id': fingerprint([recipe['semantic_fingerprint'], target, ids]),
             'target': target, 'preview_ids': ids, 'count': len(ids)} for target, ids in grouped.items()]
