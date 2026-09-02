# PetroLab milestone QA gate

Milestone build разрешено отдавать на ручную пользовательскую приёмку только после четырёх зелёных слоёв:

1. architecture/contracts + Python/frontend tests;
2. public import regression corpus;
3. real Tauri Desktop E2E на Windows;
4. private normative real-workbook corpus со всеми обязательными книгами и approved baseline.

Ручная приёмка после этих gates оценивает UX и научный смысл. Повторять вручную технические сценарии, которые уже покрыты автоматикой, не требуется.

До подключения приватного corpus к защищённому runner публичный GitHub CI проверяет его registry и гарантирует, что raw workbooks не попали в репозиторий. Полный `--require-all` gate обязателен перед milestone/release и выполняется в окружении, где приватные исходники смонтированы.
