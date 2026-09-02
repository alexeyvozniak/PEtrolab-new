# PetroLab Desktop E2E

Этот набор тестов запускает настоящий Tauri executable через `tauri-driver` и Selenium на Windows.

Текущий smoke gate проверяет запуск приложения и базовую навигацию Import ↔ Analyses. Следующие сценарии должны добавляться здесь как реальные desktop workflows, а не только как React/unit contracts.

Windows CI перед тестом устанавливает matching Microsoft Edge Driver, собирает packaged Python scientific sidecar и debug Tauri executable.
