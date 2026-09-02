# Автоматизированный QA PetroLab Desktop

## Цель

Пользователь не должен быть основным регрессионным тестировщиком PetroLab. Ручная проверка нужна для научной корректности, удобства и milestone-приёмки, а повторяемые технические дефекты должны ловиться автоматически до выдачи новой сборки.

## Слои проверки

### 1. Contracts и unit tests

Быстрая проверка доменной модели, схем, scientific core и frontend contracts. Выполняется на каждом PR.

### 2. Import Regression Corpus

У импорта два слоя, и их нельзя путать.

#### 2.1. Нормативный real-workbook corpus — источник истины

Авторитетным считается набор **реальных пользовательских Excel-файлов**, а не синтетические примеры. Обязательные сценарии зарегистрированы в `fixtures/import/real-corpus.registry.json`. Сами исходники не коммитятся, потому что репозиторий публичный и научные данные могут быть неопубликованными.

Полный приватный gate фиксирует для каждой реальной книги:

- SHA-256 точного исходного файла;
- состав и порядок листов;
- число физических строк по листам;
- число распознанных logical blocks;
- коды import warnings;
- byte-identical состояние файла до и после чтения PetroLab.

Первый полный прогон создаёт `real-corpus.baseline.json` со статусом `candidate`. Baseline становится нормативной только после явной проверки и смены `review_status` на `approved`. Любое последующее изменение SHA, структуры листов, блоков или предупреждений ломает milestone gate и требует осмысленного пересмотра baseline.

Команда полного gate:

```bash
python scripts/validate_real_import_corpus.py --require-all --corpus-dir fixtures/import/real-private
```

#### 2.2. Public synthetic/minimized corpus — быстрый защитный слой

`fixtures/import/*.expected.json` и генераторы в `tests/real_world_fixtures.py` нужны для быстрых воспроизводимых PR-проверок, минимальных reproductions и редких edge cases. Они помогают локализовать дефект, но **не заменяют реальные книги**.

Новый баг, найденный на реальном workbook, считается закрытым только когда:

1. исходный реальный workbook включён или уже присутствует в приватном normative corpus;
2. его утверждённый baseline/contract отражает требуемое поведение;
3. при необходимости добавлен маленький synthetic reproduction для быстрой диагностики;
4. оба слоя проходят после исправления.

### 3. Real Desktop E2E

Windows CI собирает настоящий Tauri executable и управляет им через WebDriver. Windows runner устанавливает matching Microsoft Edge Driver и `tauri-driver`, после чего smoke gate обязан доказать, что приложение:

1. запускается как desktop executable;
2. показывает рабочий Import screen;
3. переключается на Analyses;
4. возвращается в Import через «Добавить данные».

После стабилизации smoke слоя сюда последовательно добавляются сценарии:

- Clean Table → import → Analyses;
- difficult workbook → structure review → mapping → import;
- invalid source → choose another file;
- import → restart → persisted analyses;
- duplicate review;
- wide worksheet navigation;
- transposed worksheet;
- retract latest import.

### 4. Release gate

Полный installer, fresh-install smoke, migration/restore, updater и **обязательный полный real-workbook corpus** проверяются для milestone/release candidate. Они не должны замедлять каждую мелкую итерацию разработки.

## Текущий нормативный real-workbook набор

Реестр сейчас содержит девять обязательных реальных книг: шесть исходных наборов, на которых уже развивался импорт PetroLab, и три реальные LA-ICP-MS книги 2026 года. Для кириллических вариантов имени допускаются только явно зарегистрированные aliases; случайный похожий Excel не может тихо подменить нормативный источник.

## Правило ручной приёмки

Ручная milestone-проверка начинается только после зелёных contracts, public corpus, real Desktop E2E и полного приватного real-workbook gate. Пользователь оценивает научный смысл и UX, а не повторяет механические smoke/regression сценарии.
