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
    "SnO2": _component("Sn", 118.71, 1, 2),
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
    "F": {**_component("F", 18.998, 1, 0), "kind": "anion"},
    "Cl": {**_component("Cl", 35.45, 1, 0), "kind": "anion"},
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
NEPHELINE = _definition(
    "formula.nepheline.32o", "Нефелин по Henderson на 32 атома кислорода", 32,
    ["SiO2", "Al2O3", "Na2O"], "K2O CaO TiO2 FeO Fe2O3 MgO MnO Cr2O3", [21.3, 24],
    ["https://doi.org/10.1180/mgm.2020.78"], "Henderson (2020), Table 4, Barth sample 1, recalculated column 2",
    {"nepheline": {"framework_sites": 16, "cavity_sites": 8,
                   "framework_cations": ["Si", "Ti", "Al", "Fe3+"],
                   "cavity_cations": ["Na", "K", "Ca"],
                   "charge_difference_max": 0.25, "near_zero_charge": 0.02,
                   "framework_sum_range": [15.9, 16.1], "delta_ratio_range": [1.0, 1.2]},
     "basis": "Table 2 equations 3–6 and 14, before Na excess correction; selected oxides only"},
)
APATITE = {
    **_definition(
        "formula.apatite.25oeq", "Апатит по Ketcham на 25 кислородных эквивалентов", 25,
        ["CaO", "P2O5"], "SiO2 Al2O3 FeO Fe2O3 MgO MnO Na2O K2O SrO BaO La2O3 Ce2O3 Nd2O3 Y2O3 SO3 F Cl",
        [15.6, 16.4],
        ["https://doi.org/10.2138/am-2015-5171", "https://doi.org/10.1007/s00410-024-02147-8"],
        "Li et al. (2024), volatile precision example",
        {"apatite_x_site_capacity": 2},
    ),
    "oh_basis": "Closure estimate OH = 2 - F - Cl on 25 oxygen equivalents. Requires selected quantitative F and Cl; "
                "assumes a full X site occupied only by these three anions. Other channel anions are outside this model.",
}
_TITANITE_M_CATIONS = ["Ti", "Al", "Fe3+", "Mg", "Mn", "Cr", "Sn"]
TITANITE = {
    **_definition(
        "formula.titanite.2cat", "Титанит на 2 катиона T + M", None, ["CaO", "SiO2", "TiO2"],
        "Al2O3 FeO Fe2O3 MgO MnO Cr2O3 SnO2 F", [2.7, 3.3],
        ["https://doi.org/10.2478/mipo-2022-0005", "https://doi.org/10.1007/s00710-019-00675-x"],
        "Ordosch et al. (2019), Table 4, P40 and P43, published APFU rescaled to T + M = 2",
        {"titanite_M_cations": _TITANITE_M_CATIONS,
         "basis": "T + M normalization of measured components; selected Al is assigned to M in this model"},
    ),
    "cation_basis": 2,
    "cation_basis_species": ["Si", *_TITANITE_M_CATIONS],
    "oh_basis": "Conditional estimate OH = Al + Fe3+ - F for the coupled substitution; requires explicit quantitative "
                "Al2O3, Fe2O3 and F. Assumes the selected Al and Fe3+ occupy the M site. No redox or water measurement.",
}
_SCHNEIDERMAN_TRACY = "https://msaweb.org/AmMin/AM76/AM76_942.pdf"


def _mica_definition(basis):
    scale = basis // 11
    return {
        **_definition(
            f"formula.mica.{basis}oeq", f"Слюда на {basis} кислородных эквивалентов", basis,
            ["SiO2", "Al2O3"], "TiO2 Cr2O3 FeO Fe2O3 MnO MgO CaO Na2O K2O BaO F Cl",
            [6.6 * scale, 8.3 * scale],
            ["https://doi.org/10.5194/ejm-36-657-2024", _SCHNEIDERMAN_TRACY],
            "Schneiderman and Tracy (1991), Table 3, OR-8A; 22 O equivalents double the 11-O values",
            {"mica_sites": {"tetrahedral": 4 * scale, "anion": 2 * scale}},
            positive_groups=(("K2O", "Na2O", "CaO", "BaO"),),
            indices={"Mg#": list(_MG_NUMBER)},
        ),
        "oh_basis": "Conditional maximum OH = anion site capacity - F - Cl. Requires quantitative F and Cl; "
                    "other occupants can lower OH. This is not a water measurement.",
    }


