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


def _reported_text(reported):
    """Normalize either semantic evidence objects or legacy string labels."""
    if isinstance(reported, dict):
        value = reported.get("value")
    elif isinstance(reported, str):
        value = reported
    else:
        value = None
    return value.strip() if isinstance(value, str) and value.strip() else None


def reported_target(reported):
    """Resolve reported text to a controlled target without changing the text."""
    text = _reported_text(reported)
    return REPORTED_TARGETS.get(text.casefold()) if text else None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _decision_input(record):
    """Return the scientific evidence only, independent of transport shape.

    Planned records and persisted project projections carry different source
    coordinates and display metadata.  Those fields must not make a valid
    mineral decision appear stale after a lossless database round-trip.
    """
    evidence = []
    for measurement in record.get('measurements') or []:
        if not isinstance(measurement, dict):
            evidence.append(measurement)
            continue
        evidence.append({
            key: measurement.get(key)
            for key in (
                'field', 'unit', 'raw_token', 'qualifier', 'detection_limit',
                'value_status', 'reported_fe_form', 'fe_handling',
            )
        })
    return [evidence, _reported_text(record.get('reported_mineral')), EXTENDED_RULESET_VERSION, INPUT_GATE_VERSION]


def verify_record(record, accepted=None):
    evidence = record.get('measurements') or []
    if accepted is None and isinstance(record.get('mineral_assignment'), dict):
        accepted = record.get('mineral_assignment')
    inputs = {}
    problems = []
    for measurement in evidence:
        field = measurement.get('field') if isinstance(measurement, dict) else None
        if not isinstance(field, str) or not field.strip():
            problems.append('missing_component_field')
            continue
        if measurement.get('unit') != 'wt.%':
            continue
        if field in inputs:
            problems.append('duplicate_component')
        if measurement.get('reported_fe_form') == 'unresolved':
            problems.append('unresolved_iron_form')
        if measurement.get('value_status') != 'numeric':
            problems.append('missing_or_censored_input')
            continue
        try:
            value = float(str(measurement.get('raw_token')).replace(',', '.'))
        except (TypeError, ValueError):
            problems.append('invalid_numeric_input')
            continue
        if not math.isfinite(value) or value < 0:
            problems.append('invalid_numeric_input')
            continue
        inputs[field] = value
    if not REQUIRED_CORE.issubset(inputs) or not ({'FeO', 'FeOt', 'Fe2O3', 'Fe2O3t'} & inputs.keys()):
        problems.append('incomplete_major_element_input')
    if len({'FeO', 'FeOt'} & inputs.keys()) > 1 or len({'Fe2O3', 'Fe2O3t'} & inputs.keys()) > 1:
        problems.append('overlapping_iron_basis')
    input_hash = fingerprint(_decision_input(record))
    reported = record.get('reported_mineral')
    reported_text = _reported_text(reported)
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
        controlled_reported_target = reported_target(reported)
        if not prediction.target or prediction.confidence != 'high':
            result['status'] = 'low_confidence'
        elif not reported_text:
            result['status'] = 'missing_reported'
        elif controlled_reported_target == prediction.target:
            result['status'] = 'consistent'
        elif controlled_reported_target:
            result['status'] = 'conflict'
        else:
            result['status'] = 'unrecognized_reported'
    if accepted:
        if accepted.get('input_fingerprint') == input_hash and accepted.get('ruleset_version') == EXTENDED_RULESET_VERSION:
            result['accepted'] = accepted
            result['status'] = 'verified'
        else:
            result['issues'].append('accepted_assignment_stale')
    result['reported_target'] = reported_target(reported)
    return result


def add_verification(records, recipe):
    accepted = recipe['global_decisions'].get('mineral_acceptances', {})
    for record in records:
        verification = verify_record(record, accepted.get(record['preview_id']))
        record['mineral_verification'] = verification
        if verification.get('accepted'):
            record['mineral_assignment'] = verification['accepted']


def acceptance_scopes(plan, recipe):
    grouped = {}
    for record in plan['planned_records']:
        verification = record.get('mineral_verification')
        if verification and verification['status'] == 'consistent' and verification['confidence'] == 'high':
            grouped.setdefault(verification['prediction'], []).append(record['preview_id'])
    return [{'scope_id': fingerprint([recipe['semantic_fingerprint'], target, ids]),
             'target': target, 'preview_ids': ids, 'count': len(ids)} for target, ids in grouped.items()]
