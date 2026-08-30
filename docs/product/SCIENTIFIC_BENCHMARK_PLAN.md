# План независимых научных benchmark-тестов PetroLab Desktop v2

**Статус:** обязательный release gate для Scientific Core  
**Цель:** доказать перенос научного поведения независимо от кода Streamlit v1 и будущей production-реализации v2.

## 1. Общие правила

1. Expected values вычисляются из опубликованного уравнения, ручного независимого расчёта или внешнего эталонного набора. Production-функция не используется для подготовки expected output.
2. Каждый benchmark содержит method ID/version, citation, входные units/semantics, assumptions, expected output, tolerance и ожидаемые warnings/errors.
3. Исходные числа, censored tokens и missing states сохраняются отдельно. Строки `<0.01`, `0`, пусто и `bdl` не становятся одним значением.
4. Один benchmark проверяет один научный контракт. Интеграционный тест может связывать их, но не заменяет локальный эталон.
5. Изменение ожидаемого значения требует отдельного review: ссылка на источник, объяснение причины и запись старого результата.

## 2. Formula Registry: 15 семейств

Обязательные семейства:

1. olivine;
2. clinopyroxene;
3. orthopyroxene;
4. garnet;
5. feldspar;
6. mica;
7. amphibole;
8. spinel;
9. Fe-Ti oxide;
10. apatite;
11. perovskite;
12. nepheline;
13. carbonate;
14. titanite;
15. zircon.

Для каждого семейства нужны минимум четыре класса cases:

- идеальный или почти идеальный end-member с известной стехиометрией;
- реальный опубликованный/лабораторный анализ с ожидаемым APFU/QC;
- неполный анализ с отсутствующим диагностическим компонентом;
- граничный случай Fe valence, OH/halogens, total или charge-balance assumptions.

Formula benchmark проверяет oxygen/cation basis, сумму катионов, Fe2+/Fe3+ policy, site allocation, end-members, QC flags и отсутствие ложного species name. Абсолютная и относительная tolerance задаются по каждому output, а не одной глобальной константой.

## 3. Mineral Recognition

Benchmark-набор разделяется на:

- core catalog: 97 reference entries и 55 conservative chemical targets;
- alkaline/carbonatite extension: 27 entries и 12 targets;
- oxide specialist rules;
- intentionally ambiguous and unresolved cases.

Проверяются candidate order, score, confidence, reasons, ruleset/reference versions и запрет silent assignment. Species, неразличимые по routine EPMA, ожидаются на group/target level. Изменение ruleset не переписывает ранее принятое пользователем Mineral Assignment.

## 4. Composition statistics

### Exact cases

- CLR для `[1, 2, 4]`: geometric mean `2`, expected vector `[-ln(2), 0, ln(2)]`.
- Aitchison variation для простого набора с независимо рассчитанными `var(ln(x_i/x_j))`.
- ILR: проверяется ортонормальность выбранного basis и round-trip к closure с заданной tolerance.

### Guards

- mixed domain `Mg# + TiO2 + F` блокируется для CLR/ILR;
- oxides wt.% и trace ppm не смешиваются в одном log-ratio run;
- `0`, negative, missing и censored исключаются раздельно и попадают в excluded manifest;
- pseudocount не создаётся без отдельного versioned replacement method.

## 5. PCA и clustering

- PCA проверяет feature order, scaler, explained variance, loadings sign convention/эквивалентность и mapping обратно к stable Analysis ID.
- K-means имеет фиксированный seed и проверяемый synthetic dataset с ожидаемым partition с точностью до permutation labels.
- Hierarchical clustering проверяет linkage/distance parameters и membership.
- HDBSCAN проверяет noise labels, probabilities/strengths и small-sample guards; конкретная numbering cluster labels не считается научным результатом.
- Любое сохранение cluster как Work Group проверяет exact Analysis IDs и отсутствие побочного изменения Generation/Mineral/QC.

## 6. Group Fields

- Convex hull: exact vertices для известного набора, duplicates/collinear points и minimum `n`.
- Confidence ellipse: covariance, probability level, degrees of freedom/sample-size warning и singular covariance.
- KDE: bandwidth, grid extent, normalization и small-sample warning.
- Plot Visibility exclusion и `show_points=false` проверяются раздельно: скрытие маркеров не меняет field input.

## 7. Import и Measurement semantics

Fixture должен включать:

- несколько листов с разными строками заголовков;
- два блока на одном листе;
- `FeO`, `FeOt`, `Fe2O3`, смешанный Fe и отсутствие решения;
- `<0.01`, `bdl`, `0`, negative, blank, text note;
- oxides wt.%, trace ppm/ppb и APFU;
- повторяющиеся Sample/Point labels и разные analytical methods;
- duplicate rows и одинаковые значения из разных Source.

Проверяются atomic rollback, exact source row/header, original token, parsed value, unit, detection limit, decision provenance и Import Recipe semantic round-trip.

## 8. Fingerprint, stale и migration

- Изменение одного значимого Measurement меняет input fingerprint и делает Derived Value/Calculation Run stale.
- Изменение незначимого UI state fingerprint не меняет.
- Изменение method version или scientific parameter делает результат stale.
- Recipe/schema migration перечисляет changed/dropped fields и не применяется молча.
- Workspace Snapshot и Analysis Template имеют разные fingerprint domains: concrete IDs допустимы только в Snapshot.

## 9. Portable Project и publication

- archive manifest hashes проверяются до записи в workspace;
- `../`, absolute paths, symlink escapes и duplicate normalized paths отклоняются;
- SQLite integrity и expected entity counts проверяются до/после restore;
- publication manifest совпадает с exact Analysis IDs, units, Plot Specification, Calculation Runs и файлами пакета;
- Corel-safe SVG structural test запрещает `clipPath`, `mask`, `foreignObject` и embedded raster для редактируемых scientific layers.

## 10. Release gate

Scientific Method считается доступным пользователю только когда:

- definition и citation сохранены;
- independent canonical/boundary/error benchmarks зелёные;
- provenance и stale round-trip зелёные;
- связанные AT-сценарии зелёные;
- результат не меняет Measurement;
- версия метода и benchmark-set version попадают в diagnostic/export manifest.

Наличие похожего метода или зелёного теста в Streamlit v1 не удовлетворяет этому gate.
