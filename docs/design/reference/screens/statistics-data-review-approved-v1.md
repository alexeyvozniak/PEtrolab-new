# Статистика: проверка состава данных

- **ID:** `statistics-data-review`
- **Версия дизайна:** v1
- **Состояние:** утверждено
- **Viewport:** 1440 × 1024
- **Связанные сценарии:** US-12, US-13, US-23, AT-12, AT-29
- **Дата утверждения:** 2026-08-29
- **Audit-informed candidate:** `../../candidates/statistics-data-review-domain-guard-v1.png`

## Назначение

Проверка точного входа, переменных, методов, пропусков и исключений до выбора статистического метода.

## Утверждённые решения

- Сравниваемые Work Groups и число Analyses видны слева.
- В центре показаны Analysis ID и фактические значения выбранных признаков.
- Filter, отмеченные строки и calculation input не смешиваются.
- Смешанные EPMA/EDS и пропуски требуют явного решения, которое сохраняется в протоколе.
- Audit-informed candidate добавляет компактный mixed-domain guard для Mg#/indices, concentration domains, APFU и CLR/ILR без нового шага процесса.
