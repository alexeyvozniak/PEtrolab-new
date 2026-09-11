"""Import-facing checks around the existing versioned PetroLab suggestion rules."""
from dataclasses import asdict
import hashlib
import json
import math

from .mineral_reference import MINERALS
from .alkaline_mineral_reference import ALKALINE_MINERALS
from .mineral_recognition_extended import recognize_mineral_extended, EXTENDED_RULESET_VERSION

INPUT_GATE_VERSION = 'import-wt-percent-complete-core-2'
LABEL_VERSION = 'mineral-labels-2026-09-11'
REQUIRED_CORE = {'SiO2', 'Al2O3', 'MgO', 'CaO', 'Na2O', 'K2O'}
CONTROLLED_LABELS = {m.name.casefold(): m.name for m in (*MINERALS, *ALKALINE_MINERALS)}
CONTROLLED_LABELS.update({m.chemical_target.casefold(): m.chemical_target for m in (*MINERALS, *ALKALINE_MINERALS)})
LABEL_ALIASES = {
    'флогопит': 'phlogopite', 'phl': 'phlogopite', 'биотит': 'biotite', 'bt': 'biotite',
    'диопсид': 'diopside', 'cpx': 'clinopyroxene', 'клинопироксен': 'clinopyroxene',
    'opx': 'orthopyroxene', 'ортопироксен': 'orthopyroxene', 'оливин': 'olivine',
    'ol': 'olivine', 'гранат': 'garnet', 'grt': 'garnet', 'андрадит': 'andradite',
    'апатит': 'apatite', 'ap': 'apatite', 'нефелин': 'nepheline', 'ne': 'nepheline',
    'перовскит': 'perovskite', 'кварц': 'quartz', 'qtz': 'quartz',
    'форстерит': 'forsterite', 'аннит': 'annite', 'мусковит': 'muscovite',
}
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
    text = controlled_label(reported)
    return REPORTED_TARGETS.get(text.casefold()) if text else None


def controlled_label(value):
    text = _reported_text(value)
    key = text.casefold() if text else ''
    return CONTROLLED_LABELS.get(LABEL_ALIASES.get(key, key).casefold())


def mineral_options():
    return sorted(set(CONTROLLED_LABELS.values()))


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
    return [evidence, _reported_text(record.get('reported_mineral')), EXTENDED_RULESET_VERSION, INPUT_GATE_VERSION, LABEL_VERSION]


def verify_record(record, accepted=None):
    evidence = record.get('measurements') or []
    if accepted is None and isinstance(record.get('mineral_assignment'), dict):
        accepted = record.get('mineral_assignment')
    inputs = {}
    problems = []
    unavailable_volatiles = []
    seen_fields = set()
    for measurement in evidence:
        field = measurement.get('field') if isinstance(measurement, dict) else None
        if not isinstance(field, str) or not field.strip():
            problems.append('missing_component_field')
            continue
        if measurement.get('unit') != 'wt.%':
            continue
        if field in seen_fields:
            problems.append('duplicate_component')
        seen_fields.add(field)
        if measurement.get('reported_fe_form') == 'unresolved':
            problems.append('unresolved_iron_form')
        if measurement.get('value_status') != 'numeric':
            if field in {'F', 'Cl'} and measurement.get('value_status') in {'missing', 'below_detection_limit'}:
                unavailable_volatiles.append(field)
                continue
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
              'label_version': LABEL_VERSION,
              'missing_components': sorted(REQUIRED_CORE - inputs.keys()) + ([] if {'FeO', 'FeOt', 'Fe2O3', 'Fe2O3t'} & inputs.keys() else ['FeO / FeOt / Fe2O3 / Fe2O3t']),
              'excluded_inputs': sorted(set(unavailable_volatiles)),
              'issues': sorted(set(problems)), 'status': 'insufficient_input'}
    if not problems:
        prediction = recognize_mineral_extended(inputs)
        if unavailable_volatiles and prediction.target != 'olivine':
            result['issues'].append('missing_or_censored_input')
            prediction = None
    else:
        prediction = None
    if prediction is not None:
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
    if accepted and accepted.get('origin') == 'user_assigned':
        # Range annotations are explicit interpretations, not classifier runs.
        # Keep the stored annotation unchanged and expose its controlled label.
        result['manual_assignment'] = accepted
        label = controlled_label(accepted)
        if label:
            result['accepted'] = {**accepted, 'target': label}
            result['status'] = 'manually_assigned'
        else:
            result['status'] = 'manual_unresolved'
            result['issues'].append('manual_label_unrecognized')
    elif accepted:
        if accepted.get('input_fingerprint') == input_hash and accepted.get('ruleset_version') == EXTENDED_RULESET_VERSION:
            result['accepted'] = accepted
            result['status'] = 'verified'
        else:
            result['issues'].append('accepted_assignment_stale')
            result['status'] = 'stale_assignment'
    result['reported_target'] = reported_target(reported)
    return result


def add_verification(records, recipe):
    accepted = recipe['global_decisions'].get('mineral_acceptances', {})
    for record in records:
        manual = record.get('mineral_assignment')
        decision = manual if manual and manual.get('origin') == 'user_assigned' else accepted.get(record['preview_id'])
        verification = verify_record(record, decision)
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
