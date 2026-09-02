# Автоматизированный QA PetroLab Desktop

## Цель

Пользователь не должен быть основным регрессионным тестировщиком PetroLab. Ручная проверка нужна для научной корректности, удобства и milestone-приёмки, а повторяемые технические дефекты должны ловиться автоматически до выдачи новой сборки.

## Слои проверки

### 1. Contracts и unit tests

Быстрая проверка доменной модели, схем, scientific core и frontend contracts. Выполняется на каждом PR.

### 2. Import Regression Corpus

Каждый известный проблемный источник становится постоянным fixture case:

- исходный файл `fixtures/import/<case>.<ext>`;
- ожидаемый контракт `fixtures/import/<case>.expected.json`;
- исходник должен оставаться byte-identical после inspect/plan;
- ожидаемые листы, candidate blocks и предупреждения проверяются автоматически;
- исправленный однажды дефект не может незаметно вернуться.

Новый баг импорта считается полностью исправленным только после добавления regression case, воспроизводящего его до исправления и проходящего после исправления.

### 3. Real Desktop E2E

Windows CI собирает настоящий Tauri executable и управляет им через WebDriver. Минимальный smoke gate обязан доказать, что приложение:

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

Полный installer, fresh-install smoke, migration/restore и updater проверяются только для release candidate. Они не должны замедлять каждую мелкую итерацию разработки.

## Начальный Import Corpus backlog

Существующие synthetic real-world generators уже покрывают основу будущего corpus:

- long instrument preamble;
- repeated headers;
- multiple logical blocks;
- complementary duplicate blocks;
- transposed weight-percent data;
- atomic-percent data;
- duplicate fields from different methods;
- generic isotope data.

Следующие реальные случаи должны добавляться из пользовательских файлов после обезличивания или как минимальные synthetic reproductions: blank populated headers, mixed Fe semantics, `<DL`/blank/zero/negative, wide workbooks, Cyrillic/network paths и многолистовые instrument exports.

## Правило ручной приёмки

Ручная milestone-проверка начинается только после зелёных contracts, corpus и Desktop E2E. Пользователь оценивает научный смысл и UX, а не повторяет механические smoke/regression сценарии.