MICA_11 = _mica_definition(11)
MICA_22 = _mica_definition(22)
AMPHIBOLE = _definition(
    "formula.amphibole.23oeq", "Амфибол на 23 кислородных эквивалента", 23,
    ["SiO2"], "TiO2 Al2O3 Cr2O3 FeO Fe2O3 MnO MgO CaO Na2O K2O F Cl", [14.5, 16.3],
    ["https://doi.org/10.2138/am.2012.4276", _SCHNEIDERMAN_TRACY],
    "Schneiderman and Tracy (1991), Table 2, OR-8A A",
    {"basis": "Anhydrous 23-oxygen-equivalent cation normalization; no species naming or site assignment"},
    positive_groups=(("FeO", "MgO", "MnO", "Na2O", "CaO"),),
    indices={"Mg#": list(_MG_NUMBER), "Fe3+/ΣFe": list(_IRON_FRACTION)},
)


def _mica_sites(result, sites):
    apfu = result["apfu"]
    tetrahedral_deficit = sites["tetrahedral"] - apfu["Si"]
    al_iv = min(apfu["Al"], max(0, tetrahedral_deficit))
    result["site_sum_apfu"] = {"Al_IV": al_iv, "Al_VI": apfu["Al"] - al_iv}
    if not 0 <= tetrahedral_deficit <= apfu["Al"]:
        result["warnings"].append({"kind": "outside_model_check", "field": "mica_tetrahedral_site"})
    missing = sorted({"F", "Cl"} - apfu.keys())
    if missing:
        result["warnings"].append({"kind": "components_unavailable", "field": "mica_OH_upper_bound",
                                   "missing_species": missing})
        return
    residual = sites["anion"] - math.fsum(apfu[species] for species in ("F", "Cl"))
    result["anion_balance_apfu"] = {"W_site_residual": residual}
    if residual < 0:
        result["warnings"].append({"kind": "outside_model_check", "field": "mica_W_site"})
    else:
        result["estimated_anions_apfu"] = {"OH_upper_bound": residual}


def _titanite_result(result, octahedral_cations):
    apfu = result["apfu"]
    octahedral_sum = math.fsum(apfu[species] for species in octahedral_cations if species in apfu)
    result["site_sum_apfu"] = {"T_plus_M": apfu["Si"] + octahedral_sum, "M": octahedral_sum}
    if octahedral_sum:
        result["indices"] = {"X_titanite_proxy": apfu["Ti"] / octahedral_sum}
    missing = sorted({"Al", "Fe3+", "F"} - apfu.keys())
    if missing:
        result["warnings"].append({"kind": "components_unavailable", "field": "titanite_OH_estimate",
                                   "missing_species": missing})
        return result
    residual = apfu["Al"] + apfu["Fe3+"] - apfu["F"]
    result["anion_balance_apfu"] = {"OH_residual": residual}
    if residual < 0 or apfu["F"] + residual > 1:
        result["warnings"].append({"kind": "outside_model_check", "field": "titanite_OH_estimate"})
        return result
    result["estimated_anions_apfu"] = {"OH": residual}
    return result


def _apatite_result(result, capacity):
    apfu = result["apfu"]
    missing = sorted({"F", "Cl"} - apfu.keys())
    if missing:
        result["warnings"].append({"kind": "components_unavailable", "field": "apatite_OH_estimate",
                                   "missing_species": missing})
        return result
    residual = capacity - math.fsum(apfu[key] for key in ("F", "Cl"))
    result["anion_balance_apfu"] = {"X_site_residual": residual}
    if residual < 0:
        result["warnings"].append({"kind": "outside_model_check", "field": "apatite_X_site",
                                   "value": capacity - residual, "range": [0, capacity]})
        return result
    result["estimated_anions_apfu"] = {"OH": residual}
    result["indices"] = {"X_F": apfu["F"] / capacity, "X_Cl": apfu["Cl"] / capacity, "X_OH": residual / capacity}
    return result


