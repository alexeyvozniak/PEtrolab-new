# PetroLab Desktop v2

Новая настольная версия PetroLab для воспроизводимой работы с геологическими и геохимическими данными.

Репозиторий пока находится на стадии **архитектурного и продуктового фундамента**. Здесь намеренно нет реализации интерфейса: код экрана появляется только после утверждения его эталонного макета и наблюдаемого поведения.

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

```bash
python scripts/validate_contracts.py
python -m unittest discover -s tests
```

## Следующий разрешённый шаг

Реализовать срез A из `DESKTOP_V2_IMPLEMENTATION_SEQUENCE.md`: project shell, versioned NDJSON и read-only Analysis table. Затем последовательно закрывать Import/Analyses и Plotting, не пропуская scientific/restore gates.
