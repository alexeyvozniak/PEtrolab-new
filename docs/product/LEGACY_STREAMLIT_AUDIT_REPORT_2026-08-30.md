# PetroLab Desktop v2: итоговый аудит научного наследия Streamlit v1

**Дата:** 2026-08-30
**Streamlit v1:** `alexeyvozniak/PetroLab`, `main`, commit `e7bf36f46a6c049bc0dfb767483611e892503e41`, версия 0.16.1
**Desktop v2:** `alexeyvozniak/PEtrolab-new`, `main`, исходная точка аудита `4e200b7e9ca020e36a7ebcad7134074222a0bcba`
**Режим:** Streamlit v1 изучалась без изменений кода и рабочей базы. Для запусков использовалась отдельная временная `PETROLAB_DATA_DIR`.

## 1. Вердикт

Streamlit v1 содержит значительно больше научных механизмов, чем было отражено в спецификации Desktop v2 на начало аудита. Переносить её страницы, навигацию, session-state wrappers и compatibility routes не следует. Переносу подлежат контракты данных, проверяемые научные правила и несколько малых рабочих удобств.

Решения по 38 проверенным механизмам:

- `Keep`: 23;
- `Rework`: 8;
- `Defer`: 5;
- `Reject`: 2.

Главные пробелы Desktop v2 до аудита:

1. Нет точного контракта композиционной статистики: CLR/ILR, домены состава, нули, отрицательные значения и запрет произвольного pseudocount.
2. Не зафиксирован версионированный suggestion-layer распознавания минералов и независимый formula registry с тестовыми эталонами.
3. Не определены fingerprints расчётов, stale detection, пользовательские Derived Values и политика повторного расчёта.
4. Не определены безопасный черновик редактирования, восстановление после перезапуска, конфликт внешнего Excel, backup, undo и operation journal.
5. Не разделены Workspace Snapshot конкретной работы и Analysis Template, применимый к другому набору.
6. Не описан переносимый проект с уровнями включения источников и изображений, проверкой архива и безопасным восстановлением.
7. Не отражены быстрый точный экспорт Selection, сохранённые Table Views, восстановление рабочего контекста и deterministic Smart Start.

## 2. Доказательная база

Проверены:

- 522 отслеживаемых Git-файла Streamlit v1;
- 151 тестовый, regression, acceptance или smoke-файл;
- 75 модулей страниц и compatibility-модулей, из которых 38 маршрутов подключены непосредственно из `app.py`;
- научные модули формул, классификации, статистики, термобарометрии, термодинамики, partitioning и plotting;
- import, source sync, draft, archive, export, publication и collaboration services;
- история изменений от ранее проверенного commit `52b442b` до `e7bf36f`.

Из 65 явно выбранных и исполняемых научных и операционных test-файлов 60 прошли, 5 завершились ошибкой. Точный состав запуска и способ исполнения зафиксированы в `LEGACY_STREAMLIT_TEST_RUN_2026-08-30.md`.

| Проверка | Результат | Значение для аудита |
|---|---|---|
| `tests_import_service.py` | fail | старый fixture не передаёт обязательное решение `FeO`/`FeOt`; защита v1 сработала корректно, тест устарел |
| `tests_advanced_recipe_state.py` | fail | тест ожидает побитово прежний словарь, а текущая реализация добавляет `_scientific_context` для защиты от восстановления recipe в другом наборе; v2 нужен версионированный и контекстно связанный semantic round-trip |
| `tests_v0151_silent_errors.py` | fail | тест ожидает удалённую колонку `entity_link_source`; несовпадение схемы теста и текущего `main` |
| `tests_v0160_task_first_navigation.py` | fail | ожидаемый список навигации не обновлён после Product Design rebuild |
| `tests_grain_profile_hardening.py` | fail | тест импортирует удалённую приватную функцию `_exact_order` |

Дополнительные пробелы покрытия, не входящие в число 65 исполняемых файлов: отсутствуют отдельные `tests_edit_undo.py` и `tests_outliers.py`, хотя соответствующие модули существуют. Streamlit успешно запускался с изолированной `PETROLAB_DATA_DIR`, но cloud browser не получил доступ к локальному порту; поэтому визуальный UX-аудит не заявляется завершённым.

Эти расхождения показывают, почему код v1 нельзя копировать как источник истины. Научное поведение принимается только после отдельного контракта и новых Desktop v2 acceptance tests.

## 3. Карта Streamlit v1 в Desktop v2

