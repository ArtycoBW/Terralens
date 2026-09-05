# Вычислительное ядро TerraLens

Python 3.12, автономный CPU-пакет. Для инференса не нужны Django, БД, Redis или сеть. Выбранная модель — CatBoost residual к M0 с календарными и соседними сенсорными признаками, без погоды; артефакт — `ml/artifacts/final/manifest.json`. Исторический M0 сохранён в `ml/artifacts/baseline`.

На одинаковых development folds финальная модель получила RMSE **0,079287**, M0 — **0,090611**. Отдельная assessment points: **0,082415**; temporal 2024 points: **0,066037**. Для блоков ошибки выше: **0,128748 / 0,140835** соответственно. Официальный test RMSE неизвестен. [Полный протокол, абляции и ограничения](../docs/analysis/model-research/REPORT.md).

## Окружение и команды

Из корня workspace: `uv sync --frozen`. Для отдельного ML-окружения:

```sh
uv venv .venv-ml
uv export --package terralens-ml --no-dev --frozen --no-emit-workspace --output-file /tmp/terralens-ml-requirements.txt
uv pip sync --python .venv-ml/bin/python /tmp/terralens-ml-requirements.txt
uv pip install --python .venv-ml/bin/python --no-deps ./ml
```

Для точного воспроизведения используется общий uv.lock. Обычный `pip install ./ml` также устанавливает независимый пакет. В Windows заменить путь интерпретатора на `.venv-ml\Scripts\python.exe`.

```sh
uv run --frozen python -m terralens_ml audit --input train-dataset.zip
uv run --frozen python -m terralens_ml audit --input test-dataset.csv
uv run --frozen python -m terralens_ml research --config ml/configs/research.yaml
uv run --frozen python -m terralens_ml predict --input test-dataset.csv --output artifacts/submission.csv --model ml/artifacts/final/manifest.json
uv run --frozen python -m terralens_ml validate-submission --input test-dataset.csv --submission artifacts/submission.csv
uv run --frozen pytest ml/tests -q
```

`research` воспроизводит M0/M1/PCHIP, robust Whittaker, history+residual, CatBoost и абляции фильтрации/clipping/истории/погоды/сенсоров. План, folds и seeds фиксируются на диске до расчёта. Все восемь ранее просмотренных holdout AOI исключены. Из остальных 31 выделены 21 selection, пять calibration и пять assessment; global fit использует только selection до 2024. Остальные AOI уже встречались в старом baseline-исследовании, поэтому новая assessment не называется новым слепым holdout. Финальный refit на calibration/assessment не выполняется.

Большие воспроизводимые predictions и маски сохраняются в `artifacts/research` вне Git; компактные hashes/метрики/split — в `docs/analysis/model-research`. Повтор с другой схемой в том же output отклоняется. CatBoost использует два CPU-потока. Артефакт хранится как JSON с checksum; pickle не загружается.

Старые команды `train --config ml/configs/baseline.yaml` и `evaluate --config ml/configs/validation.yaml` сохранены для воспроизведения первого этапа. `train` обучает модель без калибровки; выбранный артефакт с независимой калибровкой создаёт `research`. Старый `evaluate` повторно читает исторический holdout; его нельзя использовать для нового выбора гиперпараметров.

## Поведение восстановления

- Вся динамика скрытых контрольных строк удаляется до расчёта; дата и crop сохраняются, календарь пересчитывается. Предоставленные climatology/status/zscore не используются.
- Расчёт изолирован по AOI и сезону. Начало сезона задаёт `season_start_month`, по умолчанию январь; это техническая календарная граница.
- Raw NDVI сохраняется; значения вне [−1,1] исключаются из clean observations. В evaluation y_true не исправляется. Raw/filter и clipping доступны как явные абляции.
- M0 усредняет соседей, M1 учитывает расстояния в днях, PCHIP не экстраполирует. Внутренний gap≤60 дней, край≤14 дней; дальше — обученный crop/month prior, month prior, train median с low_support. Whittaker сглаживает только пропуски, пригодные наблюдения остаются неизменными.
- CatBoost корректирует только восстановленные значения. Сенсорные признаки собираются заново из доступных соседей в пределах 14 дней; AOI ID не входит в модель. Недостающие признаки остаются NaN.
- M4 использует только предыдущие сезоны того же поля/crop, не менее трёх лет. `--reference-history train-dataset.zip` подключает дополнительную историю явно, с hash и запретом совпадающих ключей; её собственная synthetic mask сохраняется. Final M5 не использует историческую норму как feature.
- Submission содержит только контрольные ключи в исходном порядке. Валидатор проверяет точное множество, uniqueness, конечность и количество из входа; на текущем test это 3 112 строк. Проверка выполняется до атомарной записи и после чтения файла.

## Интервалы, норма и события

Финальная модель хранит empirical residual quantiles уровня 90% на отдельной calibration выборке, с группами short/long/edge/prior и pooled fallback при N<100. Assessment points coverage — **90,80%**, blocks — **87,74%**; temporal points — **92,55%**, blocks — **85,31%**. Повторные точки внутри AOI зависимы, блоки недопокрываются: безусловная гарантия покрытия не заявляется.

`reconstruct` возвращает колонку `prediction_interval` (dict lower/upper/level/method). Observed даты и некалиброванные модели возвращают null/not_calibrated. Backend передаёт `config={"interval_domain": "live"}`: method становится `empirical_residual_domain_shift`, добавляется domain_shift. Benchmark-калибровка не подтверждает покрытие реальных регионов.

Норма строится отдельно: годовые медианы окна ±15 дней по тому же AOI/crop, центр median, scale=1,4826×MAD, минимум три предыдущих сезона. Текущий сезон и synthetic-mask history исключаются. При scale<0,01 zscore=null. Явный `method="mean_std"` воспроизводит прежнюю политику; `season_start_month` задаёт границу reference seasons.

Границы: z≥−1 normal, −2≤z<−1 stress, z<−2 critical. Период требует двух наблюдаемых дней либо семи дней с наблюдаемым подтверждением. Полностью восстановленный участок не становится подтверждённым событием. Один критический spike — single_observation_alert. Long gap, low support и domain shift снижают confidence. Событие содержит долю доступной погоды и фактические evidence. Причины остаются гипотезами; независимых агрономических labels нет.

## Python API

`fit`, `reconstruct`, `predict_submission` — `terralens_ml.model`; `add_reference`, `detect_anomalies` — `terralens_ml.anomalies`. Backend импортирует тот же код, что использует CLI. Пригодные значения и порядок входных строк сохраняются. `load_model` проверяет JSON schema, checksum, priors и калибровку. Обучение в HTTP-запросах не выполняется.
