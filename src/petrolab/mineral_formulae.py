"""Versioned oxide-normalized methods adapted from the PetroLab v1 formula registry."""

import math

from .import_preview import ImportCommandError
from .olivine_formula import OLIVINE, oxygen_normalized_formula


def _component(species, atomic_weight, cations, oxygens):
    return {"species": species, "atomic_weight": atomic_weight, "cations": cations, "oxygens": oxygens,
            "molar_mass": cations * atomic_weight + oxygens * OLIVINE["oxygen_atomic_weight"]}


_COMPONENTS = {
    **OLIVINE["components"],
    "BaO": _component("Ba", 137.327, 1, 1),
    "SrO": _component("Sr", 87.62, 1, 1),
    "ZrO2": _component("Zr", 91.224, 1, 2),
    "HfO2": _component("Hf", 178.49, 1, 2),
    "ThO2": _component("Th", 232.04, 1, 2),
    "UO2": _component("U", 238.03, 1, 2),
    "Y2O3": _component("Y", 88.906, 2, 3),
    "P2O5": _component("P", 30.974, 2, 5),
    "SO3": _component("S", 32.06, 1, 3),
    "PbO": _component("Pb", 207.2, 1, 1),
    "ZnO": _component("Zn", 65.38, 1, 1),
    "V2O3": _component("V3+", 50.942, 2, 3),
}


def _definition(method_id, name, oxygen_basis, positive_components, optional, cation_range, references, benchmark,
                end_member_rules=None, positive_groups=(), indices=None):
    return {
        "method_id": method_id, "name": name, "version": "1.0.0",
        "input_unit": "wt.%", "oxygen_basis": oxygen_basis, "cation_basis": None,
        "required_components": positive_components,
        "positive_groups": [list(group) for group in positive_groups],
        "components": {oxide: _COMPONENTS[oxide] for oxide in (*positive_components, *optional.split())},
        "oxygen_atomic_weight": OLIVINE["oxygen_atomic_weight"],
        "iron_policy": OLIVINE["iron_policy"],
        "missing_policy": "Required oxides must be positive; unselected optional oxides are unmodelled; censored inputs are rejected.",
        "oh_basis": OLIVINE["oh_basis"],
        "end_member_rules": end_member_rules or {},
        "index_rules": indices or {},
        "applicability_checks": {"oxide_sum_wt_pct": [95, 105], "cation_sum_apfu": cation_range},
        "references": [*references, "https://ciaaw.org/abridged-atomic-weights.htm"],
        "independent_benchmarks": [benchmark],
    }


