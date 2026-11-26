"""Read-only descriptive summaries of exact reported measurements."""
from collections import defaultdict, Counter
from contextlib import closing
from math import isfinite
from statistics import mean, median, stdev
import json
from .desktop_workflow import _measurement_numeric_value
from .import_apply import open_project
from .import_preview import ImportCommandError
from .plot_data import _selection, _ACTIVE_ANALYSES

_FIELDS = ("field", "unit", "measurement_set", "method", "reported_fe_form")

def _finite(value):
    return value if value is not None and isfinite(value) else None

def summarize_measurements(rows, ids):
    """Each exact field has at most one observation per Analysis in a summary."""
    grouped = defaultdict(lambda: defaultdict(list))
    for row in rows:
        grouped[tuple(row[field] for field in _FIELDS)][row["analysis_id"]].append(row)
    result = []
    for key, observations in sorted(grouped.items(), key=lambda item: tuple(str(x or "") for x in item[0])):
        counts = Counter()
        values = []
        paired = []
        for analysis_id, records in observations.items():
            if len(records) != 1:
                counts["duplicate"] += 1
                continue
            record = records[0]
            value = _measurement_numeric_value(record)
            if value is None:
                counts["excluded"] += 1
            else:
                values.append(value)
        row = dict(zip(_FIELDS, key))
        row.update(n=len(values), missing=len(ids)-len(observations), duplicate=counts["duplicate"], excluded=counts["excluded"],
                   mean=_finite(mean(values)) if values else None,
                   median=_finite(median(values)) if values else None,
                   minimum=min(values) if values else None, maximum=max(values) if values else None,
                   sd=_finite(stdev(values)) if len(values)>1 else None)
        if len(ids)==2:
            for analysis_id in ids:
                records = observations.get(analysis_id, [])
                paired.append({"raw_tokens":[item["raw_token"] for item in records],
                    "status":"missing" if not records else "duplicate" if len(records)!=1 else "numeric" if _measurement_numeric_value(records[0]) is not None else "excluded",
                    "numeric_value":_measurement_numeric_value(records[0]) if len(records)==1 else None})
            a,b = (item["numeric_value"] for item in paired)
            delta = _finite(b-a) if a is not None and b is not None else None
            row.update(pair=paired, delta=delta, relative_percent=_finite(100*(delta/a)) if delta is not None and a != 0 else None)
        result.append(row)
    return result

def selection_summary(database_path, analysis_ids):
    if not isinstance(analysis_ids,list) or not 1<=len(analysis_ids)<=50000:
        raise ValueError("summary_analysis_ids")
    parameters = _selection(analysis_ids)
    with closing(open_project(database_path)) as connection:
        connection.execute("BEGIN")
        active = connection.execute(f"SELECT a.analysis_id, a.identity_json, s.display_name AS source_name {_ACTIVE_ANALYSES}",parameters).fetchall()
        by_id = {row["analysis_id"]:row for row in active}
        if len(by_id)!=len(analysis_ids):
            raise ImportCommandError("SUMMARY_ANALYSIS_UNAVAILABLE","Часть анализов недоступна. Обновите отбор.")
        rows = connection.execute("""SELECT analysis_id, canonical_field AS field, unit, measurement_set, method,
            reported_fe_form, raw_token, qualifier, value_status
            FROM measurement WHERE analysis_id IN (SELECT value FROM json_each(?)) ORDER BY analysis_id, rowid""",(parameters[1],))
        summary = summarize_measurements(rows,analysis_ids)
        return {"analysis_count":len(analysis_ids),"pair": [{"analysis_id":id,
            "label":" · ".join(value for value in json.loads(by_id[id]["identity_json"]) if value),
            "source_name":by_id[id]["source_name"]} for id in analysis_ids] if len(analysis_ids)==2 else None,
            "rows":summary}
