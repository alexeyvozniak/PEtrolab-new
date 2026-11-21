"""Anhydrous olivine formula on a fixed four-oxygen basis."""

import math

from .import_preview import ImportCommandError


# CIAAW abridged atomic weights 2024. Oxide factors are recorded with each run.
_OXYGEN_WEIGHT = 15.999
_OXIDES = {
    "SiO2": ("Si", 28.085, 1, 2), "TiO2": ("Ti", 47.867, 1, 2),
    "Al2O3": ("Al", 26.982, 2, 3), "Cr2O3": ("Cr", 51.996, 2, 3),
    "FeO": ("Fe2+", 55.845, 1, 1), "Fe2O3": ("Fe3+", 55.845, 2, 3),
    "MnO": ("Mn", 54.938, 1, 1), "MgO": ("Mg", 24.305, 1, 1),
    "NiO": ("Ni", 58.693, 1, 1), "CaO": ("Ca", 40.078, 1, 1),
    "Na2O": ("Na", 22.990, 2, 1), "K2O": ("K", 39.098, 2, 1),
}
OLIVINE = {
    "method_id": "formula.olivine.4o", "version": "1.0.0", "name": "Оливин на 4 атома кислорода",
    "input_unit": "wt.%", "oxygen_basis": 4, "cation_basis": None,
    "required_components": ["SiO2", "MgO", "FeO"],
    "components": {
        oxide: {"species": species, "cations": cations, "oxygens": oxygens,
                "atomic_weight": weight, "molar_mass": cations * weight + oxygens * _OXYGEN_WEIGHT}
        for oxide, (species, weight, cations, oxygens) in _OXIDES.items()
    },
    "oxygen_atomic_weight": _OXYGEN_WEIGHT,
    "iron_policy": "FeO as Fe2+, explicitly reported Fe2O3 as Fe3+; no redox estimation or conversion of total iron",
    "missing_policy": "required oxides missing or censored block the run; unselected optional oxides are unmodelled",
    "oh_basis": "anhydrous model; OH, F, Cl and water are not estimated",
    "end_member_rules": {"basis": "molar percentage of included divalent cations; no site allocation",
                         "species": {"Fo": "Mg", "Fa": "Fe2+", "Te": "Mn", "CaOl": "Ca", "Lei": "Ni"}},
    "applicability_checks": {"oxide_sum_wt_pct": [95, 105], "cation_sum_apfu": [2.9, 3.1]},
    "references": ["https://doi.org/10.1180/mgm.2022.113", "https://ciaaw.org/abridged-atomic-weights.htm",
                   "https://doi.org/10.1016/j.cageo.2012.05.023"],
    "independent_benchmarks": ["Gündüz and Asan (2023), Table 1, column 5"],
}


def calculate_olivine(values, method=OLIVINE):
    components = method["components"]
    if not method["required_components"] or not set(method["required_components"]) <= values.keys() or values.keys() - components.keys():
        raise ImportCommandError("FORMULA_UNSUPPORTED_COMPONENTS", "Нужны SiO₂, MgO и FeO; выберите только поддерживаемые оксиды.")
    if any(type(value) not in (int, float) or not 0 <= value <= 100 for value in values.values()) or values["SiO2"] <= 0:
        raise ImportCommandError("FORMULA_INVALID_MEASUREMENT", "Для расчёта нужны массовые доли от 0 до 100 wt.% и положительный SiO₂.")
    moles = {oxide: value / components[oxide]["molar_mass"] for oxide, value in values.items()}
    oxygen = math.fsum(amount * components[oxide]["oxygens"] for oxide, amount in moles.items())
    if oxygen <= 0:
        raise ImportCommandError("FORMULA_INVALID_MEASUREMENT", "Кислородный знаменатель ниже числовой точности.")
    apfu = {components[oxide]["species"]: (amount / oxygen) * method["oxygen_basis"] * components[oxide]["cations"]
            for oxide, amount in moles.items()}
    bounds = method["applicability_checks"]
    total = math.fsum(values.values())
    cations = math.fsum(apfu.values())
    warnings = []
    for code, value in (("oxide_sum_wt_pct", total), ("cation_sum_apfu", cations)):
        lower, upper = bounds[code]
        if not lower <= value <= upper:
            warnings.append({"kind": "outside_model_check", "field": code, "value": value, "range": [lower, upper]})
    species = method["end_member_rules"]["species"]
    modelled = {name: apfu[element] for name, element in species.items() if element in apfu}
    denominator = math.fsum(modelled.values())
    fractions = {key: value / denominator * 100 for key, value in modelled.items()} if denominator else {}
    return {"apfu": apfu, "divalent_component_mol_percent": fractions, "oxide_sum_wt_pct": total, "cation_sum_apfu": cations,
            "unmodelled_optional_oxides": sorted(components.keys() - values.keys()), "warnings": warnings}