def _nepheline_result(result, rules):
    apfu = result["apfu"]
    framework = rules["framework_cations"]
    cavity = rules["cavity_cations"]
    measured_framework = {cation: apfu[cation] for cation in framework if cation in apfu}
    framework_sum = math.fsum(measured_framework.values())
    if not framework_sum:
        raise ImportCommandError("FORMULA_INVALID_MEASUREMENT", "Сумма катионов каркаса ниже числовой точности.")
    framework_charge = math.fsum(value * (4 if cation in {"Si", "Ti"} else 3)
                                for cation, value in measured_framework.items())
    trivalent = math.fsum(apfu[cation] for cation in ("Al", "Fe3+") if cation in apfu)
    delta_t = (framework_charge / framework_sum) * (rules["framework_sites"] - framework_sum)
    site_sums = {"framework_sum": framework_sum}
    charge = {"delta_T_charge": delta_t}
    indices = {"Si_Al": apfu["Si"] / trivalent} if trivalent else {}
    sites = rules["cavity_sites"]
    fractions = {"Ne": 100 * apfu["Na"] / sites}
    if "K" in apfu:
        fractions["Ks"] = 100 * apfu["K"] / sites
    if "Ca" in apfu:
        fractions["CaNe"] = 200 * apfu["Ca"] / sites
    if {"Mg", "Fe2+", "Mn"} <= apfu.keys():
        fractions["KsM"] = 200 * math.fsum(apfu[cation] for cation in ("Mg", "Fe2+", "Mn")) / sites

    missing = sorted(set(cavity) - apfu.keys())
    if missing:
        result["warnings"].append({"kind": "components_unavailable", "field": "nepheline_cavity",
                                   "missing_species": missing})
    else:
        cavity_charge = apfu["Na"] + apfu["K"] + 2 * apfu["Ca"]
        delta_al = trivalent - cavity_charge
        charge.update(cavity_charge=cavity_charge, delta_Al_cc=delta_al)
        site_sums["cavity_vacancy_proxy"] = sites - math.fsum(apfu[cation] for cation in cavity)
        fractions["Qxs"] = 100 * (sites - cavity_charge) / sites
        if delta_t:
            indices["delta_ratio"] = delta_al / delta_t
        near_zero = max(abs(delta_al), abs(delta_t)) < rules["near_zero_charge"]
        ratio = abs(indices.get("delta_ratio", 0))
        if (not rules["framework_sum_range"][0] <= framework_sum <= rules["framework_sum_range"][1]
                or max(abs(delta_al), abs(delta_t)) > rules["charge_difference_max"]
                or not (near_zero or rules["delta_ratio_range"][0] <= ratio <= rules["delta_ratio_range"][1])):
            result["warnings"].append({"kind": "outside_model_check", "field": "nepheline_stoichiometry"})
    return {**result, "site_sum_apfu": site_sums, "charge_per_formula": charge,
            "indices": indices, "end_member_mol_percent": fractions}


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
    if "nepheline" in rules:
        return _nepheline_result(result, rules["nepheline"])
    if "apatite_x_site_capacity" in rules:
        return _apatite_result(result, rules["apatite_x_site_capacity"])
    if "titanite_M_cations" in rules:
        return _titanite_result(result, rules["titanite_M_cations"])
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
    if "mica_sites" in rules:
        _mica_sites(result, rules["mica_sites"])
    if "site_proxies" in rules:
        sums = {site: math.fsum(apfu[key] for key in species if key in apfu)
                for site, species in rules["site_proxies"].items()}
        result["site_sum_apfu"] = sums
        if sums["B"]:
            result["indices"] = {"Ti_B_fraction_proxy": apfu["Ti"] / sums["B"]}
    if "cation_fractions" in rules:
        result["cation_fraction"] = {key: value / method["cation_basis"] for key, value in apfu.items()}
    return result
