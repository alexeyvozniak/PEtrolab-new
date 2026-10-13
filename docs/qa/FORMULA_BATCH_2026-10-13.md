# Проверка сервисного пакета: 100 анализов

Production UI группового расчёта **не реализован и не принят**.
Согласованный контракт ADR-0019 остаётся прежним: 1–100 уникальных явных ID,
один метод/параметры, all-or-nothing save, immutable history, draft science.

Причина задержек: `_inputs` вызывал `list_project_analyses` отдельно для
каждого ID, повторяя запросы summary/import metadata проекта 100 раз.
Теперь один существующий bounded `analysis_ids` projection в той же SQLite
транзакции. Восстанавливается порядок запрошенных ID, отсутствующие строки
остаются failed, source snapshots и fingerprint semantics не меняются.
Это не устранение всех per-row SQL и не обещание конкретного ускорения.

Независимый `tests/test_formula_batch.py`: реальный импорт 101 состава Fo50,
явные mineral decisions, NDJSON preview/save/retry/history. До исправления
regression: `projection.call_count` 100 вместо 1; после исправления 4 pass.
Идеальные ожидания Si=Mg=Fe2=1, Fo=Fa=50, cation sum=3 получены из
стехиометрии, не вызовом production-функции.

Доказано: точные 100 ID и их порядок/Measurement provenance; один общий run,
retry без дубля; история у первого и сотого анализа, отсутствие у 101-го;
исходные Measurements/file bytes неизменны; integrity и foreign keys ok.
Отсутствующий сотый ID не пропускается; 101 ID отклоняется. SQL trigger при
записи сотого анализа откатывает предыдущие 99, run и project identity.
Изменение сотого входа отвергает весь old preview и делает общий run stale;
stored payload не переписывается. Мутации/trigger существуют только в temp QA.

Итог дерева с AT-48: contracts, 238 Python, 62 UI, 26 Tauri, 4 Sites,
production build pass. Существующее предупреждение chunk >500KB остаётся.
UI/native проверки AT-48 — отдельный отчёт; не выдавать их за batch UI QA.

Следующий согласуемый срез:
[краткий сценарий групповой обработки](../product/MINERAL_BATCH_RECALCULATION_PROPOSAL.md).
