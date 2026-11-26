# Ускорение импорта PetroLab 2

Ветка: codex/import-performance; база: 006f6fc8b5a73a6b820c8fb4c85a3f65676e6df3. Release не меняется.

## Цели

- Отдельно измерять разбор, построение плана, интерактивные действия, SQLite и сквозной импорт; повторять тесты на одной машине, одном наборе и одинаковых условиях.
- Базовый исторический замер для 10 000 анализов × 12 оксидов: подготовка рецепта 7,94 с, запись 31,85 с (не новый замер). Цель следующей итерации — сквозной импорт до 15 с, тёплый просмотр таблицы до 200 мс; это цели, не обещание достигнутой скорости.
- Наборы: CSV/XLSX, 1 000/10 000/100 000 строк, многолистовые и транспонированные книги, неоднозначные единицы и Fe, пустые ячейки, <DL, дубликаты, метаданные.

## Очерёдность

- [x] Выделена ветка от актуальной release.
- [x] Первый кодовый срез: проверка отпечатка и разбор источника один раз за обычный preview_window; один раз за _review вместо отдельных разборов для плана и двух типов bulk scope. Добавлен регрессионный тест счётчика вызовов и отказа после изменения источника.
- [ ] Выполнить регрессионный тест, полный Python suite, validate_contracts и AT-02/03/35/38, зафиксировать исходный и новый замеры (CI не заменяет нативную приёмку).
- [ ] Профилировать этапы и размер NDJSON; отдельно определить узкое место записи SQLite.
- [x] Реализован ограниченный кэш разобранных источников по пути и точному SHA-256 (4 книги, 250 000 физических ячеек, 8 млн символов суммарно); на каждом обращении повторно хешируются байты, commit по-прежнему заново разбирает и валидирует файлы. Добавлены проверки тёплого просмотра, вытеснения и изменения байтов при сохранении размера и mtime. Приёмка и измерения ещё не завершены.
- [ ] Устранить пересчёт неизменённых источников; ключи включают полный набор значимых решений, версию правил, отпечаток и контекст. Не ослаблять stale guards.
- [ ] Пакетная запись измерений и provenance в существующей атомарной транзакции; проверить rollback при отказе в середине записи.
- [ ] Проверить повторное использование Import Recipe, прогресс и отмену; изменения UI только после согласованного эталона.
- [ ] Сравнить сквозные метрики, результаты scientific/restore gates, скриншоты и Windows MSI. Merge только после приёмки.

## Неприкосновенные условия

Сохранять исходные файлы побайтово, физические координаты, значения, единицы, Fe semantics, <DL, дубликаты, sample assignments, подтверждённые формулы, отпечатки и атомарность. Не менять SQLite schema и научные правила ради скорости. На первом срезе нет межкомандного кэша, изменения UI или ослабления проверки источника. Старые публичные функции по пути файла продолжают работать и проверять вход. До запуска тестов и измерений статус экспериментальный.

## 2026-11-26: проверка первого среза

Architecture CI на 5cfb96d: контракты прошли, 214 тестов, одна ошибка в прежнем тесте Windows-only записи XLSX на Linux (EDIT_EXCLUSIVE_ACCESS_UNAVAILABLE). Windows Python step прошёл. Отдельный коммит 9c911ca добавляет проверку безопасного отказа на не-Windows и оставляет полный Windows-сценарий неизменным. Следующий срез: ограниченный cache без кэша Import Plan. Не считать готовым до полного CI и измерений.

## Сравнительный замер

Добавлен `scripts/benchmark_import.py`: CSV/XLSX 1 000 и 10 000 анализов с 12 оксидами, отдельно create/get/пять preview/commit и размер JSON, точные SHA-256 исходника и измерений, SQLite integrity/foreign keys. Workflow Import performance comparison запускает тот же скрипт и те же файлы на baseline 006f6fc8 и candidate на одном Linux runner. Прирост скорости не утверждается до получения результатов; 100 000 строк, реальные книги и Windows остаются отдельной проверкой.

## Результаты benchmark 230a0b6 (2026-11-26)

