import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from petrolab.desktop_workflow import list_project_analyses, suggest_import_recipe
from petrolab.import_apply import apply_import_plan
from petrolab.import_preview import ImportCommandError
from petrolab.mineral_formulae import (
    APATITE, CARBONATE_1CAT, CARBONATE_2CAT, FELDSPAR, GARNET, ILMENITE, NEPHELINE, PEROVSKITE, PYROXENE, SPINEL, ZIRCON,
    calculate_mineral_formula,
)
from petrolab.ndjson_service import handle_request


class MineralFormulaTests(unittest.TestCase):
    def test_published_feldspar_and_zircon_apfu(self):
        # Kim et al. (2019), Table 1, grain 1, crystalline plagioclase.
        feldspar = calculate_mineral_formula(
            dict(SiO2=44.82, Al2O3=34.55, Na2O=0.67, CaO=18.63, K2O=0.05, FeO=0.30,
                 MgO=0.04, TiO2=0.02, Cr2O3=0, MnO=0.03), FELDSPAR)
        for key, expected in dict(Si=2.088, Al=1.897, Ca=0.930, Na=0.060, K=0.003).items():
            self.assertAlmostEqual(feldspar["apfu"][key], expected, delta=0.002)
        self.assertAlmostEqual(feldspar["end_member_mol_percent"]["An"], 93.66, delta=0.1)

        # Zaman and Antao (2020), Table 1, 1:CB. Unquantified oxides are omitted.
        zircon = calculate_mineral_formula(
            dict(SiO2=32.67, ZrO2=65.74, HfO2=1.11, UO2=0.02, ThO2=0.01, CaO=0.02,
                 Y2O3=0.10, Cr2O3=0.01, MnO=0.01, SO3=0.03), ZIRCON)
        for key, expected in dict(Si=1.003, Zr=0.984, Hf=0.010).items():
            self.assertAlmostEqual(zircon["apfu"][key], expected, delta=0.002)

    def test_published_pyroxenes_and_explicit_iron(self):
        # Journal of Petrology, Table 6, E17–016 Opx and E16–085 Cpx.
        cases = [
            ([52.43, 0.21, 9.10, 0.65, 6.73, 30.39, 1.19, 0.06, 0], (1.80, 1.56, 0.04), (2.45, 86.76, 10.79)),
            ([50.00, 0.48, 8.39, 0.62, 5.78, 19.00, 14.79, 0.20, 0.02], (1.81, 1.03, 0.57), (32.34, 57.79, 9.87)),
        ]
        oxides = ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "MgO", "CaO", "Na2O", "K2O")
        for values, apfu, components in cases:
            with self.subTest(values=values):
                result = calculate_mineral_formula(dict(zip(oxides, values)), PYROXENE)
                for field, expected in zip(("Si", "Mg", "Ca"), apfu):
                    self.assertAlmostEqual(result["apfu"][field], expected, delta=0.01)
                for field, expected in zip(("Wo", "En", "Fs"), components):
                    self.assertAlmostEqual(result["end_member_mol_percent"][field], expected, delta=0.12)
                self.assertNotIn("Fe3+/ΣFe", result["indices"])
        measured_iron = calculate_mineral_formula(dict(SiO2=53, FeO=8, Fe2O3=4, MgO=23, CaO=10), PYROXENE)
        self.assertGreater(measured_iron["apfu"]["Fe3+"], 0)
        self.assertAlmostEqual(measured_iron["indices"]["Fe3+/ΣFe"], 0.3103, delta=0.0002)
        with self.assertRaises(ImportCommandError):
            calculate_mineral_formula(dict(SiO2=53, FeOt=8, MgO=23, CaO=10), PYROXENE)

    def test_end_members_do_not_replace_missing_values_with_zero(self):
        with self.assertRaises(ImportCommandError):
            calculate_mineral_formula(dict(SiO2=33), ZIRCON)
        with self.assertRaises(ImportCommandError):
            calculate_mineral_formula(dict(SiO2=62, Al2O3=20), FELDSPAR)
        incomplete = calculate_mineral_formula(dict(SiO2=68, Al2O3=20, Na2O=12), FELDSPAR)
        self.assertNotIn("Ca", incomplete["apfu"])
        self.assertEqual(incomplete["end_member_mol_percent"], {})
        warning = next(item for item in incomplete["warnings"] if item["kind"] == "components_unavailable")
        self.assertEqual(warning["missing_species"], ["Ca", "K"])
        albite = calculate_mineral_formula(dict(SiO2=68.74, Al2O3=19.44, Na2O=11.82, CaO=0, K2O=0), FELDSPAR)
        self.assertAlmostEqual(albite["apfu"]["Si"], 3, delta=0.002)
        self.assertEqual(albite["end_member_mol_percent"], {"An": 0, "Ab": 100, "Or": 0})

    def test_published_spinel_indices_and_ilmenite_apfu(self):
        # ODP Leg 163X, Table AT5, SEG40A-1-2, first analysis.
        spinel = calculate_mineral_formula(
            dict(SiO2=0, TiO2=1.24, Al2O3=13.66, Fe2O3=15.33, FeO=19.86, MnO=0.32,
                 MgO=9.73, CaO=0.01, Cr2O3=40.03, NiO=0.15), SPINEL)
        self.assertAlmostEqual(spinel["indices"]["XFe3_B"], 0.195, delta=0.002)
        self.assertAlmostEqual(spinel["indices"]["Cr#"], 0.6625, delta=0.002)
        self.assertAlmostEqual(spinel["cation_sum_apfu"], 3, delta=0.003)
        ideal = calculate_mineral_formula(dict(MgO=28.33, Al2O3=71.67), SPINEL)
        self.assertAlmostEqual(ideal["apfu"]["Al"], 2, delta=0.001)
        self.assertNotIn("Cr#", ideal["indices"])
        with self.assertRaises(ImportCommandError):
            calculate_mineral_formula(dict(Al2O3=100), SPINEL)

        # McEnroe et al. (2007), Table 2, AL36b 138a, reported split Fe oxides.
        ilmenite = calculate_mineral_formula(
            dict(SiO2=0.012, TiO2=53.400, Al2O3=0.005, Cr2O3=0.048, V2O3=0.233, Fe2O3=2.062,
                 MgO=3.859, NiO=0.040, FeO=40.834, MnO=0.278, ZnO=0, CaO=0), ILMENITE)
        for key, expected in {"Ti": 0.9780, "Fe2+": 0.8317, "Fe3+": 0.0378}.items():
            self.assertAlmostEqual(ilmenite["apfu"][key], expected, delta=0.0003)
        self.assertAlmostEqual(ilmenite["indices"]["Fe3+/ΣFe"], 0.0435, delta=0.0003)
        ideal = calculate_mineral_formula(dict(TiO2=52.64, FeO=47.36), ILMENITE)
        self.assertAlmostEqual(ideal["apfu"]["Ti"], 1, delta=0.001)
        self.assertNotIn("Fe3+/ΣFe", ideal["indices"])

    def test_published_perovskite_and_dolomite(self):
        # Gravina et al. (2008), Tapira EPMA composition, section S1.
        perovskite = calculate_mineral_formula(
            dict(CaO=38.9, TiO2=56.6, Na2O=0.224, Fe2O3=1.2, Ce2O3=1.4), PEROVSKITE)
        for species, expected, tolerance in (("Ca", 0.96, 0.02), ("Ti", 0.98, 0.01), ("Fe3+", 0.022, 0.002),
                                             ("Na", 0.01, 0.001), ("Ce", 0.011, 0.002)):
            self.assertAlmostEqual(perovskite["apfu"][species], expected, delta=tolerance)
        self.assertAlmostEqual(perovskite["site_sum_apfu"]["B"], 1, delta=0.01)
        ideal = calculate_mineral_formula(dict(CaO=41.25, TiO2=58.75), PEROVSKITE)
        self.assertAlmostEqual(ideal["site_sum_apfu"]["A"], 1, delta=0.001)
        with self.assertRaises(ImportCommandError):
            calculate_mineral_formula(dict(CaO=40), PEROVSKITE)

        # Adami et al. (2025), Table 3 EPMA, with total iron represented as FeO-equivalent.
        values = dict(CaO=27.48, MgO=20.66, FeOt=3.45, MnO=0.10, Na2O=0.39, SrO=0.05, BaO=0.04,
                      NiO=0.03, Cr2O3=0.18, V2O3=0.06)
        dolomite = calculate_mineral_formula(values, CARBONATE_2CAT)
        for species, expected in (("Ca", 0.92), ("Mg", 0.97), ("Fe_total", 0.09)):
            self.assertAlmostEqual(dolomite["apfu"][species], expected, delta=0.015)
        self.assertNotIn("Fe2+", dolomite["apfu"])
        self.assertNotIn("Fe3+", dolomite["apfu"])
        self.assertEqual(dolomite["warnings"], [])
        self.assertAlmostEqual(dolomite["cation_sum_apfu"], 2)
        calcite = calculate_mineral_formula(dict(CaO=56.03), CARBONATE_1CAT)
        self.assertEqual(calcite["cation_fraction"], {"Ca": 1})
        with self.assertRaises(ImportCommandError) as error:
            calculate_mineral_formula({**values, "FeO": 0}, CARBONATE_2CAT)
        self.assertEqual(error.exception.code, "FORMULA_UNRESOLVED_IRON")

    def test_published_garnet_and_calcium_partition(self):
        # Yin et al. (2024), Table 1, Grt 1. The paper reports the Ca pool as Grs.
        grt1 = dict(K2O=0.02, CaO=0.52, FeO=2.93, MnO=41.51, TiO2=0.04, Cr2O3=0,
                    Na2O=0.03, MgO=0.02, Al2O3=21.16, SiO2=33.77)
        result = calculate_mineral_formula(grt1, GARNET)
        fractions = result["end_member_mol_percent"]
        for field, expected in dict(Sps=92.05, Alm=6.42, Ca_pool=1.45, Prp=0.09).items():
            self.assertAlmostEqual(fractions[field], expected, delta=0.08)
        self.assertNotIn("Grs", fractions)
        self.assertTrue(any(warning.get("missing_species") == ["Fe3+"] for warning in result["warnings"]))
        grt2 = dict(K2O=0.04, CaO=0.70, FeO=12.86, MnO=29.44, TiO2=0.12, Cr2O3=0.02,
                    Na2O=0.07, MgO=0.07, Al2O3=20.15, SiO2=35.51)
        second = calculate_mineral_formula(grt2, GARNET)["end_member_mol_percent"]
        for field, expected in dict(Sps=68.24, Alm=29.43, Ca_pool=2.06, Prp=0.27).items():
            self.assertAlmostEqual(second[field], expected, delta=0.08)
        explicit_valences = calculate_mineral_formula({**grt1, "Fe2O3": 0}, GARNET)["end_member_mol_percent"]
        self.assertEqual(explicit_valences["Grs"], fractions["Ca_pool"])
        self.assertEqual(explicit_valences["Adr"], 0)
        self.assertAlmostEqual(sum(explicit_valences.values()), 100)
        grossular = calculate_mineral_formula(
            dict(SiO2=40.01, Al2O3=22.63, CaO=37.36, MgO=0, FeO=0, MnO=0, Fe2O3=0, Cr2O3=0), GARNET)
        self.assertAlmostEqual(grossular["apfu"]["Ca"], 3, delta=0.002)
        self.assertEqual(grossular["end_member_mol_percent"]["Grs"], 100)
        with self.assertRaises(ImportCommandError):
            calculate_mineral_formula(dict(SiO2=60, MgO=40), GARNET)

    def test_nepheline_reference_and_missing_cavity_components(self):
        # Henderson (2020), Table 4 column 2, Barth sample recalculation.
        values = dict(SiO2=42.85, Al2O3=33.36, Fe2O3=0.10, CaO=1.42, Na2O=15.00, K2O=5.81)
        result = calculate_mineral_formula(values, NEPHELINE)
        for field, expected in dict(Si=8.333, Al=7.646, Na=5.655, K=1.441, Ca=0.296).items():
            self.assertAlmostEqual(result["apfu"][field], expected, delta=0.005)
        fractions = result["end_member_mol_percent"]
        for field, expected in dict(Ne=70.69, Ks=18.02, CaNe=7.40, Qxs=3.89).items():
            self.assertAlmostEqual(fractions[field], expected, delta=0.08)
        self.assertAlmostEqual(result["charge_per_formula"]["delta_Al_cc"], -0.028, delta=0.005)
        ideal = calculate_mineral_formula(dict(SiO2=42.30, Al2O3=35.89, Na2O=21.81, K2O=0, CaO=0), NEPHELINE)
        self.assertAlmostEqual(ideal["site_sum_apfu"]["framework_sum"], 16, delta=0.003)
        self.assertAlmostEqual(ideal["end_member_mol_percent"]["Ne"], 100, delta=0.03)
        incomplete = calculate_mineral_formula({key: value for key, value in values.items() if key != "K2O"}, NEPHELINE)
        self.assertNotIn("Qxs", incomplete["end_member_mol_percent"])
        self.assertIn({"kind": "components_unavailable", "field": "nepheline_cavity", "missing_species": ["K"]},
                      incomplete["warnings"])
        enriched = calculate_mineral_formula({**values, "Na2O": 24}, NEPHELINE)
        self.assertLess(enriched["end_member_mol_percent"]["Qxs"], 0)
        self.assertIn({"kind": "outside_model_check", "field": "nepheline_stoichiometry"}, enriched["warnings"])

    def test_apatite_reference_and_x_site_balance(self):
        # Li et al. (2024), microprobe precision example; the four reported major components.
        values = dict(CaO=54.48, P2O5=41.37, F=2.133, Cl=1.016)
        result = calculate_mineral_formula(values, APATITE)
        for field, expected in dict(X_F=0.572, X_Cl=0.146, X_OH=0.281).items():
            self.assertAlmostEqual(result["indices"][field], expected, delta=0.015)
        self.assertAlmostEqual(result["estimated_anions_apfu"]["OH"], 0.562, delta=0.03)
        self.assertAlmostEqual(result["cation_sum_apfu"], result["apfu"]["Ca"] + result["apfu"]["P"])
        ideal = calculate_mineral_formula(dict(CaO=55.82, P2O5=42.39, F=0, Cl=0), APATITE)
        self.assertAlmostEqual(ideal["apfu"]["Ca"], 10, delta=0.002)
        self.assertEqual(ideal["estimated_anions_apfu"], {"OH": 2})
        incomplete = calculate_mineral_formula(dict(CaO=54.48, P2O5=41.37, F=2.133), APATITE)
        self.assertNotIn("estimated_anions_apfu", incomplete)
        self.assertIn({"kind": "components_unavailable", "field": "apatite_OH_estimate", "missing_species": ["Cl"]},
                      incomplete["warnings"])
        overloaded = calculate_mineral_formula({**values, "F": 6}, APATITE)
        self.assertLess(overloaded["anion_balance_apfu"]["X_site_residual"], 0)
        self.assertNotIn("estimated_anions_apfu", overloaded)
        self.assertTrue(any(warning["field"] == "apatite_X_site" for warning in overloaded["warnings"]))

    def test_all_methods_round_trip_through_the_versioned_service(self):
        with TemporaryDirectory() as folder:
            source, database = Path(folder) / "epma.csv", Path(folder) / "project.sqlite"
            with source.open("w", newline="", encoding="utf-8") as stream:
                output = csv.writer(stream)
                output.writerow(["Analysis", "SiO2 (wt.%)", "Al2O3 (wt.%)", "CaO (wt.%)", "Na2O (wt.%)",
                                 "K2O (wt.%)", "MgO (wt.%)", "FeO (wt.%)", "ZrO2 (wt.%)", "HfO2 (wt.%)",
                                 "TiO2 (wt.%)", "FeOt (wt.%)", "MnO (wt.%)", "P2O5 (wt.%)", "F (wt.%)", "Cl (wt.%)"])
                output.writerow(["F1", 44.82, 34.55, 18.63, 0.67, 0.05, "", "", "", ""])
                output.writerow(["P1", 50, 8.39, 14.79, 0.20, 0.02, 19, 5.78, "", ""])
                output.writerow(["Z1", 32.67, "", "", "", "", "", "", 65.74, "<0.01"])
                output.writerow(["S1", "", 71.67, "", "", "", 28.33, "", "", ""])
                output.writerow(["I1", "", "", "", "", "", "", 47.36, "", "", 52.64])
                output.writerow(["V1", "", "", 41.25, "", "", "", "", "", "", 58.75])
                output.writerow(["C1", "", "", 27.48, "", "", 20.66, "", "", "", "", 3.45])
                output.writerow(["G1", 33.77, 21.16, 0.52, "", "", 0.02, 2.93, "", "", "", "", 41.51])
                output.writerow(["N1", 42.85, 33.36, 1.42, 15, 5.81])
                output.writerow(["AP1", "", "", 54.48, "", "", "", "", "", "", "", "", "", 41.37, 2.133, 1.016])
                output.writerow(["AP2", "", "", 54.48, "", "", "", "", "", "", "", "", "", 41.37, 2.133, "<0.01"])
            original = source.read_bytes()
            apply_import_plan(database, source, suggest_import_recipe(source)["recipe"])
            baseline = list_project_analyses(database)["analyses"]

            def call(command, **parameters):
                return handle_request({"request_id": str(uuid4()), "protocol_version": "1.0", "command": command,
                                       "payload": {"project_database_path": str(database), **parameters}})

            rows = {row["identity"]["Analysis"]: row for row in baseline}
            choices = [
                ("F1", FELDSPAR, {"SiO2", "Al2O3", "CaO", "Na2O", "K2O"}, "end_member_mol_percent.An", "mol.%"),
                ("P1", PYROXENE, {"SiO2", "CaO", "MgO", "FeO"}, "indices.Mg#", "1"),
                ("Z1", ZIRCON, {"SiO2", "ZrO2"}, "apfu.Zr", "APFU"),
                ("S1", SPINEL, {"MgO", "Al2O3"}, "apfu.Al", "APFU"),
                ("I1", ILMENITE, {"FeO", "TiO2"}, "apfu.Ti", "APFU"),
                ("V1", PEROVSKITE, {"CaO", "TiO2"}, "site_sum_apfu.B", "APFU"),
                ("C1", CARBONATE_1CAT, {"CaO", "MgO"}, "cation_fraction.Ca", "1"),
                ("C1", CARBONATE_2CAT, {"CaO", "MgO", "FeOt"}, "apfu.Fe_total", "APFU"),
                ("G1", GARNET, {"SiO2", "Al2O3", "CaO", "MgO", "FeO", "MnO"}, "end_member_mol_percent.Sps", "mol.%"),
                ("N1", NEPHELINE, {"SiO2", "Al2O3", "CaO", "Na2O", "K2O"}, "charge_per_formula.delta_Al_cc", "e/f.u."),
                ("AP1", APATITE, {"CaO", "P2O5", "F", "Cl"}, "estimated_anions_apfu.OH", "APFU"),
            ]
            catalog = {method["method_id"]: method for method in call("formula.methods.list")["result"]}
            self.assertIn("formula.olivine.4o", catalog)
            for label, method, components, expected_field, expected_unit in choices:
                with self.subTest(label=label):
                    self.assertEqual(catalog[method["method_id"]], method)
                    row = rows[label]
                    measurements = {item["field"]: item["measurement_id"] for item in row["measurement_list"]}
                    fields = {"method_id": method["method_id"], "analysis_id": row["analysis_id"],
                              "measurement_ids": [measurements[field] for field in sorted(components)]}
                    if label == "Z1":
                        blocked = call("formula.review", **{**fields, "measurement_ids": [*fields["measurement_ids"],
                                                                                       measurements["HfO2"]]})
                        self.assertEqual(blocked["error"]["code"], "FORMULA_INVALID_MEASUREMENT")
                    review = call("formula.review", **fields)["result"]
                    fingerprints = {name: review[name] for name in ("input_fingerprint", "method_definition_fingerprint")}
                    run = call("formula.run", **fields, **fingerprints)["result"]
                    reopened = call("formula.run.open", run_id=run["id"])["result"]
                    self.assertEqual(reopened, run)
                    self.assertEqual(reopened["status"], "current")
                    derived = {item["field"]: item["unit"] for item in run["result_manifest"]["derived_values"]}
                    self.assertEqual(derived[expected_field], expected_unit)
            censored = rows["AP2"]
            blocked = call("formula.review", method_id=APATITE["method_id"], analysis_id=censored["analysis_id"],
                           measurement_ids=[item["measurement_id"] for item in censored["measurement_list"]
                                            if item["field"] in {"CaO", "P2O5", "F", "Cl"}])
            self.assertEqual(blocked["error"]["code"], "FORMULA_INVALID_MEASUREMENT")
            self.assertEqual(list_project_analyses(database)["analyses"], baseline)
            self.assertEqual(source.read_bytes(), original)
