# AT-15. Размеры окна и визуальные эталоны

Проверены «Обзор», «Анализы», «Поиск» и «Построение» в локальной нативной сборке Windows с KDE. Проект содержал семь синтетических анализов, два типа диаграмм и один источник CSV. Размеры заданы для области WebView при масштабе 1×. У нативного окна задан минимум 1180×800. Размер 390×844 проверен эмуляцией WebView. Исходный CSV совпал побайтово.

| Область WebView | «Обзор» | «Анализы» | «Поиск» | «Построение» |
| --- | --- | --- | --- | --- |
| 390×844 | [Снимок](screenshots/at15-native-viewports/AT-15-390x844-overview.png) | [Снимок](screenshots/at15-native-viewports/AT-15-390x844-analyses.png) | [Снимок](screenshots/at15-native-viewports/AT-15-390x844-search.png) | [Снимок](screenshots/at15-native-viewports/AT-15-390x844-plots.png) |
| 1280×800 | [Снимок](screenshots/at15-native-viewports/AT-15-1280x800-overview.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1280x800-analyses.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1280x800-search.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1280x800-plots.png) |
| 1440×900 | [Снимок](screenshots/at15-native-viewports/AT-15-1440x900-overview.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1440x900-analyses.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1440x900-search.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1440x900-plots.png) |
| 1920×1080 | [Снимок](screenshots/at15-native-viewports/AT-15-1920x1080-overview.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1920x1080-analyses.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1920x1080-search.png) | [Снимок](screenshots/at15-native-viewports/AT-15-1920x1080-plots.png) |

## Наблюдения

- Во всех трёх настольных размерах страницы укладываются по ширине. При 1280×800 команды построения переносятся на вторую строку, обе панели и действия отбора остаются видимыми. В таблице анализов при этой ширине измерения доступны через внутреннюю прокрутку таблицы.
- На 390×844 фактическая ширина страницы во всех случаях составляет 980 px. Правая граница общей кнопки «Добавить данные» находится на 720 px. В «Анализах» начальный экран показывает навигацию и фильтры, а таблица оказывается за правой границей. [Замеры](screenshots/at15-native-viewports/acceptance.json)
- По сравнению с полноразмерным эталоном «Построение» сохраняет общий левый навигатор приложения. Он занимает 205 px при 1280×800 и 238 px при 1440×900. Эталон использует эту область под раскладку и инструменты диаграмм. В проверенном «Обзоре» лента и план работы расположены в ожидаемых областях, при этом фон, группировка навигации и заголовок отличаются от эталона. [Построение](../design/reference/screens/plotting-approved-v1.png) · [Обзор](../design/reference/screens/overview-active-v1.png)

## Состояние эталонов

Из 36 PNG в каталоге эталонов 29 загрузились, семь содержат повреждённые данные изображения. Повреждение подтверждено декодированием PNG.

- `plotting-layers-fields-approved-v1.png`
- `statistics-clustering-result-approved-v1.png`
- `statistics-comparison-result-approved-v1.png`
- `statistics-data-review-approved-v1.png`
- `statistics-data-review-domain-guard-approved-v1.png`
- `statistics-guided-method-approved-v1.png`
- `statistics-task-approved-v1.png`

Сценарий остаётся открыт. Нужны согласованный узкий вариант, оригиналы семи эталонов, остальные утверждённые экраны и отдельная проверка системного масштабирования Windows. [Кандидат компоновки 390 px](../design/reference/screens/compact-workspaces-candidate.md)
