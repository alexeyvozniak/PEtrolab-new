# AT-49 — первый групповой пересчёт

Утверждён пользователем 2026-10-13. US-33, ADR-0026. Существующий зелёный
инспектор, один App Selection и те же Python preview/save/history; не новый
state manager/bridge/job queue. Один метод/параметры, максимум 100 ID.
Научные методы, их hashes/fingerprints и draft-статусы этим срезом не менялись.

## Наблюдаемое поведение

Флажки в «Анализах»/«Минералах» используют общий временный отбор. Фокус строки,
фильтр и загрузка страницы не изменяют его. Python перечитывает принятые
назначения и возвращает общий установленный метод; unaccepted/unavailable/
mixed scopes не уменьшаются молча. Сводка показывает готовые/ошибочные строки,
один анализ/error открыт, другие причины и состав закрыты.
Явное исключение меняет только Selection и требует нового preview.
Fe сохраняется при переходе к меньшему scope с тем же методом; late reply не
возвращает старый preview. Atomic save/retry/stale остаются Python-only.
История доступна у любого участника и раскрывает сохранённый состав с ID.

Дополнительный дефект больших наборов: выбранная проблемная строка могла быть
вне загруженной страницы. Exact-ID mineral projection и существующая загрузка
Analyses теперь возвращают её real fingerprint/ruleset и открывают проверку,
не очищая Selection. Следующая обычная страница сливается по ID, не добавляет
эту строку повторно. Scoped projections и merge имеют отдельные regressions.

## Реальное приложение

Один `npm run tauri dev -- --config tests/tauri-formula-batch-qa.json`.
Изолированный `org.petrolab.formula-batch-qa`; пользовательский проект не открыт
и не изменён. `scripts/qa_formula_batch.py` подготовил **через Python domain**
100 manual QA assignments; это не массовое назначение через production UI.
Последние две строки имеют Si=0 намеренно, принятие минерала не означает QC.
Native import 100 строк через picker этим сценарием не сертифицируется;
real-service UI test отдельно проходит import/acceptance/Selection/save.

В окне: accepted queue → выбрать загруженные 100 → calculate → 98 ready/2
failed и disabled save100 → next error → explicit remove → recalculate99 →
explicit remove → recalculate98 → save98 → search QA-Batch-099 (98 selected
скрыты, отбор неизменен) → Analyses (checkboxes сохраняются) → полный close/
restart → single QA-Batch-001 → current shared history. Selection после
restart пустой, как и положено эфемерному набору; immutable run сохранён.

Run: `dbe9681f-6e31-44b3-adfe-3ffcc53faa38`, 98 ID, all_fe2, 686 derived values.
300 Measurements до/после SHA256:
`99d0120e18cbbdfed417ac21af6ec0f1466bae07b26735a7ee6769ea265ccd70`.
CSV до/после:
`99b3b28c951adfa15e78e01abfdc418c9700ee1a1578a7fef9ece1272874eaf8`.
Один run, SQLite integrity ok; два исключённых анализа остаются в проекте.

Все картинки визуально открыты, реальные outer-window **1363×936**:

- [100 selected, одна кнопка, settings закрыты](screenshots/formula-batch-selection-1363x936-20261013.png)
- [Одна текущая ошибка и 98/2](screenshots/formula-batch-error-1363x936-20261013.png)
- [Fe select без обрезания](screenshots/formula-batch-settings-1363x936-20261013.png)
- [Новый точный scope98, Fo=Fa=50](screenshots/formula-batch-preview-1363x936-20261013.png)
- [98 скрыты фильтром, scope сохранён](screenshots/formula-batch-hidden-selection-1363x936-20261013.png)
- [Общий отбор в Analyses](screenshots/formula-batch-shared-selection-1363x936-20261013.png)
- [Shared history после полного restart](screenshots/formula-batch-history-1363x936-20261013.png)

Native inspector ScrollPattern: HorizontallyScrollable=false. Настройки/длинные
пояснения закрыты. Сохранённая история показывает текущий анализ, не среднее
значение всего пакета. Таблица Analyses остаётся широким существующим экраном;
её density/default visible identity columns — отдельный UX follow-up.

Computer Use native pipe unavailable; существующий UIA helper с guards.
Native Enter main action (99), Enter next error и Tab/Enter settings прошли.
Позже foreground заблокирован Windows; новые клавиши не отправлялись.
Не объявлять завершённой всю native keyboard матрицу Fe/OH/Space: Space и
Fe сохранение/ошибка/late reply покрыты UI tests, remaining native paths —
отдельная QA проверка. Blank/minimized initial captures заменены и просмотрены,
history после restart resize приведён к тому же outer size.

## Воспроизводимые проверки

Contracts valid; **239 Python**, **69 UI** (включая real service), **26 Tauri**,
**4 Sites**, production build pass. Existing chunk >500KB warning остаётся.
Sidecar пересобран на final core; packaged seven-method gate pass.

```powershell
$env:PYTHONPATH = 'src'
python scripts/validate_contracts.py
python -m unittest discover -s tests
python scripts/build_windows_service.py
python scripts/qa_amphibole_service.py --all-methods --executable desktop/src-tauri/binaries/petrolab-service.exe
python scripts/qa_formula_batch.py --verify-executable desktop/src-tauri/binaries/petrolab-service.exe
Set-Location desktop
npm run test:ui
npm run test:tauri-contract
npm run test:sites
npm run build
```

Packaged batch QA повторяется на dedicated подготовленном проекте: exact100
catalog, 98/2 preview, independent Fo50, whole-scope save refusal, exact unloaded
ID projection, unchanged source/Measurements/run count. Default prepare отказывается
от перезаписи непустого проекта. Python tests дополнительно: 101 IDs отказ,
missing100 не пропущен, late SQL failure rollback99, stale100, retry/history.
UI tests: exact100/error navigation, Fe retention after removal, late response,
101 без hidden chunking, pagination/filter/focus, unloaded issue review; real
explicit clear недоступного отбора даже в пустом active project;
import/acceptance/shared Selection/one save/history for each member и saved IDs.

## Следующий срез

Полная native keyboard матрица для группового Fe/OH/Space ещё не закрыта.
1000–2000, multi-method scopes, cancellation/resume и bulk mineral assignment
не реализованы. Научный следующий срез — Opx structural с опубликованным
независимым benchmark; [план точности всех семейств](../product/STRUCTURAL_FORMULA_IMPLEMENTATION_PLAN.md).
Ни один текущий bulk/structural метод не назван validated или полной моделью
всей минеральной группы.
