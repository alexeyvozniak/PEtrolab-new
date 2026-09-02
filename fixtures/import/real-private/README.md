# Private real-workbook corpus

Эта папка предназначена для нормативного корпуса **реальных исходных Excel-файлов**, на которых PetroLab обязан проходить импорт перед milestone/release-приёмкой.

Сырые книги намеренно не коммитятся: репозиторий публичный, а аналитические данные могут быть неопубликованными. `.gitignore` сохраняет в GitHub только этот README.

Обязательные книги и допустимые имена перечислены в `../real-corpus.registry.json`. Сейчас нормативный набор содержит девять реальных сценариев: исходные книги по слюдам/дайкам, два приборных экспорта 2023 года и три LA-ICP-MS книги 2026 года.

## Как устроена проверка

1. Реальные книги помещаются в эту папку или в любой приватный каталог.
2. Для внешнего каталога задаётся `PETROLAB_REAL_IMPORT_CORPUS_DIR`.
3. Первый полный прогон создаёт приватную candidate baseline:

```bash
python scripts/validate_real_import_corpus.py --write-candidate-baseline --corpus-dir fixtures/import/real-private
```

4. Baseline содержит SHA-256 каждого исходника, реальные листы, число обнаруженных logical blocks и коды предупреждений. Её нужно проверить; только после проверки `review_status` меняется с `candidate` на `approved`.
5. Нормативный milestone-gate:

```bash
python scripts/validate_real_import_corpus.py --require-all --corpus-dir fixtures/import/real-private
```

Он падает, если отсутствует хотя бы одна обязательная книга, изменились её байты, PetroLab изменил исходник во время чтения, поменялись листы/блоки/предупреждения относительно утверждённой baseline либо baseline не была явно утверждена.

Публичный CI проверяет сам реестр и безопасный synthetic regression corpus. Полный real-workbook gate запускается только там, где приватные исходники действительно смонтированы.
