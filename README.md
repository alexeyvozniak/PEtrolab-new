# PetroLab Desktop v2

Новая настольная версия PetroLab для воспроизводимой работы с геологическими и геохимическими данными.

Desktop v2 находится в разработке. В навигации доступны импорт, анализы, поиск, образцы, связи, изображения, построение, статистика и публикации. Реализованные сценарии и открытые условия выпуска перечислены в [плане из 20 срезов](docs/product/RELEASE_20_SLICES.md).

## Что уже зафиксировано

- утверждены основные состояния «Обзор», «Импорт», «Анализы», «Образец», «Шлифы», «Поиск», «Построение», «Статистика» и «Публикация»;
- Selection, Work Group, Source, Generation, Filter и Plot Specification являются разными сущностями;
- сохранённая легенда не меняется от текущего Selection: выбранное накладывается зелёным контуром;
- таблица «Анализы» фильтруется по любой колонке, закрепляет выбранные строки сверху и позволяет обратимо скрывать выбросы на графиках;
- рабочее поле построения поддерживает 6, 8 и более связанных диаграмм с вертикальной прокруткой;
- точки и прямоугольные области на шлифе могут связываться с Analysis и Media Asset при любом масштабе изображения;
- Streamlit v1 остаётся отдельной стабильной версией и не меняется этим проектом.
- завершён legacy-аудит Streamlit v1 `e7bf36f`: научные и рабочие контракты перенесены в спецификацию без копирования старой page/session-state архитектуры.

## Целевая архитектура

```text
React UI → Tauri commands → Python child process → Scientific core + SQLite
```

React отображает проекции данных и пользовательское состояние. Tauri запускает приложение, управляет локальным Python-процессом и системными диалогами. Python владеет доменной моделью, валидацией, импортом, расчётами, provenance и транзакциями SQLite. Подробности: [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md).

## Источники истины

1. [Научные правила](docs/product/SCIENTIFIC_RULES.md)
2. [Доменная модель](docs/product/DOMAIN_MODEL.md)
3. [Пользовательские сценарии](docs/product/USER_SCENARIOS.md) и [приёмочные тесты](docs/product/UI_ACCEPTANCE.md)
4. [Дизайн-система](docs/product/DESIGN_SYSTEM.md) и [утверждённые экраны](docs/design/reference/)
5. ADR и техническая реализация

Порядок vertical slices зафиксирован в [DESKTOP_V2_IMPLEMENTATION_SEQUENCE.md](docs/product/DESKTOP_V2_IMPLEMENTATION_SEQUENCE.md), а обязательные независимые научные проверки — в [SCIENTIFIC_BENCHMARK_PLAN.md](docs/product/SCIENTIFIC_BENCHMARK_PLAN.md).

## Проверка фундамента

В PowerShell из корня репозитория:

```powershell
python scripts/validate_contracts.py
$env:PYTHONPATH = "$PWD/src"
python -m unittest discover -s tests
```

Явный `PYTHONPATH` нужен, чтобы тесты использовали этот checkout, а не установленную ранее копию пакета. Задача VS Code `PetroLab: Python tests` задаёт его автоматически.

## Перенос проекта на другой компьютер

Закройте PetroLab. В PowerShell из каталога приложения укажите путь к своей базе и создайте архив. Уровень `full` включает базу, исходные таблицы и изображения. Для переноса только базы используйте `project`, для базы с таблицами — `project_sources`.

```powershell
$project = Join-Path $env:APPDATA 'org.petrolab.desktop\petrolab-v2.sqlite'
.\binaries\petrolab-service.exe archive export $project 'D:\PetroLab.petrolab' --level full
```

Скопируйте архив на другой компьютер. Восстановление создаёт новый каталог. Затем откройте его в отдельном запуске PetroLab:

```powershell
.\binaries\petrolab-service.exe archive restore 'D:\PetroLab.petrolab' 'D:\PetroLab-Project'
$env:PETROLAB_PROJECT_DATABASE = 'D:\PetroLab-Project\project.sqlite'
.\petrolab-desktop.exe
```

Обычный запуск из меню «Пуск» открывает базу в каталоге приложения.