FELDSPAR = _definition(
    "formula.feldspar.8o", "Полевой шпат на 8 атомов кислорода", 8, ["SiO2", "Al2O3"],
    "CaO Na2O K2O BaO SrO FeO Fe2O3 MgO TiO2 Cr2O3 MnO", [4.8, 5.2],
    ["https://doi.org/10.1180/mgm.2022.113", "https://doi.org/10.1029/2019JE005998"],
    "Kim et al. (2019), Table 1, grain 1, crystalline plagioclase",
    {"fractions": {"An": "Ca", "Ab": "Na", "Or": "K"}, "celsian": "100 Ba / (Ca + Na + K + Ba)"},
    positive_groups=(("CaO", "Na2O", "K2O", "BaO"),),
)
_MG_NUMBER = ("Mg", ["Mg", "Fe2+"])
_IRON_FRACTION = ("Fe3+", ["Fe2+", "Fe3+"])
PYROXENE = _definition(
    "formula.pyroxene.6o", "Пироксен на 6 атомов кислорода (исходная форма Fe)", 6, ["SiO2"],
    "CaO MgO FeO Fe2O3 Na2O Al2O3 TiO2 Cr2O3 MnO NiO K2O", [3.8, 4.2],
    ["https://doi.org/10.1180/minmag.1988.052.367.15", "https://academic.oup.com/view-large/392420083"],
    "Published Table 6, E17–016 orthopyroxene and E16–085 clinopyroxene",
    {"fractions": {"Wo": "Ca", "En": "Mg", "Fs": "Fe2+"},
     "quadrilateral": "Q = Ca + Mg + Fe2+; J = 2 Na; Mg# = Mg / (Mg + Fe2+)",
     "basis": "PetroLab v1 Ca–Mg–Fe2+ proportions; no site allocation or species naming"},
    positive_groups=(("CaO", "MgO", "FeO", "Na2O", "MnO"),),
    indices={"Mg#": list(_MG_NUMBER), "Fe3+/ΣFe": list(_IRON_FRACTION)},
)
ZIRCON = _definition(
    "formula.zircon.4o", "Циркон на 4 атома кислорода", 4, ["SiO2", "ZrO2"],
    "HfO2 ThO2 UO2 Y2O3 P2O5 SO3 PbO SrO CaO TiO2 FeO Fe2O3 Cr2O3 MnO MgO NiO Al2O3", [1.9, 2.1],
    ["https://doi.org/10.3390/min10110947"],
    "Zaman and Antao (2020), Table 1, sample 1:CB",
)
SPINEL = _definition(
    "formula.spinel.4o", "Шпинель на 4 атома кислорода (исходная форма Fe)", 4, [],
    "SiO2 TiO2 Al2O3 Cr2O3 FeO Fe2O3 MnO MgO NiO CaO Na2O K2O ZnO V2O3", [2.85, 3.15],
    ["https://www-odp.tamu.edu/publications/163X_IR/VOLUME/CHAPTERS/103.PDF"],
    "ODP Leg 163X, Table AT5, SEG40A-1-2 (Piece 1, 10–14), first analysis",
    positive_groups=(("FeO", "MgO", "MnO", "ZnO", "NiO"), ("Al2O3", "Cr2O3", "Fe2O3", "TiO2")),
    indices={"Cr#": ["Cr", ["Cr", "Al"]], "XFe3_B": ["Fe3+", ["Cr", "Al", "Fe3+"]], "Mg#": list(_MG_NUMBER)},
)
ILMENITE = _definition(
    "formula.ilmenite.3o", "Ильменитовый ряд на 3 атома кислорода (исходная форма Fe)", 3, ["TiO2"],
    "SiO2 Al2O3 Cr2O3 V2O3 FeO Fe2O3 MgO NiO MnO ZnO CaO", [1.9, 2.1],
    ["https://doi.org/10.1029/2007JB004973"],
    "McEnroe et al. (2007), Table 2, ilmenite AL36b, 138a, separately reported FeO and Fe2O3",
    positive_groups=(("FeO", "Fe2O3", "MgO", "MnO"),),
    indices={"Fe3+/ΣFe": list(_IRON_FRACTION)},
)


def calculate_mineral_formula(values, method):
    required = set(method["required_components"])
    if not required <= values.keys() or values.keys() - method["components"].keys():
        raise ImportCommandError("FORMULA_UNSUPPORTED_COMPONENTS",
                                 "Обязательные оксиды: " + ", ".join(method["required_components"]) + ".")
    if (any(type(value) not in (int, float) or not 0 <= value <= 100 for value in values.values())
            or any(values[oxide] <= 0 for oxide in required)):
        raise ImportCommandError("FORMULA_INVALID_MEASUREMENT",
                                 "Нужны массовые доли от 0 до 100 wt.% и положительные значения обязательных оксидов.")
    for alternatives in method["positive_groups"]:
        if not any(values.get(oxide, 0) > 0 for oxide in alternatives):
            raise ImportCommandError("FORMULA_UNSUPPORTED_COMPONENTS",
                                     "Нужен хотя бы один положительный компонент: " + ", ".join(alternatives) + ".")
    result = oxygen_normalized_formula(values, method)
    apfu = result["apfu"]
    rules = method["end_member_rules"]
    if "fractions" in rules:
        species = rules["fractions"]
        missing = sorted(set(species.values()) - apfu.keys())
        denominator = math.fsum(apfu[element] for element in species.values()) if not missing else 0
        fractions = {name: 100 * apfu[element] / denominator for name, element in species.items()} if denominator else {}
        if not fractions:
            result["warnings"].append({"kind": "components_unavailable", "field": "end_member_mol_percent",
                                       "missing_species": missing})
        if not missing and "celsian" in rules and "Ba" in apfu and (alkalis_with_ba := denominator + apfu["Ba"]):
            fractions["Cn"] = 100 * apfu["Ba"] / alkalis_with_ba
        result["end_member_mol_percent"] = fractions
    if "quadrilateral" in rules:
        result["quadrilateral_apfu"] = {}
        if "Na" in apfu:
            result["quadrilateral_apfu"]["J"] = 2 * apfu["Na"]
        if denominator:
            result["quadrilateral_apfu"]["Q"] = denominator
    if method["index_rules"]:
        result["indices"] = {}
        for index, (numerator, terms) in method["index_rules"].items():
            if set(terms) <= apfu.keys() and (total := math.fsum(apfu[element] for element in terms)):
                result["indices"][index] = apfu[numerator] / total
    return result
