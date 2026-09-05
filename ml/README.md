# Вычислительное ядро TerraLens

Python 3.12, автономный CPU-пакет. Для инференса не нужны Django, БД, Redis или сеть. Финальная модель — равновесный ансамбль трёх CatBoost residual моделей к M0: seeds 42/107/211, по 400 деревьев глубины 5, 78 календарных, сенсорных и локальных признаков, без погоды. Артефакт — `ml/artifacts/final/manifest.json`, model_id `131aee618934151e`. Исторический M0 сохранён в `ml/artifacts/baseline`.

На одинаковых development folds RMSE снизился с **0,069207 до 0,068260** на точках и с **0,095374 до 0,094173** на блоках. Обе метрики улучшились во всех пяти folds. Повторная assessment points/blocks: **0,071194 / 0,092206**; temporal 2024: **0,057633 / 0,080936**. На этих диагностических наборах точки улучшились, блоки ухудшились на 1,86% / 2,53%. Эти данные уже просматривались; нового слепого holdout нет. Официальный test RMSE неизвестен. [Последний протокол и компромиссы](../docs/analysis/crop-dynamics/REPORT.md), [предыдущий этап](../docs/analysis/model-coverage/REPORT.md), [исходные 13 вариантов](../docs/analysis/model-research/REPORT.md).

