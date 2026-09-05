# Batch-результаты

Оба результата получены моделью `131aee618934151e` из `ml/artifacts/final/manifest.json`. Каждый содержит только `anon_polygon_id,date,primary_ndvi_pred` и контрольные строки своего входа, в исходном порядке, без дублей. Рядом лежат manifests с SHA-256 входа, модели и результата.

| Результат | Вход | Строк | Оценка |
|---|---|---:|---|
| [submission.csv](submission.csv) | `test-dataset.csv` | 3 112 | Локально RMSE 0,075034, GapScore 7,49 / 30 по позднее приложенным ответам |
| [submission-test-features.csv](submission-test-features.csv) | `test_features.csv` в `doc-1788600393.zip` | 2 323 | Формат и ключи проверены; подходящих ответов нет |

Это два разных тестовых набора без общих контрольных ключей. Организаторы не указали, какой считать финальным. Результаты нельзя смешивать; оценка платформы не получена. Ответы не использованы для обучения или изменения первого submission. [Подробная сверка, точные метрики и хеши](../docs/CASE_AUDIT.md).

Повторить из корня:

```sh
uv run --frozen python -m terralens_ml predict --input test-dataset.csv --model ml/artifacts/final/manifest.json --output deliverables/submission.csv
uv run --frozen python -m terralens_ml validate-submission --input test-dataset.csv --submission deliverables/submission.csv
```

Для второго входа — [команды с исходным ZIP](../docs/CASE_AUDIT.md#3-отдельный-результат-для-test_featurescsv). Модель, исследовательские отчёты, frontend и инструкции запуска включены в репозиторий. Финальная презентация в комплекте не найдена.