[CI comparison](https://github.com/alexeyvozniak/PEtrolab-new/actions/runs/45832455244) success. Linux, Python-сервис, один runner, синтетические таблицы 12 оксидов. Все SHA-256 входов и измерений совпали, SQLite integrity/foreign keys pass.

| Формат / строки | Create до → после, с | Get до → после, с | Preview median до → после, с | Commit до → после, с |
|---|---:|---:|---:|---:|
| CSV 1k | 2.062 → 1.220 | 1.455 → 0.238 | 0.814467 → 0.000435 | 2.623 → 1.376 |
| CSV 10k | 19.690 → 11.815 | 14.579 → 2.590 | 8.019448 → 0.001532 | 27.577 → 15.413 |
| XLSX 1k | 2.475 → 1.434 | 1.773 → 0.232 | 1.023594 → 0.000416 | 3.000 → 1.516 |
| XLSX 10k | 25.087 → 14.259 | 18.255 → 2.600 | 10.447761 → 0.001095 | 32.381 → 16.693 |

Остаточное узкое место: review JSON ~45 MB на 10k строк, create/commit. Время UI не измерено. Срез записи: executemany с лимитом 8192 параметрических строк, без промежуточных commit, родительские таблицы записываются перед дочерними. Тест намеренно ломает поздний INSERT source_cell_provenance после нескольких flush, требует полного rollback и повторной успешной записи. Benchmark дополнен отпечатком provenance и семантики и проверкой числа строк. Следующий CI проверяет результат; новый прирост пока не заявляется.

### Commit readiness only

Внутренний `_project(..., readiness_only=True)` использует те же проверки источников, формул, обязательных вопросов и дубликатов, но не вычисляет отпечаток полной UI-проекции плана и не копирует её для интерфейса при commit. Публичная проекция не меняется. Финальный apply_import_batch по-прежнему повторно проверяет источник, план и формулы и сохраняет отпечаток плана. Тест сравнивает readiness с полной проекцией до и после изменения файла и проверяет отсутствие записи. Отдельно остаётся большой NDJSON для обычной интерактивной проверки; для него потребуется контракт постраничной выдачи с сохранением полного поиска и пакетных действий.

### 2026-11-26 — incremental review and recognition

Vocabulary recognition normalizes each candidate cell once, preserving exact short-token/prefix matching and missing markers; repeated header signatures computed once per block; block counts accumulated in one pass. Bounded per-source review plan cache (2 entries, total 10k records/150k measurements) keyed by exact recipe digest and freshly verified staged SHA-256; bypassed for mineral verification, annotations, sample assignments, accepted formulae and commit readiness. Explicit replan, discard and successful commit clear affected entries. Regression covers original predicate equivalence, unchanged get, changed mapping, client mutation isolation. Final commit still rebuilds and verifies the plan. No quantitative speed claim before CI.

### Compact review transport

NDJSON opt-in `columns_v1` avoids repeating 15+ measurement field names for every cell. The desktop API restores the full original objects before React (no pagination, layout change or search limitation). Test compares the entire decoded response with legacy projection including `<DL`, zero, null, Fe and source coordinates; malformed shape is rejected. Benchmark reports raw and compact serialized payload bytes where supported. Full UI and Windows latency measurement still required.

### Lazy physical preview

The approved Import workspace displays one active table. Instead of fetching all sheet/block previews on every decision, App requests only the current active block, including on source and sheet switching. Existing layout, draft guards and full scientific readiness remain unchanged. Real sidecar integration verifies one initial preview and one request when switching the sheet. User goal: immediate source navigation with the original table visible; primary action still review/commit; existing loading/error states and explicit exclusions remain. Native visual QA remains open.

### Import polish — 1/6

Reuse the successful clean-table classification plan and parsed source when adding a source. Rehash the staged bytes before retaining the inspection; seed only if the exact recipe digest matches (including project aliases). Both caches retain existing bounds. Final validation is unchanged. Test verifies one parse and one plan construction for clean input.

### Import polish — 2/6

Prepare immutable measurement mapping evidence once per field in row-oriented and transposed blocks, instead of resolving Fe header and mapping metadata for every measurement. Keep the exact measurement shape, coordinate construction, token handling, and independent mutable measurement objects. Regression checks mapping resolution count and coordinates; existing transposed and provenance fixtures remain in the full suite.

### Import polish — 3/6

Reuse the already parsed qualifier when computing the measurement value status. Public value_status continues to use the same helper. Tests include numeric zero, decimal comma, censored limits including underflow/overflow, <DL, ND, non-finite and missing values; no change to token or status semantics.

### Import polish — 4/6

Memoize the existing case-insensitive full-record JSON search index on the first nonempty query, reuse it across keystrokes, clear it when the query is cleared and invalidate it when the plan changes. All fields and all records remain searchable; the existing 120-row rendering limit, result count and UI layout are unchanged. Interaction test covers clearing, case-insensitivity and no matches.

### Import polish — 5/6

Use the existing activity message and spinner as an accessible stage indicator: 1–4 select/stage/recognize/preview; 1–2 review decision/preview; 1–3 atomic validation and persistence/staging cleanup/project refresh. Update only at actual awaited boundaries; no fabricated percentage or promise of progress within the synchronous service. Success/error and guards are unchanged. Real-service integration pauses the staging request and checks the status before release and after completion.