Позднее предоставленные ответы проверены на неизменённом `deliverables/submission.csv`: локальный RMSE **0,075034**, MAE **0,049410**, GapScore **7,49 / 30**, 3 112 точек. Обучение или выбор модели по этим ответам не выполнялись. Для другого входа `test_features.csv` отдельно построено 2 323 прогноза той же моделью; подходящих ответов к нему нет. [Сверка входов, хеши и воспроизведение оценки](../docs/CASE_AUDIT.md).

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
uv run --frozen python -m terralens_ml research --config ml/configs/crop-dynamics.yaml --development-only
uv run --frozen python -m terralens_ml research --config ml/configs/crop-dynamics.yaml
uv run --frozen python -m terralens_ml predict --input test-dataset.csv --output artifacts/submission.csv --model ml/artifacts/final/manifest.json
uv run --frozen python -m terralens_ml validate-submission --input test-dataset.csv --submission artifacts/submission.csv
uv run --frozen pytest ml/tests -q
```

`research --development-only` выполняет только folds и выбор кандидата: calibration/assessment не рассчитываются, финальная модель не обучается. `crop-dynamics.yaml` сравнивает прежний ансамбль, культуру, динамику сенсоров и оба набора признаков вместе. Полный запуск фиксирует победителя и только затем проводит fit, калибровку и повторную диагностику; артефакт создаётся в `artifacts/crop-dynamics/model`. Для публикации проверенного артефакта скопировать `model.json` и `manifest.json` в `ml/artifacts/final` либо передать путь операторской команде backend `register_model`. Прежняя версия доступна в Git и registry. Конфигурации прошлых этапов `mask-coverage.yaml` и `mask-ensemble.yaml` сохранены для воспроизведения.

План, folds и seeds фиксируются до расчёта. Выбор — минимум pooled points RMSE при отсутствии роста blocks RMSE относительно baseline. Для этого этапа условием публикации также стали ≥1% улучшения points, улучшение минимум в четырёх folds и положительная нижняя граница 95% парного AOI-bootstrap интервала. Все условия выполнены. Восемь старых holdout AOI исключены. Сохранены 21 selection, пять calibration и пять assessment; global fit использует только selection до 2024. Refit на calibration/assessment и подбор по повторным диагностическим результатам не выполняются.

Большие predictions и masks находятся в `artifacts/crop-dynamics` вне Git; компактные evidence — в `docs/analysis/crop-dynamics`. Повтор с другой схемой в том же output отклоняется. CatBoost использует два CPU-потока, члены ансамбля обучаются последовательно. Артефакт хранится в JSON с checksum, без pickle. Новым признакам соответствует schema_version=3: старые runtimes отклоняют его, новый runtime продолжает читать артефакты v1/v2. Признак культуры доступен для воспроизведения эксперимента, но в выбранной модели отключён; categorical JSON экспортируется с train Pool.

Старые команды `train --config ml/configs/baseline.yaml` и `evaluate --config ml/configs/validation.yaml` сохранены для воспроизведения первого этапа. `train` обучает модель без калибровки; выбранный артефакт с независимой калибровкой создаёт `research`. Старый `evaluate` повторно читает исторический holdout; его нельзя использовать для нового выбора гиперпараметров.

## Поведение восстановления

- Вся динамика скрытых контрольных строк удаляется до расчёта; дата и crop сохраняются, календарь пересчитывается. Предоставленные climatology/status/zscore не используются.
- Расчёт изолирован по AOI, сезону и непрерывному отрезку одной культуры. Смена wheat → maize → wheat создаёт три отрезка; соседи и окна не пересекают эти границы. Начало сезона задаёт `season_start_month`, по умолчанию январь; это техническая календарная граница.
- Raw NDVI сохраняется; значения вне [−1,1] исключаются из clean observations. В evaluation y_true не исправляется. Raw/filter и clipping доступны как явные абляции.
- M0 усредняет соседей, M1 учитывает расстояния в днях, PCHIP не экстраполирует. Внутренний gap≤60 дней, край≤14 дней; дальше — обученный crop/month prior, month prior, train median с low_support. Whittaker сглаживает только пропуски, пригодные наблюдения остаются неизменными.
- CatBoost корректирует только восстановленные значения. Сенсорная интерполяция доступна при расстоянии до ближайшего пригодного значения ≤14 дней. Локальные признаки: два наблюдения с каждой стороны, календарные расстояния и наклоны, линейная оценка, count/mean/std окон ±14/30/60 дней. AOI ID не входит в модель; отсутствующие признаки остаются NaN.
- Пять point masks разбивают перемешанные пригодные цели каждого AOI/сезона на непересекающиеся части; каждая цель скрывается ровно один раз за цикл. Между ними идут block masks. Ансамбль обучен на 79 256 примерах, охватывающих все 14 977 пригодных целей selection. Внутренние priors пересчитываются после маскирования. Если после внутренней маски не остаётся пригодного target для prior, возвращается ошибка.
- Новые признаки качества: расстояние до ближайшего значения и интервал между опорными датами каждого сенсора, число доступных NDVI-сенсоров и разброс их интерполированных оценок. Скрытая дата не предоставляет своей динамики.
- Динамика NDVI-сенсоров: строго предыдущее/следующее значения, календарные расстояния и наклон; медиана primary−sensor на ≥3 совместных видимых датах в окне ±60 дней, число пар и скорректированная сенсорная оценка. Недостаток данных остаётся NaN.
- Итоговая residual correction — арифметическое среднее трёх независимых CatBoost. Калибруется итог ансамбля; наблюдения остаются неизменными.
- M4 использует только предыдущие сезоны того же поля/crop, не менее трёх лет. `--reference-history train-dataset.zip` подключает дополнительную историю явно, с hash и запретом совпадающих ключей; её собственная synthetic mask сохраняется. Финальная модель не использует историческую норму как feature; M4 остаётся отдельным исследовательским вариантом.
- Submission содержит только контрольные ключи в исходном порядке. Валидатор проверяет точное множество, uniqueness, конечность и количество из входа: 3 112 строк для `test-dataset.csv`, 2 323 для предоставленного отдельно `test_features.csv`. Проверка выполняется до атомарной записи и после чтения файла.

## Интервалы, норма и события

Финальная модель хранит empirical residual quantiles уровня 90% на отдельной calibration выборке, с группами short/long/edge/prior и pooled fallback при N<100. Повторная assessment points coverage — **90,80%**, blocks — **90,08%**; temporal points — **92,91%**, blocks — **94,06%**. Повторные точки внутри AOI зависимы, оценочные данные ранее просматривались: безусловная гарантия покрытия не заявляется.

`reconstruct` возвращает колонку `prediction_interval` (dict lower/upper/level/method). Observed даты и некалиброванные модели возвращают null/not_calibrated. Backend передаёт `config={"interval_domain": "live"}`: method становится `empirical_residual_domain_shift`, добавляется domain_shift. Benchmark-калибровка не подтверждает покрытие реальных регионов.

Норма строится отдельно: годовые медианы окна ±15 дней по тому же AOI/crop, центр median, scale=1,4826×MAD, минимум три предыдущих сезона. Текущий сезон и synthetic-mask history исключаются. При scale<0,01 zscore=null. Явный `method="mean_std"` воспроизводит прежнюю политику; `season_start_month` задаёт границу reference seasons.

Границы: z≥−1 normal, −2≤z<−1 stress, z<−2 critical. Период требует двух наблюдаемых дней либо семи дней с наблюдаемым подтверждением. Полностью восстановленный участок не становится подтверждённым событием. Один критический spike — single_observation_alert. Long gap, low support и domain shift снижают confidence. Событие содержит долю доступной погоды и фактические evidence. Причины остаются гипотезами; независимых агрономических labels нет.

## Python API

Дополнительная [проверка на трёх реальных полях](../docs/analysis/field-cases/REPORT.md) использует неизменённые веса и все сенсоры скрываемой даты удаляет до расчёта. На 40 одиночных целях RMSE модели 0,05322 против 0,03754 у M0; на 38 целях в парах — 0,06677 против 0,07637. Перенос неоднороден; эти поля не использовались для нового обучения или выбора модели. В отчёте есть реальные события и повторный расчёт без сети.

Сводный статус приложения с правила `event-max-else-two-clean-days-and-half-period-reference-v3` требует для «Нормы» не только два пригодных наблюдаемых дня с z-score, но и доступную норму минимум на половине календарного периода. Подтверждённые события имеют приоритет. Недостаточная история остаётся `insufficient_data`; формула восстановления и веса не меняются.

`fit`, `reconstruct`, `predict_submission` — `terralens_ml.model`; `add_reference`, `detect_anomalies` — `terralens_ml.anomalies`. Backend импортирует тот же код, что использует CLI. Пригодные значения и порядок входных строк сохраняются. `load_model` проверяет JSON schema, checksum, priors и калибровку. Обучение в HTTP-запросах не выполняется.
