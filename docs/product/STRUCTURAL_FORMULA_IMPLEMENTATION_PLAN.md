# Структурные формулы: последовательность расширения

Пользовательский объём от 2026-10-12: завершить структурные расчёты и добавить
гранат, рудные минералы, перовскит, нефелин, полевые шпаты, анальцим и
фельдшпатоиды. Этот список - обязательный backlog, не заявление о готовности.
Экран остаётся существующим инспектором: одна кнопка, свернутые настройки,
отдельные исходные/производные значения и воспроизводимая история.

## Порядок малых срезов

1. Гранат: безводный X/Y/Z, explicit Fe2+/reported Fe3+/Droop, эмпирическая
   формула. ADR 0024, AT-47. Не охватывает весь garnet supergroup.
   Подключён draft; приёмка: `docs/qa/GARNET_STRUCTURAL_2026-10-12.md`.
2. Cpx/Opx: новые версии с Fe3+/Droop, T/M1/M2 и независимым ferric benchmark;
   старые oxygen6/0.1.0 и их fingerprints не менять.
   Cpx: отдельный `clinopyroxene.structural6/0.1.0`, ADR 0025, AT-48.
   Opx в приложении пока только прежний bulk. Подготовлено отдельное,
   **не подключённое к registry** ядро structural6 (ADR 0027, AT-50).
   Идеальные endpoint/баланс и природный ferric Tariat-эталон проверены отдельно;
   WinPyrox S1 («En или Cen») сам по себе не доказывает Opx-применимость.
   Tariat показывает ограничения Droop и идеальных Fe-Mg позиций, не их
   научную валидацию. Следующий срез — reviewed applicability/provenance,
   отдельная definition и native-подключение; не копировать
   Cpx target/номенклатуру и не объявлять идеальные позиции физическими.
3. Слюды/амфиболы: отдельные reviewed модели позиций и анионов, oxidation и
   измеренного H2O. Не определять неизвестные OH/Li/Fe3+ как измеренные.
4. Полевые шпаты: 8 O, T/M, An-Ab-Or; не выбирать полиморф по химии.
5. Рудные: самостоятельные spinel/Cr-spinel/Fe-Ti oxide/ilmenite/hematite
   методы с собственным Fe/валентным базисом. Сульфиды и самородные минералы
   не рассчитывать оксидной нормировкой; для них отдельный elemental domain.
6. Перовскит: ABO3, позиции/валентности и явные REE/Nb/Na-допущения.
7. Нефелин: Henderson, избыток Si, щёлочи и vacancies только по проверенной модели.
8. Анальцим: framework и отдельно измеренная/принятая вода; не делать 1 H2O
   измеренным результатом. Другие фельдшпатоиды имеют самостоятельные методы:
   лейцит/кальсилит, затем sodalite/cancrinite с Cl/S/CO3 и H2O.

Для каждого: первоисточник -> method definition/ADR -> идеальный и опубликованный
benchmark -> чистое Python ядро -> registry/NDJSON -> atomic save/stale/history
-> real-service UI -> packaged/native screenshots/keyboard -> отдельный commit.
Нет единой "формулы рудных" или общей кислородной нормы для всех фельдшпатоидов.
`validated` требует независимого научного review, не только зелёных тестов.

## Уточнение запроса 2026-10-13: точность всех семейств

«Более точный метод» означает проверенную применимость, валентности/позиции,
сопоставление с независимыми опубликованными числами и различимость допущений,
а не больше знаков после запятой. Один универсальный пересчёт для всех минералов
не допускается. При недостаточных измерениях точный ответ может быть отказом.

| Семейство | Следующий научный пробел | Доказательство до подключения |
|---|---|---|
| Оливин | пределы Fe3/малых компонентов и неопределённость, не слепая новая oxygen4 | природные анализы с независимо известным железом; прежний Fo–Fa не менять |
| Opx | T/M1/M2, отдельные Fe3/Droop assumptions | позиции/charge/conservation, ferric natural benchmark; новый method ID |
| Cpx | natural Droop и область идеальной allocation; не выдавать её за физическую Fe–Mg partition | независимый природный ferric эталон именно выбранной модели |
| Слюды/флогопит | T/M/I/W, oxidation, measured H2O и Li | раздельные anion/Fe модели, эталоны с измеренными F/Cl/H2O; unknown Li/OH не становится measured |
| Амфиболы | T/C/B/A/W, Fe3, OH/O и разные нормировки | Hawthorne-compatible ограниченная модель, независимые site/ferric/anion benchmarks; bulk23 не заменять |
| Гранаты | пределы Ti/majorite/hydrogarnet и uncertainty | отдельная применимость и benchmark; не расширять anhydrous модель молча |
| Полевые шпаты | T/M и An–Ab–Or | albite/anorthite/orthoclase + published natural input; никакого выбора полиморфа по составу |
| Рудные | отдельные spinel/ilmenite/hematite и elemental sulphides | разные валентные/анионные модели; sulfide wt.% не смешивать с oxides |
| Перовскит | ABO3 с substitutions/charge limits | ideal + published substituted case с явными valences |
| Нефелин | framework/excess Si/vacancies | независимый Henderson-compatible natural benchmark |
| Анальцим/прочие фельдшпатоиды | отдельные framework/anion/water модели | каждый mineral family отдельно; assumed H2O/CO3 не выдавать за measured |

После текущего UI batch-среза первый научный срез — **Opx structural**.
Если natural ferric reference отсутствует/недостаточен, не называть алгоритм
завершённым или validated. Затем mica/amphibole; прочие семьи остаются
обязательным backlog. Массовый UI использует только реально установленные
совместимые methods из Python, а не обещанные методы этой таблицы.

Точки расширения: `src/petrolab/formula_methods.py`, новые неизменяемые модули
методов, `tests/test_*_formula.py`, `tests/test_formula_workflow.py`,
`desktop/tests/import-workspace.integration.test.jsx`, packaged QA и ADR/AT.
React показывает структурные данные Python, но не вычисляет их.
