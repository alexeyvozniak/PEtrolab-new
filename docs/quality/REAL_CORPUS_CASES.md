# Real import corpus cases

Machine-readable source: `fixtures/import/real-corpus.registry.json`.

The v1 corpus deliberately mixes genuinely different workbook families: wide mica/literature data, two real 2023 instrument exports, a dedicated phlogopite workbook, Turiy Mys mica data, the Kola dyke dataset, and three LA-ICP-MS workbooks from 2026. This diversity is intentional: passing one tidy table is not enough to declare PetroLab import stable.

Every case is required at milestone time. A missing case is a failed gate, not a skipped test.