| Область v1 | Основные маршруты/модули | Назначение в v2 |
|---|---|---|
| Старт и продолжение | `home`, `workflow`, `project_checklist`, `navigation_state` | «Обзор» и восстановление Workspace Snapshot |
| Добавление данных | `add_data`, `intake`, `quick_import`, `import_staging` | единый «Импорт» с progressive disclosure |
| Табличная работа | `analyses`, `batch_edit`, `attention`, `table_views`, `analysis_drafts` | «Анализы» |
| Формулы и классификация | `formulae`, `minerals`, `mixed_minerals`, `generations` | «Анализы» + Calculation Run; не отдельные обязательные страницы |
| Поиск и объекты | `search`, `global_search`, `object_workspace`, `samples`, `sources` | «Поиск» и «Образец» |
| Пространственные связи | `slides`, `thin_section_workspace`, `images`, `linked_petrography` | «Шлифы», «Изображения», Analytical Point |
| Исследование графиков | `plots`, `linked_views`, `multi_panel`, `ternary`, `science_plots`, `distribution` | «Построение» с единым Plot Specification |
| Статистика | `statistics`, `PCA`, clustering, `group_envelopes` | утверждённый пошаговый экран «Статистика» |
| Специализированные расчёты | `thermobarometry`, `equilibrium`, `thermodynamics`, `partitioning` | Calculation Run; UI после отдельного утверждения |
| Публикация | `article_tables`, `export`, `figure_recipes`, `publication_composer` | «Публикация» и быстрый экспорт владельца материала |
| Перенос и обмен | `projects`, `project_archive`, `collaboration`, `selective_exchange` | shell/Projects; collaboration отложена |
| Породы | `rocks`, `rock_workspace`, `whole_rock_compare` | следующая версия, как уже решил пользователь |

## 4. Реестр решений

