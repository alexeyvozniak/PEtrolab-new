# Архитектура PetroLab Desktop v2

**Статус:** принята как стартовый контракт  
**Дата:** 2026-08-28

## 1. Цель

Архитектура должна позволять независимо менять красивую настольную оболочку, научные алгоритмы и хранение проектов. Следующий AI должен понимать основные границы за несколько минут и не нуждаться в слоях совместимости.

## 2. Процессы и ответственность

| Часть | Владеет | Не владеет |
|---|---|---|
| React UI | раскладка, доступность, жесты выбора, локальная проекция состояния, визуализация | формулы, SQL, импорт, миграции, provenance |
| Tauri shell | окно, системные диалоги, безопасные пути, запуск/остановка Python, упаковка Windows | Analysis, Selection, Generation, научные правила |
| Python application service | команды use case, сессия Selection, валидация ID, транзакции | компоненты и координаты интерфейса |
| Scientific core | доменные сущности, научная валидация, расчёты, импортные преобразования, provenance | SQLite, React, Tauri |
| Persistence | SQLite, репозитории, миграции, атомарность, резервные копии | вкладки, виджеты, легенда как CSS |

## 3. Топология запуска

1. Tauri запускает один локальный Python child process для открытого окна приложения.
2. Обмен идёт по stdin/stdout в формате NDJSON с `protocol_version` и `request_id`.
3. В первой версии не открывается localhost-порт и не вводится отдельный web server.
4. stderr Python сохраняется как диагностический журнал без пользовательских данных по умолчанию.
5. При завершении окна Tauri отправляет `shutdown`, ждёт штатное завершение и только затем останавливает зависший процесс.

Такой транспорт является деталью границы. Команды и ответы описываются схемами и не зависят от конкретной библиотеки IPC.

## 4. Направление зависимостей

```text
React views
    ↓ typed commands / projections
Tauri process supervisor
    ↓ versioned NDJSON
Python application services
    ↓
Scientific domain core ← Persistence ports → SQLite adapters
```

Зависимость всегда направлена внутрь. Scientific core не импортирует persistence adapter. SQLite adapter реализует интерфейс, объявленный приложением или core.

## 5. Команды первого vertical slice

| Команда | Вход | Результат |
|---|---|---|
| `project.open` | путь, режим миграции | Project Summary, версия схемы |
| `analysis.query` | колонки, сортировка, Column Filters, Plot Visibility | страница Analysis Projection |
| `selection.replace` | Analysis IDs | проверенный Selection |
| `selection.union` | Analysis IDs | обновлённый Selection |
| `selection.subtract` | Analysis IDs | обновлённый Selection |
| `work_group.create` | имя, описание, Selection IDs | сохранённый Work Group |
| `plot_spec.save` | панели, оси, легенда, фильтры | Plot Specification |
| `plot_data.query` | Plot Specification, viewport | данные панелей и маски видимости |
| `plot_visibility.hide` | Analysis IDs, причина уровня представления | обновлённая обратимая маска |
| `source_filter.set` | Source ID, visible | обновлённый Filter |
| `import.recipe.validate` | source fingerprint, Import Recipe | отчёт совместимости колонок, единиц и семантики без записи |
| `scientific_method.get` | method ID, version | версионированное определение метода и benchmark metadata |
| `workspace_snapshot.restore` | Workspace Snapshot ID | план полного или частичного восстановления ссылок и ревизий |

Команда возвращает либо `result`, либо структурированную ошибку. UI не разбирает traceback и не делает вывод по тексту ошибки.

## 6. Состояние и идентичность

- Все связи используют устойчивые UUID, а не номер строки, координату точки или подпись легенды.
- Selection — эфемерное множество `analysis_ids` в сессии. React хранит только синхронизированную проекцию.
- Work Group — неизменяемый снимок состава; его редактирование создаёт новую ревизию.
- Filter и Plot Visibility не меняют состав Selection и не удаляют Analysis.
- Legend Definition принадлежит Plot Specification. Selection добавляет overlay и не заменяет цвет/маркер серии.
- Выбранные строки закрепляются сверху только в табличной проекции; порядок не записывается в доменную сущность.

## 7. Графики и выбросы

`Plot Specification` хранит панели, оси, масштаб, легенду и фильтры. Отдельная `hidden_analysis_ids` — обратимая маска представления. Скрытые точки:

- остаются в проекте и Selection;
- не участвуют в автоматическом диапазоне осей;
- не попадают в lasso/rectangle hit testing;
- могут быть возвращены на графики;
- не получают автоматически QC-статус и не меняют исходные Measurement.

Для большого полотна UI виртуализирует панели, но единый Selection применяется и к панелям вне viewport.

## 8. Пространственные данные

Spatial Annotation хранит геометрию в исходных координатах изображения. Viewport, pan и zoom — только UI-состояние. Для калиброванного шлифа дополнительно сохраняется преобразование и координаты в системе шлифа. Media Link и связь Analysis–Annotation являются отдельными обратимыми отношениями.

## 9. Транзакции и безопасность данных

- Импорт сначала создаёт план и полный отчёт, затем выполняется одной транзакцией.
- Исходный файл никогда не меняется; сохраняются SHA-256, лист и исходная строка.
- Миграция проекта требует резервной копии и сверки количества сущностей до/после.
- Научное редактирование не выполняется через прямой SQL из UI.
- Measurement не перезаписывается Derived Value или Interpretation.

## 10. Версионирование

- `protocol_version` меняется при несовместимом формате команд.
- `project_schema_version` мигрируется отдельно от протокола.
- `algorithm_version` записывается у каждого Calculation Run и Derived Value.
- JSON Schemas в `/schemas` являются проверяемым контрактом обмена и сохранённых спецификаций.
- После legacy-аудита к обязательным сохраняемым контрактам добавлены `Import Recipe`, `Scientific Method Definition` и `Workspace Snapshot`. Порядок их внедрения и release gates определены в `docs/architecture/POST_LEGACY_IMPLEMENTATION_ROADMAP_2026-08-30.md`.

## 11. Решения и открытые вопросы

Принятые решения находятся в `docs/architecture/adr`. Библиотеки первого среза зафиксированы в ADR-0011: TanStack Table + React Virtuoso, Zustand, Radix UI и React SVG с узкими модулями D3. Выбор компонента не меняет доменную модель или протокол.

Компактное состояние mixed-domain guard утверждено как reference. Его научный контракт обязателен и не разрешает обход guard в M4.
