# Формульные семейства — AT-46, 2026-10-12

## Найдено и исправлено

Главная кнопка восстанавливала quick preset вместо выбранных Fe/OH параметров.
Независимый real-service UI-тест слюды воспроизвёл ошибку: после выбора OH и
Enter вычисленное OH исчезало. Теперь preset лишь задаёт начальные значения
из Python; одна кнопка рассчитывает текущие параметры. Второе конкурирующее
действие из настроек убрано. При пустом выборе причина отключения видна рядом
с основной кнопкой, даже когда настройки свёрнуты.

Кнопка и имя Analysis закреплены при прокрутке формулы/истории. Настройки имеют
явный Tab-stop. UI показывает `draft` и у оливина, где статус не входил в
per-row result: используется версия определения preview либо сохранённого
метода history, не более новый каталог для старого run.

Научные Python-алгоритмы, версии, implementation hashes, Measurements и
номенклатурные правила не изменены. Это исправление рабочего использования,
а не завершение полной структурной номенклатуры.

## Набор и независимые ожидания

| Fixture | Ожидание | Основание |
|---|---|---|
| `olivine_fo50.csv` | Si/Mg/Fe²⁺ = 1/1/1, Fo/Fa = 50/50 | Независимая стехиометрия MgFeSiO₄ |
| `mica_phlogopite.csv` | Si/Al/Mg/K = 3/1/3/1; OH_est = 2 только при выбранном OH и измеренных F=Cl=0 | Независимая стехиометрия флогопита, не production expectations |
| `clinopyroxene_e16_085.csv` | Si/Mg/Ca ≈ 1.81/1.03/0.57; Wo/En/Fs ≈ 32.34/57.79/9.87 | Опубликованная Table 6, egac110, существующий независимый benchmark |
| `orthopyroxene_e17_016.csv` | Si/Mg/Ca ≈ 1.80/1.56/0.04; Wo/En/Fs ≈ 2.45/86.76/10.79 | Та же Table 6; сумма отображённых оксидов 100.76, не подогнана к 100.78 |
| `amphibole_tn8.csv` | Si/Mg/Ca/Ni ≈ 8.0/4.4/1.6/1.0 | Опубликованная TN8 Table 2; допуск 0.1 APFU |
| `amphibole_unsupported_f.csv` | Ошибка на измеренном F=0; ноль сохранённых runs | Проверка границы метода, не отбрасывание F |

Первоисточники, допуски и ограничения находятся в ADR 0019–0023 и независимых
`tests/test_*_formula.py`. Ожидания скрипта не получаются вызовом расчёта.

## Реальный сервис и desktop

`scripts/qa_amphibole_service.py --all-methods` проверяет все пять семейств
через один настоящий NDJSON process. Проверены published/ideal значения,
единицы APFU/mol.%/wt.%, Measurement IDs, idempotent save, вновь прочитанная
SQLite history, неизменные Measurements/байты fixtures, Fe-ошибка без записи,
смена OH и отказ save со старым fingerprint. Полный AT-45 дополнительно
проверяет атомарный отказ смешанного scope и stale без перезаписи старого run.
Тот же сценарий прошёл на **PyInstaller executable** и включён в Windows CI.

Native Tauri QA проведена в `org.petrolab.amphibole-qa`, не в проекте пользователя.
Четыре дополнительных fixture импортированы реальным service API и явно приняты;
кнопка расчёта/save, просмотр значений и история проверены в настоящем UI.
После полного закрытия и `npm run tauri dev -- --config tests/tauri-amphibole-qa.json`
вновь открылись пять сохранённых runs; несохранённых preview после старта нет:

- Оливин: `5a3a0f66-17e1-4695-8f32-97f15f46be78`.
- Слюды: `19219bd1-6d14-4772-9311-b741a0178cde`.
- Cpx: `560b0217-30d2-4aa8-a3a6-bf10f3d98fbc`.
- Opx: `3dd60186-90ed-4337-a5e7-6e46af0741dc`.
- Амфибол: прежний `536491d2-eb15-484b-9312-445720c3f08c`, повторное save идемпотентно.

45 сохранённых Measurements шести Analysis сопоставлены по raw token и wt.%
с файлами-источниками после native расчётов: совпадают. Ошибочная строка Amp-F
не имеет сохранённого расчёта. Один Vite на 1420; sidecar запущен, icon создан.

## Скриншоты и соответствие

Настоящие PNG, размер каждого проверен: **1363×936**. Сохранена утверждённая
трёхпанельная структура ADR 0019; нового экрана и новых научных контролов нет.

- [Оливин](screenshots/formula-olivine-sticky-1363x936-20261012.png).
- [Флогопит](screenshots/formula-mica-sticky-1363x936-20261012.png).
- [Cpx](screenshots/formula-cpx-sticky-1363x936-20261012.png).
- [Opx](screenshots/formula-opx-sticky-1363x936-20261012.png).
- [Амфибол](screenshots/formula-amphibole-sticky-1363x936-20261012.png).
- [История оливина после перезапуска](screenshots/formula-olivine-history-1363x936-20261012.png).
- [История Opx после перезапуска](screenshots/formula-opx-history-1363x936-20261012.png).
- [Ошибка амфибола с сохранённым Fe-выбором](screenshots/formula-amphibole-error-1363x936-20261012.png).

В каждом проверенном состоянии ScrollPattern формульного инспектора возвращает
`HorizontallyScrollable=false`, `HorizontalScrollPercent=-1`. Подписи и select
помещаются; кнопка и имя Analysis видны над прокрученной таблицей.

## Проверки и предел приёмки

- Contracts: pass; 215 Python-тестов: pass.
- UI: 59/59, два полных запуска; 26 Tauri contracts: pass; 4 Sites: pass; build: pass.
- Packaged `--all-methods`: pass. Существующий chunk >500 kB — warning.
- Пять независимых UI-cases проверяют Enter, Tab к настройкам, текущие параметры,
  пустой выбор, ошибку без потери параметров и отсутствие save при ошибке.
- Real-service слюда проверяет OH/Fe именно через основную кнопку и сохранённую
  provenance; остальные real-service формульные сценарии также используют её.

Windows CI head `5b17aef` упал в немедленной assertion `aria-current` списка
изображений, не в формулах. Локально отдельный тест проходил. `b77904b` меняет
его на user keyboard и ожидание фактических aria-current/focus, без снятия
assertions и без изменения image UI. Frontend step Windows CI `b77904b` прошёл.
Полный CI следующего head фиксируется в PR #22, не выдаётся за завершённый здесь.

Нативная **клавиатурная** часть AT-46 пока не зачтена: Computer Use pipe
недоступен, Windows не разрешил QA-процессу получить foreground; защиту
от отправки клавиш в другое приложение не обходили. Новые native screenshot
и мышиные/service проверки не заменяют Tab/Enter в настоящем WebView.
Вердикт: рабочий общий срез подтверждён; полная release/native-keyboard приёмка
и полный структурный расчёт остаются открытыми.

Научные следующие срезы и пользовательские ограничения:
`docs/product/FORMULA_USER_GUIDE.md`. Перед ними — независимые ferric/anion/site
benchmarks, новое versioned definition и сохранение старых методов/runs.