| № | Механизм v1 и доказательство | v2 до аудита | Решение | Контракт v2 |
|---:|---|---|---|---|
| 1 | Per-sheet header row и semantic mapping: `column_schema.py`, `import_service.py` | частично | Keep | Import Recipe хранит физический индекс, исходный заголовок, каноническое поле и решение пользователя отдельно для каждого листа/блока |
| 2 | Поиск блоков и строк-заголовков: `import_staging.detect_block_header_rows` | отсутствует | Keep | несортированный лист сначала разбирается на подтверждаемые блоки; partial write запрещён |
| 3 | Atomic multi-sheet import и rollback: `import_runtime._rollback`, `tests_import_atomic.py` | частично | Keep | Import Batch фиксируется целиком или не создаёт видимых Analyses |
| 4 | Linked source и managed copy: `import_service._store_managed_source`, `sources.py` | отсутствует | Rework | тип владения файлом явный; mixed save scope блокируется; managed copy не выдаётся за внешний оригинал |
| 5 | Source fingerprint, old-value check и Excel backup: `sources._assert_source_is_current`, `analysis_service.save_changes_and_sync` | частично | Keep | внешняя запись только после проверки fingerprint и старого значения; backup создаётся до записи |
| 6 | Recovery snapshot и post-save warning: `analysis_service._post_save_maintenance` | отсутствует | Rework | primary save и обслуживание разделены; сбой recovery/QC не отменяет удачное сохранение, но остаётся видимым |
| 7 | Draft, restart recovery и conflict detection: `analysis_drafts.py`, `tests_analysis_drafts.py` | отсутствует | Keep | локальный Edit Draft сохраняется отдельно от Measurement, восстанавливается после перезапуска и не обходится при внешнем конфликте |
| 8 | Undo и operation journal: `edit_undo.py`, `operation_journal.py` | частично | Rework | обратимые научные операции журналируются с точным составом и inverse action; отсутствие regression test в v1 закрывается AT v2 |
| 9 | Stable Analysis identity и project scope | учтено | Keep | ни один перенос не возвращает row-number identity |
| 10 | Saved Table Views: `table_views.py`, `tests_v0158_table_views.py` | отсутствует | Keep | Table View хранит столбцы, порядок, сортировку, группировку и Filter, но не Selection и не копию Dataset |
| 11 | Row display states: hidden/excluded/label/color/marker | частично | Rework | view-only label/color/marker не становятся Generation, QC или Measurement; hide и exclude остаются разными действиями |
| 12 | Точный XLSX export Selection: `tests_v0158_selection_export.py` | отсутствует | Keep | массовая панель «Анализы» и «Поиск» выгружает ровно отмеченные Analysis ID вместе с provenance |
| 13 | Workspace Snapshot: `petrolab/ui/navigation_state.py`, IgPet/ioGAS audit | отсутствует | Keep | восстанавливает Data Universe, Table View, панели, оси, видимость, Selection по явной политике и активный Calculation Run |
| 14 | Analysis Template отдельно от Snapshot | отсутствует | Keep | Template не содержит конкретных Analysis ID и применим к другому совместимому набору |
| 15 | Portable `.petrolab`: `project_archive.py`, `tests_project_archive*.py` | частично | Keep | уровни project/project+sources/full; integrity check, zip-slip guard, backup и явная замена непустого workspace |
| 16 | Incremental selective exchange: `selective_exchange_merge.py`, `tests_selective_exchange.py` | отсутствует | Defer | не входит в первый vertical slice; сохраняется как будущий additive merge с origin identity |
| 17 | Versioned mineral suggestion: базовый каталог `petrolab/mineral_reference.py` содержит 97 записей/55 химических целей, alkaline extension добавляет 27 записей/12 целей | отсутствует | Keep | это suggestion, а не IMA-факт; ruleset, candidates, score/confidence и explicit acceptance обязательны |
| 18 | Formula registry: 15 mineral families, method IDs и oxygen bases: `petrolab/minerals/formulae.py` | частично | Keep | каждый Derived Value хранит method id/version, basis, inputs, assumptions и независимый benchmark |
| 19 | Fe valence/Droop/OH и halogen guards: `petrolab/minerals/formula_policy.py`, `petrolab/minerals/amphibole_ima.py` | частично | Keep | неизвестная валентность не становится измеренной; OH и амфибольная классификация показывают предел применимости |
| 20 | Formula fingerprint и stale detection: `tests_formula_fingerprint.py` | частично | Keep | изменение входов, метода или версии создаёт stale result; пересчёт создаёт новую версию, не подменяет прежнюю молча |
| 21 | User-derived expressions: `user_derived.py`, `tests_user_derived.py` | отсутствует | Rework | выражение, зависимости, единицы, автор, версия и ошибки сохраняются; результат не записывается как Measurement |
| 22 | Analytical Session и Measurement Registry | частично | Keep | повторные анализы, методы и единицы не выводятся только из имени колонки |
| 23 | CoDA CLR/ILR и domain guard: `statistics.py`, `SCIENTIFIC_AUDIT_HARDENING` | отсутствует | Keep | один log-ratio run использует только oxides wt.%, trace concentrations или APFU; mixed domain блокируется |
| 24 | No silent pseudocount; zero/negative/missing exclusion | отсутствует | Keep | замена censored значений допускается только отдельным версионированным правилом; число исключённых строк показывается до запуска |
| 25 | Aitchison variation matrix и Euclidean exploratory mode | отсутствует | Rework | log-ratio variation для composition; Pearson/Spearman/Kendall и scaler остаются явно exploratory для подходящих данных |
| 26 | PCA, K-means, hierarchical, HDBSCAN и seed | частично | Keep | algorithm, scaler, parameters, seed, excluded IDs и library version входят в Calculation Run |
| 27 | Кластеры → exact Work Groups | учтено | Keep | уже утверждённый контракт сохраняется |
| 28 | Outlier suggestions отдельно от Hide/Exclude/QC | частично | Rework | MAD/IQR/manual/graph actions не смешиваются; статистика использует явную calculation-exclusion policy |
| 29 | Convex hull, confidence ellipse, KDE и assumptions | учтено | Keep | уже утверждённый Field contract дополнен sample size, probability/bandwidth и предупреждением о предпосылке эллипса |
| 30 | Manual scientific field | отсутствует | Reject | ручная геометрия допустима только как annotation/interpretation и не называется data-derived или classification field без источника |
| 31 | Smart Start: `smart_start.py`, `tests_smart_recommendations.py` | отсутствует | Rework | deterministic рекомендации по минералу, наличию колонок и единиц; пользователь видит reason, но выбор не меняет данные |
| 32 | Shared/manual/Fit Selection axis ranges | отсутствует | Keep | Autoscale, Fit Selection, Reset, shared X/Y и ручной диапазон являются view state Plot Specification |
| 33 | Grain profile exact order/zones/distance/recipe | отсутствует | Defer | после первого vertical slice; вход только exact Analysis ID, NaN остаётся gap, разные coordinate frames не соединяются |
| 34 | Thermobarometry/thermodynamics with applicability | отсутствует | Defer | научный registry сохраняется; UI допускается только с citation, calibration range, uncertainty, equilibrium test и assumptions |
| 35 | Partition models and literature Kd | отсутствует | Defer | версионированный Source-aware model; реконструкция расплава явно называется model/proxy, не Measurement |
| 36 | Article tables and publication manifests | частично | Keep | Publication Package включает exact table, units, provenance, caption и machine-readable manifest |
| 37 | Whole-rock TAS/Harker/Rhodes | зарезервировано | Defer | экран пород остаётся следующей версией; TAS/QC и Fe rules не удаляются из scientific backlog |
| 38 | 38 подключённых Streamlit routes, 75 page/compatibility modules, session keys и Quick/Advanced split | отсутствует | Reject | интерфейс и compatibility architecture не переносятся; v2 использует девять утверждённых экранов и progressive disclosure |

