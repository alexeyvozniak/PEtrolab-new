# Последовательность реализации PetroLab Desktop v2

**Статус:** нормативный план после legacy-аудита Streamlit v1  
**Базовая ревизия спецификации:** `186b0f9c4e7afb4794ae58bc853371308a72600c` с последующими исправлениями доказательной базы  
**Принцип:** один вертикальный срез должен быть полностью наблюдаемым, восстанавливаемым и научно проверяемым до начала следующего.

Этот документ задаёт пользовательскую последовательность поставки A–G. Детальные contract gates, зависимости M0–M6 и Definition of Ready находятся в `docs/architecture/POST_LEGACY_IMPLEMENTATION_ROADMAP_2026-08-30.md`; при расхождении научная и архитектурная граница из roadmap и ADR имеет приоритет над календарным порядком срезов.

## 1. Что считается первой поставкой

Первая поставка Desktop v2 не обязана повторять все страницы Streamlit v1. Она обязана безопасно провести один реальный набор через цепочку:

`Project → Import → Analyses → Selection/Work Group → Plotting → Statistics → Publication → Restore`.

Thin Sections, Images и связи Analytical Point входят в текущую v2, но развиваются после устойчивого таблично-графического ядра. Полноценный Rocks workflow, Grain Profile, thermobarometry/thermodynamics/partitioning UI и collaboration packages остаются за границей первой поставки.

## 2. Нулевой gate: контракты и эталоны

До production-кода должны быть зелёными:

- JSON Schemas и примеры команд первого среза;
- `SCIENTIFIC_RULES.md`, `DOMAIN_MODEL.md`, ADR и AT-сценарии;
- утверждённые экраны для изменяемого потока;
- независимые benchmark cases для добавляемого Scientific Method;
- migration policy для project schema и versioned recipes.

Неутверждённый `statistics-data-review-domain-guard-v1` остаётся candidate. Контракт mixed-domain guard обязателен уже сейчас, но именно его визуальное состояние нельзя считать утверждённым без решения пользователя.

## 3. Срез A: project shell и read-only Analysis table

### Результат

Приложение открывает тестовый Project, показывает виртуализированную таблицу Analysis и не меняет данные.

### Обязательные механизмы

- Tauri запускает один Python child process и обменивается versioned NDJSON.
- SQLite schema создаётся и мигрируется с backup.
- `analysis.query` возвращает устойчивые Analysis ID, units, method и provenance projection.
- Column Filters, sort и pagination не меняют Selection.
- structured errors не требуют чтения traceback в React.

### Gate

AT-01, AT-02 и архитектурные тесты процесса/идентичности. Перезапуск возвращает тот же Project без изменения Measurement.

## 4. Срез B: безопасный Import и табличная работа

### Результат

Пользователь импортирует реальный многолистовой Excel, проверяет блоки/колонки/единицы/Fe semantics, массово выделяет строки, сохраняет Work Group и выгружает точный Selection XLSX.

### Обязательные механизмы

- per-sheet/per-block header detection;
- versioned Import Recipe и semantic fingerprint;
- различение `<DL`, нуля, отрицательного, blank и отсутствующей колонки;
- явное решение `FeO`, `FeOt`, `Fe2O3`, mixed Fe;
- atomic Import Batch без partial write;
- linked source и managed copy как разные ownership modes;
- Edit Draft, external fingerprint/old-value check, backup и Operation Journal;
- Table View отдельно от Selection/Work Group;
- exact Selection export с provenance.

### Gate

AT-03–AT-09, AT-18, AT-26, AT-32, AT-36–AT-38. Повторное применение recipe либо даёт semantic round-trip, либо явный migration report.

## 5. Срез C: связанные графики и воспроизводимый Plot Specification

### Результат

Один Selection виден на 6–8 связанных панелях, легенда стабильна, Source фильтруется отдельно, точки скрываются обратимо, а график после перезапуска строится идентично.

### Обязательные механизмы

- binary/ternary/spider/REE панели используют один Selection;
- Legend Definition не пересобирается из текущего Selection;
- Plot Visibility, Filter, `show_points` и calculation exclusion различаются;
- Plot Layers имеют z-order, opacity и быстрый Field toggle;
- hull/ellipse/KDE сохраняют exact Analysis ID, method и parameters;
- Autoscale, Fit Selection, Reset, shared/manual ranges входят в Plot Specification;
- прямой экспорт одной панели/раскладки и Corel-safe SVG без `clipPath`/mask/PowerClip;
- panel labels Latin `a–d` или Cyrillic `а–г` входят в export state.

