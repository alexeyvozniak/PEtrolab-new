"""Reference compositions and normalized coordinates for trace-element patterns."""

from math import ceil, floor, isfinite, log10


PATTERN_ORDERS = {
    "ree_pattern": ("La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"),
    "spider": (
        "Cs", "Tl", "Rb", "Ba", "W", "Th", "U", "Nb", "Ta", "K", "La", "Ce", "Pb", "Pr", "Mo",
        "Sr", "P", "Nd", "F", "Zr", "Hf", "Sm", "Eu", "Sn", "Sb", "Ti", "Gd", "Tb", "Dy", "Li",
        "Ho", "Y", "Er", "Tm", "Yb", "Lu",
    ),
}

# Sun & McDonough (1989), table 1, concentrations in ppm. For the mantle
# pattern use the recommended Cs and Pb denominators from footnote b.
_REFERENCE_ROWS = {
    "Cs": (0.188, 0.0079), "Tl": (0.140, 0.005), "Rb": (2.32, 0.635), "Ba": (2.41, 6.989),
    "W": (0.095, 0.020), "Th": (0.029, 0.085), "U": (0.008, 0.021), "Nb": (0.246, 0.713),
    "Ta": (0.014, 0.041), "K": (545, 250), "La": (0.237, 0.687), "Ce": (0.612, 1.775),
    "Pb": (2.47, 0.071), "Pr": (0.095, 0.276), "Mo": (0.92, 0.063), "Sr": (7.26, 21.1),
    "P": (1220, 95), "Nd": (0.467, 1.354), "F": (60.7, 26), "Zr": (3.87, 11.2),
    "Hf": (0.1066, 0.309), "Sm": (0.153, 0.444), "Eu": (0.058, 0.168), "Sn": (1.72, 0.170),
    "Sb": (0.16, 0.005), "Ti": (445, 1300), "Gd": (0.2055, 0.596), "Tb": (0.0374, 0.108),
    "Dy": (0.2540, 0.737), "Li": (1.57, 1.60), "Ho": (0.0566, 0.164), "Y": (1.57, 4.55),
    "Er": (0.1655, 0.480), "Tm": (0.0255, 0.074), "Yb": (0.170, 0.493), "Lu": (0.0254, 0.074),
}
_C1 = "sun_mcdonough_1989_c1_v1"
_MANTLE = "sun_mcdonough_1989_mantle_diagram_v1"
_REFERENCES = {_C1: (0, "C1 chondrite"), _MANTLE: (1, "Primitive mantle (diagram values)")}
_DEFAULT_REFERENCES = {"ree_pattern": _C1, "spider": _MANTLE}


def pattern_catalog():
    return {
        kind: {
            "elements": list(order),
            "default_normalization": _DEFAULT_REFERENCES[kind],
            "normalizations": [pattern_reference(kind, list(order), reference_id) for reference_id in _REFERENCES],
        }
        for kind, order in PATTERN_ORDERS.items()
    }


def pattern_reference(kind, fields, normalization):
    reference_id = _DEFAULT_REFERENCES[kind] if normalization is None else normalization
    if not isinstance(reference_id, str) or reference_id not in _REFERENCES:
        raise ValueError("normalization")
    order = PATTERN_ORDERS[kind]
    if fields != [element for element in order if element in fields]:
        raise ValueError("pattern axes must follow the element order")
    column, label = _REFERENCES[reference_id]
    return {
        "id": reference_id, "label": label, "unit": "ppm",
        "source": "https://doi.org/10.1144/GSL.SP.1989.042.01.19",
        "table": "Table 1, footnote b" if reference_id == _MANTLE else "Table 1",
        "concentrations": {element: _REFERENCE_ROWS[element][column] for element in fields},
    }


def normalized_pattern_value(value, unit, reference_ppm):
    if value is None or value <= 0:
        return None
    # Dividing by the combined denominator avoids an intermediate underflow
    # when a very small ppb concentration is converted to ppm.
    ratio = value / (reference_ppm * (1000 if unit == "ppb" else 1))
    return ratio if isfinite(ratio) and ratio > 0 else None


def pattern_coordinates(series):
    positions = [log10(vertex["ratio"]) for point in series for vertex in point["vertices"] if vertex["ratio"] is not None]
    if not positions:
        return []
    low, high = floor(min(positions)), ceil(max(positions))
    if high == low:
        low -= 1
        high += 1
    for point in series:
        for vertex in point["vertices"]:
            ratio = vertex["ratio"]
            if ratio is not None:
                vertex["v"] = (log10(ratio) - low) / (high - low)

    step = max(1, ceil((high - low) / 7))
    return [
        {"at": (power - low) / (high - low),
         "label": f"{10 ** power:g}" if -3 <= power <= 3 else f"1e{power}"}
        for power in range(low, high + 1, step)
    ]