## 5. Научные алгоритмы, которые нельзя объявлять перенесёнными без отдельных benchmark tests

| Блок | Входы и выходы v1 | Обязательная проверка v2 |
|---|---|---|
| Формулы минералов | olivine, pyroxene, garnet, feldspar, mica, amphibole, spinel, ilmenite, apatite, perovskite, nepheline, carbonate, titanite, zircon | независимые стехиометрические эталоны, method ID, oxygen basis, Fe assumptions, missing/censored policy |
| Mineral recognition | базовые 97 entries/55 targets плюс alkaline extension 27 entries/12 targets и oxide rules | canonical positive cases, ambiguous cases, low-confidence unresolved cases, ruleset version |
| Amphibole IMA screening | site allocation, subgroup/root-name diagnostics, Fe3 and halogen availability | область применимости, отсутствие ложной точности при неизвестных Fe3/F/Cl |
| CoDA | CLR, ILR, Aitchison variation | domain gate, no pseudocount, excluded-row manifest, invariance tests |
| Clustering | K-means, hierarchical, HDBSCAN | stable ID mapping, scaler/seed/library version, small-sample guards, no Generation side effect |
| Group fields | hull, covariance ellipse, KDE | точный вход после Plot Visibility, n, parameters, assumptions, export round-trip |
| Thermobarometry | Putirka 2008 cpx-only and registered methods | citation, equation version, calibration range, uncertainty, equilibrium/applicability confirmation |
| Thermodynamics | amphibole, zircon and olivine-liquid methods in `thermodynamics.py` | per-method calibration tests, stale fingerprints and full Calculation Run provenance |
| Partitioning | literature and imported partition models | source, phase context, units, applicability, measured-melt/proxy distinction |

## 6. Отложено и отвергнуто

### Defer

- Полноценный экран пород, whole-rock workspace, TAS/Harker/Rhodes: следующая версия по решению пользователя.
- Grain Profile: после основного table/plot/statistics vertical slice; контракт exact-order сохраняется сейчас.
- Thermobarometry, thermodynamics и partitioning UI: после отдельного научного review каждого метода.
- Collaboration/exchange packages: после доказанного portable-project restore и устойчивых IDs.

### Reject

- Streamlit layout, page registry, wrapper/hotfix chain, session-state compatibility architecture.
- Отдельные «быстрый» и «расширенный» продукты; остаётся один экран с progressive disclosure.
- Произвольный pseudocount и silent replacement для `<DL`.
- Автоматическое присвоение минерала, Generation или Rock Type по низкой уверенности/кластеру.
- Ручное поле, выдаваемое за data-derived или литературную классификацию без источника.
- Неявный merge двух независимых проектов и silent averaging внутри Analytical Point.

## 7. Изменения приёмки Desktop v2

Аудит требует добавить сценарии:

1. Mixed-domain statistics guard и отдельный Euclidean exploratory path.
2. Сохранение `<DL`, нуля, пустого значения и отрицательной концентрации как разных состояний.
3. Formula fingerprint/stale round-trip и независимый benchmark.
4. Draft recovery, external-source conflict, backup и undo.
5. Workspace Snapshot после перезапуска и Template на другом совместимом наборе.
6. Portable project export/restore с sources/assets и без них.
7. Exact Selection XLSX export и Table View без изменения Selection.
8. Versioned mineral suggestion, ambiguous review и запрет silent assignment.
9. Import Recipe semantic round-trip: schema version, context fingerprint, явная миграция и список несовместимых полей без silent drop.

## 8. Ограничения аудита

Cloud browser не смог открыть локальный Streamlit port, хотя сервер v1 успешно запускался. Поэтому этот документ является аудитом научных и операционных контрактов, а не завершённым визуальным UX-аудитом Streamlit v1. Для UX-части остаётся отдельная проверка на доступной Windows/local установке с реальными скриншотами основных потоков.

## 9. Итог для реализации

Выводы аудита разложены на зависимые vertical slices, contract gates и release criteria в `docs/architecture/POST_LEGACY_IMPLEMENTATION_ROADMAP_2026-08-30.md`. Первые исполняемые контракты представлены схемами `Import Recipe`, `Scientific Method Definition` и `Workspace Snapshot` с положительными и отрицательными примерами приёмки.

Первый Desktop v2 vertical slice не расширяется новыми верхнеуровневыми страницами. Найденные `Keep`/`Rework` механизмы входят в существующие экраны и application services. Scientific methods registry реализуется поэтапно; наличие метода в Streamlit v1 не считается доказательством его переноса. Объём Desktop v2 можно замораживать только после зелёных AT, добавленных по разделу 7.
