"""Versioned oxide-normalized methods adapted from the PetroLab v1 formula registry."""

import math

from .import_preview import ImportCommandError
from .olivine_formula import OLIVINE, normalize_oxide_formula


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
    "Nb2O5": _component("Nb", 92.906, 2, 5),
    "Ta2O5": _component("Ta", 180.948, 2, 5),
    "La2O3": _component("La", 138.91, 2, 3),
    "Ce2O3": _component("Ce", 140.12, 2, 3),
    "Nd2O3": _component("Nd", 144.24, 2, 3),
    "FeOt": _component("Fe_total", 55.845, 1, 1),
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
PEROVSKITE = _definition(
    "formula.perovskite.3o", "Перовскит на 3 атома кислорода", 3, ["CaO", "TiO2"],
    "Na2O SrO BaO La2O3 Ce2O3 Nd2O3 Nb2O5 Ta2O5 FeO Fe2O3 Al2O3 Cr2O3 ZrO2 MgO MnO V2O3", [1.9, 2.1],
    ["https://pubs.geoscienceworld.org/minersoc/minmag/article/81/3/411/285322/Nomenclature-of-the-perovskite-supergroup-A",
     "https://doi.org/10.1107/S1600536808026421"],
    "Gravina et al. (2008), Tapira perovskite, S1 EPMA composition",
    {"site_proxies": {"A": ["Ca", "Na", "Sr", "Ba", "La", "Ce", "Nd"],
                      "B": ["Ti", "Nb", "Fe3+", "Al", "Cr", "Zr"]},
     "basis": "PetroLab v1 provisional sums over selected components; no site assignment or classification"},
)


def _carbonate_definition(basis, name):
    method = _definition(
        f"formula.carbonate.{basis}cat", name, None, [],
        "CaO MgO FeO Fe2O3 FeOt MnO SrO BaO ZnO NiO Na2O Cr2O3 V2O3", None,
        ["https://doi.org/10.5194/ejm-37-517-2025"], "Adami et al. (2025), Table 3, green dolomite",
        {"cation_fractions": "Cation proportion of selected quantified oxides"},
        positive_groups=(("CaO", "MgO", "FeO", "Fe2O3", "FeOt", "MnO", "SrO", "BaO", "ZnO"),),
    )
    return {**method, "cation_basis": basis, "applicability_checks": {},
            "iron_policy": "FeO as Fe2+, Fe2O3 as Fe3+, or FeOt as Fe_total without a redox assignment",
            "oh_basis": "Cation normalization only; CO2, OH and water are outside the calculation"}


CARBONATE_1CAT = _carbonate_definition(1, "Карбонаты кальцитового ряда на 1 катион")
CARBONATE_2CAT = _carbonate_definition(2, "Карбонаты доломитового ряда на 2 катиона")
GARNET = _definition(
    "formula.garnet.12o", "Гранат на 12 атомов кислорода (исходная форма Fe)", 12, ["SiO2"],
    "TiO2 Al2O3 Cr2O3 FeO Fe2O3 MnO MgO CaO Na2O K2O P2O5 Y2O3", [7.7, 8.3],
    ["https://doi.org/10.2138/am.2013.4201", "https://doi.org/10.1016/j.gsf.2023.101699"],
    "Yin et al. (2024), Table 1, Grt 1 and Grt 2",
    {"fractions": {"Prp": "Mg", "Alm": "Fe2+", "Sps": "Mn", "Ca_pool": "Ca"},
     "calcium_partition": {"Grs": "Al", "Adr": "Fe3+", "Uv": "Cr"},
     "basis": "PetroLab v1 X and Y stoichiometric proportions; no site refinement or species naming"},
    positive_groups=(("MgO", "FeO", "MnO", "CaO"), ("Al2O3", "Fe2O3", "Cr2O3")),
    indices={"Mg#": list(_MG_NUMBER)},
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
    if "FeOt" in values and {"FeO", "Fe2O3"} & values.keys():
        raise ImportCommandError("FORMULA_UNRESOLVED_IRON", "Выберите либо суммарное железо, либо раздельно заданные формы.")
    result = normalize_oxide_formula(values, method)
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
        if fractions and "calcium_partition" in rules:
            calcium = fractions["Ca_pool"]
            partition = rules["calcium_partition"]
            missing_y = sorted(set(partition.values()) - apfu.keys())
            total_y = math.fsum(apfu[element] for element in partition.values()) if not missing_y else 0
            if total_y or calcium == 0:
                del fractions["Ca_pool"]
                fractions.update({name: calcium * apfu[element] / total_y if total_y else 0
                                  for name, element in partition.items()})
            else:
                result["warnings"].append({"kind": "components_unavailable", "field": "calcium_partition",
                                           "missing_species": missing_y})
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
    if "site_proxies" in rules:
        sums = {site: math.fsum(apfu[key] for key in species if key in apfu)
                for site, species in rules["site_proxies"].items()}
        result["site_sum_apfu"] = sums
        if sums["B"]:
            result["indices"] = {"Ti_B_fraction_proxy": apfu["Ti"] / sums["B"]}
    if "cation_fractions" in rules:
        result["cation_fraction"] = {key: value / method["cation_basis"] for key, value in apfu.items()}
    return result
