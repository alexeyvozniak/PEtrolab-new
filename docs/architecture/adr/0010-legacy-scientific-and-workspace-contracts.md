# ADR-0010: Legacy scientific methods and workspace persistence

- **Status:** Accepted
- **Date:** 2026-08-30

## Context

Аудит Streamlit v1 показал проверенные механизмы, отсутствовавшие в Desktop v2 specification: versioned formula/mineral/statistics methods, input fingerprints, safe edit drafts, saved table views, exact workspace recovery and portable project archives. Копирование Streamlit pages or session-state architecture нарушило бы границы Desktop v2.

## Decision

План работы «Обзора» хранится в базе проекта. У каждой задачи есть устойчивый ID и ревизия. По ревизии сервис отклоняет сохранение из устаревшего окна. Задачи входят в архив проекта вместе с его базой. Применение шаблона рабочего пространства не переносит задачи между проектами.

Scientific Method Definition становится единственным контрактом для формул, classification suggestions, statistics, thermobarometry and partition models. Derived Value and Calculation Run store method version, inputs, assumptions and fingerprints.

Первый метод формул `formula.olivine.4o` сохраняет APFU на 4 O и молярные доли выбранных двухвалентных катионов без распределения по позициям. Вход ссылается на точные Measurement ID одного Analysis, метода и набора в wt.%. Отсутствие выбранных дополнительных оксидов явно перечисляется, неопределённые и цензурированные токены отклоняются. FeO используется в стехиометрии как Fe²⁺. Отдельно заданный Fe₂O₃ сохраняет Fe³⁺, пересчёт суммарного Fe и оценка OH отсутствуют. Проверки суммы оксидов 95–105 wt.% и суммы катионов 2,9–3,1 APFU выдают диагностические предупреждения PetroLab без коррекции результата. Эталон APFU — [таблица 1 Gündüz и Asan](https://doi.org/10.1180/mgm.2022.113). Молярные массы используют [CIAAW 2024](https://ciaaw.org/abridged-atomic-weights.htm).

Команды `formula.review` и `formula.run` разделяют проверку и запись. Запись сверяет отпечатки метода и входа и сохраняет вычисленные значения в неизменяемом Calculation Run. `formula.run.open` вычисляет состояние актуальности, `formula.runs.list` возвращает историю анализа. Подтверждённая поправка XLSX участвует во входе как отдельная запись с Operation ID, исходный токен Measurement остаётся в базе без изменений. Черновики правок в формулу не попадают.

Каталог `formula.methods.list` включает проверенные на опубликованных составах методы полевого шпата (8 O), клино- и ортопироксенов (6 O), шпинели (4 O), ильменитового ряда (3 O), циркона (4 O) и оливина. Источник реализации — реестр формул PetroLab v1. Для новых методов все выбранные оксиды должны быть однозначными измерениями в массовых процентах. Пропущенные оксиды не участвуют в пересчёте, а доли An–Ab–Or и Wo–En–Fs требуют явного числового значения каждого компонента. Для пироксена используется долевое представление Ca–Mg–Fe²⁺ из v1. Метод не даёт IMA-имя и не оценивает Fe³⁺. APFU, молярные проценты и безразмерные индексы записываются с собственными единицами в существующий Calculation Run. [Таблица полевых шпатов](https://doi.org/10.1029/2019JE005998) · [Таблица пироксенов](https://academic.oup.com/view-large/392420083) · [Таблица циркона](https://doi.org/10.3390/min10110947) · [Таблица шпинели](https://www-odp.tamu.edu/publications/163X_IR/VOLUME/CHAPTERS/103.PDF) · [Таблица ильменита](https://doi.org/10.1029/2007JB004973).

Import Recipe, Edit Draft, Table View, Workspace Snapshot, Analysis Template and Operation Journal Entry are separate domain entities. Snapshot contains concrete research state; Template contains no concrete Analysis IDs. Portable archives have explicit inclusion levels and validated restore semantics.

Streamlit UI, wrappers, compatibility routes and session keys are not migrated. Legacy implementations are evidence and test input, not a code dependency.

## Consequences

Desktop v2 preserves scientific safety and small productivity mechanisms without reproducing the old page architecture. Additional persistence entities require schemas and migrations, but they remove the need for parallel UI state managers and prevent silent loss of research context.
