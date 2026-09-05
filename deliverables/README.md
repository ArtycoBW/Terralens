# Материалы для сдачи

- [Презентация TerraLens](presentation/TerraLens-defense.pptx) — 15 слайдов, 12 основных и три дополнительных; редактируемые диаграммы и таблицы, заметки докладчика.
- [Сценарий защиты и ответы](../docs/DEFENSE_GUIDE.md), [архитектура](../docs/ARCHITECTURE.md), [три реальных поля и графики](../docs/analysis/field-cases/REPORT.md).

Презентация и полевые проверки относятся к прежней модели `131aee618934151e`. Текущие веса и новые development-метрики описаны в [README](../README.md#как-обучалась-текущая-модель) и [отчёте обучения](../docs/analysis/rmse-wave/REPORT.md).

## Batch-результаты

Текущие результаты получены моделью **`594d4e6509459b08`** из `ml/artifacts/final/manifest.json`. Каждый содержит только `anon_polygon_id,date,primary_ndvi_pred` и контрольные строки своего входа, в исходном порядке, без дублей. Рядом лежат manifests с SHA-256 входа, модели и результата. Прежний результат второго входа сохранён отдельно.

| Результат | Вход | Строк | Оценка |
|---|---|---:|---|
| [submission.csv](submission.csv) | `test-dataset.csv` | 3 112 | Новая модель; test RMSE не измерялся |
| [submission-new-test.csv](submission-new-test.csv) | `test_features.csv` | 2 323 | Новая модель; подходящих ответов нет |
| [submission-test-features.csv](submission-test-features.csv) | Тот же `test_features.csv` | 2 323 | Исторические прогнозы модели `131aee618934151e` |

Это два разных тестовых набора без общих контрольных ключей. Организаторы не указали, какой считать финальным. Результаты нельзя смешивать; оценка платформы не получена. Ответы не читались в последней волне обучения и не использовались для выбора параметров. Исторические RMSE **0,075034** и GapScore **7,49 / 30** относятся к прежнему первому submission, а не к текущему файлу. [Точные исторические метрики и хеши](../docs/analysis/input-review/local-score.json).

SHA-256 новых результатов: `submission.csv` — `22f893a793f4584bb7b0a4e36bb1ab96b92916b1b6c5ea14aa72895b0d9480fe`; `submission-new-test.csv` — `54ced3df5e5bedf1c9c03915cb2cef2ef831735d4fc9448d0a2fa0d7d4286f76`.

Повторить из корня:

```sh
uv run --frozen python -m terralens_ml predict --input test-dataset.csv --model ml/artifacts/final/manifest.json --output deliverables/submission.csv
uv run --frozen python -m terralens_ml validate-submission --input test-dataset.csv --submission deliverables/submission.csv
```

Для второго входа используйте `--input test_features.csv --output artifacts/submission-new-test-check.csv`; затем вызовите `validate-submission` с теми же путями. В Docker подключите вход или его ZIP отдельным volume. Модель, исследовательские отчёты, frontend, презентация и инструкции запуска включены в репозиторий.
