# AT-48: структурный Cpx (native evidence 2026-10-12)

Новый отдельный `clinopyroxene.structural6/0.1.0`, **draft**. Старый oxygen6
и его fingerprint/default/история не заменены. Pure Python: 6 O,
bulk APFU, идеальная оценка T/M1/M2, charge/site sums, строка формулы;
all Fe2, measured split или ограниченный Droop. Не определение вида,
не термобарометрия/измеренные occupancies, не полная пироксеновая модель.

## Независимые эталоны

[Yavuz 2013, первичный WinPyrox paper](https://triage19.com/products/AM/AM098P1338.pdf),
DOI 10.2138/am.2013.4292: p1339 allocation, p1348 Droop, p1350 Table 5 S4.
PDF SHA256 `050ec0965cb52a5b6b03adb347db7a7d21302a3b1fd84744cc806690b94e7e94`.
Страницы rendered/визуально прочитаны. QA PDF renderer не production dependency.
Printed S4 cations charge=12.064: default four-cation basis отличается от
нашего measured split six-O. Independent reference conversion 12/12.064,
допуск .003 APFU; allocation hand oracle с допуском .004. Не подгонять core
под printed «6 oxygen» label и не использовать другой Nimis/Papike алгоритм.
S4 reconstructed total Fe проверяет баланс Droop, **не** совпадение измеренного
Fe3; идеальный aegirine отдельно проверяет Fe3=1. Natural Droop требует
дальнейшей независимой проверки перед scientific validation.

Идеальные diopside/hedenbergite/jadeite/aegirine/CaTs, conservation/charge,
strict wrong-unit/missing/censored/duplicate/unsupported inputs, невозможные
Fe3 estimates, Si>2 и site imbalance проверяются отдельно. Нет wt.%→100 scaling.

## Native UI и найденный интеграционный дефект

Один Tauri dev в изолированном `org.petrolab.amphibole-qa`, 1363×936:
picker S4 → import commit → manual hedenbergite с причиной → old oxygen6
split/save → structural method/split/preview → positions → save/restart/history.
QA-проект, не проект пользователя. Settings/positions закрыты по умолчанию.
Компактные select не обрезаны, формула переносится, горизонтальной прокрутки
инспектора нет. Error при Droop на двух измеренных Fe сохраняет параметр и
history, save блокируется; смена Fe убирает preview.

Rust serde меняет порядок JSON object keys: native heading/table стали
M1/M2/T, хотя real Python UI test получал T/M1/M2. Python теперь передаёт
явный `site_order` array; React показывает этот порядок и сортирует site rows.
Независимый transport regression воспроизводит alphabetized map: сначала
failed heading, затем failed первая строка M1·Mg вместо T·Si; теперь pass.
Научные уравнения не переносились в React/Tauri.

Computer Use native pipe недоступен. Существующий UIA helper использован
без обхода foreground/focus checks. После активации пользователем прошли
Enter основной кнопки, Tab/Enter settings, смена ComboBox Fe клавиатурой,
ошибка/сохранение параметров. Это не проверка всех OH-путей других методов.
На следующем запуске повторно открыт current history после restart;
история остаётся current после оптимизации чтения batch inputs.

- [Settings](screenshots/cpx-structural-settings-1363x936-20261012.png)
- [Preview](screenshots/cpx-structural-preview-1363x936-20261012.png)
- [T/M1/M2](screenshots/cpx-structural-sites-1363x936-20261012.png)
- [Preserved Fe error](screenshots/cpx-structural-error-1363x936-20261012.png)
- [Reopened history](screenshots/cpx-structural-history-1363x936-20261012.png)

Current run `1ee399aa-11de-43f5-91e9-a81f534da240`, reported_split;
core hash `ffc297d084c065d1faa9fa95cf626f6978e20bf64f9f09114f89ec9fc22d60aa`.
Предварительный QA run с незавершённым development hash закономерно stale;
не удалён/не переписан. Old oxygen6 run current.
51→62 Measurements, 6→9 runs; прежние 51 Measurements SHA256
`a14ef642f792b29c496e0945a8176ca9fa77451fe61dba3cac276106d80bc554`,
прежние 6 run payloads SHA256
`8c768f878b450c77a9e730354f5fd1ad71a05269f34daa8c781e90233488c2ee`
до/после совпали. SQLite integrity ok.

## Verification

Contracts, 234 Python tests, 62 UI, 26 Tauri, 4 Sites, build pass для AT-48.
С последующим batch regression — 238 Python pass. Sidecar пересобран с final
core hash; packaged `qa_amphibole_service.py --all-methods --executable
desktop/src-tauri/binaries/petrolab-service.exe` проверяет все семь методов.
Существующий JS chunk >500KB warning не устранён этим срезом.

Opx structural, mica/amphibole complete models и остальные новые семейства
остаются backlog. Все методы draft; green software tests не validation.
