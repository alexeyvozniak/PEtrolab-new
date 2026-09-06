"""Create isolated native-review workbooks. Never writes to the project DB."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from real_world_fixtures import write_xlsx

folder = Path(tempfile.mkdtemp(prefix='petrolab-native-review-'))
first = write_xlsx(folder / '01-tokens-and-iron.xlsx', {'Measurements': [
    ['Analysis', 'Fe (wt.%)', 'F (wt.%)'],
    ['QA-1', 10, '<DL'], ['QA-2', 11, 'n.d.'], ['QA-3', 12, '<0.01'],
    ['QA-4', 13, 'bdl'], ['QA-5', 14, None],
]})
second = write_xlsx(folder / '02-clean-table.xlsx', {'Measurements': [
    ['Analysis', 'SiO2 [wt.%]'], ['QA-B1', 40], ['QA-B2', 41],
]})
third = write_xlsx(folder / '03-mineral-review.xlsx', {'Measurements': [
    ['Analysis', 'Mineral', 'SiO2 (wt.%)', 'Al2O3 (wt.%)', 'MgO (wt.%)', 'CaO (wt.%)', 'Na2O (wt.%)', 'K2O (wt.%)', 'FeO (wt.%)'],
    ['QA-M1', 'olivine', 40, 0, 50, 0, 0, 0, 10],
    ['QA-M2', 'garnet', 40, 0, 50, 0, 0, 0, 10],
    ['QA-M3', None, 40, 0, 50, 0, 0, 0, 10],
]})
print(json.dumps({'folder': str(folder), 'files': [
    {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in [first, second, third]
]}, indent=2))