### Gate

AT-10–AT-14, AT-27–AT-28. SVG автоматически проверяется структурно и открывается в CorelDRAW для наблюдаемой приёмки.

## 6. Срез D: Sample, Thin Section, Images и Analytical Point

### Результат

Из Sample пользователь открывает шлиф, создаёт точку/область в исходных координатах изображения и явно связывает её с Analysis/Media Asset.

### Обязательные механизмы

- координаты не зависят от viewport zoom;
- фокус annotation не меняет Selection;
- похожее имя и совпавший Sample только предлагают candidates;
- automatic link допустим лишь по утверждённому составному ключу;
- cross-sample link требует явного exception;
- исходный Media Asset неизменяем;
- экспорт с метками создаёт производный файл, без меток копирует original pixels.

### Gate

AT-15–AT-25 и AT-37 для undo связей. Проверяется открытие после перезапуска на другом масштабе изображения.

## 7. Срез E: пошаговая Statistics

### Результат

Пользователь выбирает исследовательскую задачу, проверяет состав, запускает Calculation Run, видит ограничения и сохраняет кластеры как Work Groups.

### Обязательные механизмы

- mixed-domain guard для CLR/ILR;
- отсутствие silent pseudocount;
- отдельный Euclidean exploratory path;
- exact excluded Analysis ID и missing/censored policy;
- algorithm, scaler, parameters, seed и library version;
- Calculation Run input fingerprint и stale status;
- cluster labels не становятся Generation/Mineral/QC;
- один или несколько кластеров сохраняются как immutable Work Groups.

### Gate

AT-29–AT-31 и утверждение candidate-экрана domain guard. До этого разрешён core/contract implementation, но не production UI состояния проверки домена.

## 8. Срез F: Publication и быстрый экспорт

### Результат

Любой созданный материал быстро экспортируется на месте, а большой Publication Package собирает figures, tables, captions, supplementary data и machine-readable provenance.

### Обязательные механизмы

- exact table/figure snapshot с units и Analysis ID;
- journal profile не изменяет scientific data;
- current visible Plot Layers/Fields сохраняются в export;
- package manifest содержит hashes, recipe versions и captions;
- повторный экспорт детерминирован для одного immutable snapshot.

### Gate

AT-27 и publication smoke-test: manifest совпадает с фактическим ZIP, все ссылки разрешаются, originals не перезаписываются.

## 9. Срез G: продолжение работы и переносимый Project

### Результат

Workspace Snapshot возвращает пользователя в точное состояние, Analysis Template применяется к совместимому набору, `.petrolab` переносится на другой компьютер.

### Обязательные механизмы

- Snapshot содержит concrete IDs и выбранную Selection restore policy;
- Template не содержит concrete Analysis/Source/Dataset IDs;
- schema migration показывает changed/dropped fields;
- archive levels: `project`, `project+sources`, `full`;
- manifest hashes, zip-slip guard, SQLite integrity check;
- restore в непустой workspace требует backup и explicit replace;
- optimized media не заменяет originals.

### Gate

AT-33–AT-34. Export → clean restore → re-export даёт совпадающий доменный manifest за исключением явно перечисленных environment fields.

## 10. Приоритеты legacy-механизмов

| Приоритет | Механизмы |
|---|---|
| P0 до первой поставки | Import Recipe, Fe semantics, atomic import, stable IDs, exact Selection export, Edit Draft/conflict/backup, Table View, Plot Specification, Calculation Run fingerprint/stale, Workspace Snapshot, portable restore |
| P1 внутри первой поставки | versioned mineral suggestion, Smart Start, Operation Journal для утверждённых действий, user-derived expressions, group Fields, Publication manifest |
| После первой поставки | Grain Profile, method-specific thermobarometry/thermodynamics/partitioning UI, selective exchange/collaboration |
| Следующая версия | Rocks/whole-rock workspace, TAS/Harker/Rhodes и полный Rock Type editor |

## 11. Запреты реализации

- Не переносить Streamlit route/page/session-state architecture.
- Не создавать второй Quick/Advanced продукт; использовать progressive disclosure.
- Не реализовывать Scientific Method без versioned definition, independent benchmark и provenance.
- Не объявлять срез готовым по unit-тестам без соответствующего AT и визуального сравнения с утверждённым экраном.
- Не начинать следующий срез при известных silent data changes, broken restore или непроходящем migration gate текущего.
