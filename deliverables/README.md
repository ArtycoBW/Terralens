# Batch-результат

`submission.csv` создан из `test-dataset.csv` финальной моделью `ml/artifacts/final/manifest.json`. Только три требуемых столбца и 3 112 контрольных строк; порядок совпадает с исходным CSV. Рядом — manifest с SHA-256 входа, модели и результата. Официальные ответы неизвестны, test RMSE не заявляется.

Повторить из корня:

```sh
uv run --frozen python -m terralens_ml predict --input test-dataset.csv --model ml/artifacts/final/manifest.json --output deliverables/submission.csv
uv run --frozen python -m terralens_ml validate-submission --input test-dataset.csv --submission deliverables/submission.csv
```

Модель, исследовательский отчёт и инструкции запуска включены в репозиторий. Презентация и frontend относятся к отдельному комплекту работ.
