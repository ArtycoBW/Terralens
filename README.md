# TerraLens — спецификация решения для Космохакатона


TerraLens — рабочее название сервиса мониторинга сельскохозяйственных территорий: выбор поля на карте → автоматический сбор спутниковых и погодных данных → восстановление NDVI → поиск и объяснение негативных аномалий.


## Запуск backend

Требуется Docker с запущенным daemon. Из корня:

```sh
docker compose up --build -d
```

Compose запускает миграции отдельным одноразовым сервисом и регистрирует включённый в репозиторий модельный артефакт. API: `http://localhost:8000/api/v1`, Swagger: `http://localhost:8000/api/v1/docs`, readiness: `http://localhost:8000/api/v1/health/ready`. Порты открыты только на loopback. Frontend в Compose пока не включён. Настройки локального запуска перечислены в `.env.example`; для публичного размещения нужны собственные секреты, домен и HTTPS.

## Автономный ML

Python 3.12; установка только вычислительного пакета:

```sh
python3 -m venv .venv-ml
.venv-ml/bin/pip install ./ml
.venv-ml/bin/python -m terralens_ml audit --input test-dataset.csv
.venv-ml/bin/python -m terralens_ml predict --input test-dataset.csv --output artifacts/submission.csv --model ml/artifacts/final/manifest.json
.venv-ml/bin/python -m terralens_ml validate-submission --input test-dataset.csv --submission artifacts/submission.csv
```

В Windows использовать `.venv-ml\Scripts\python.exe` и соответствующий `pip.exe`. После установки инференс не требует сети, Django, БД или Redis. Включённый артефакт — CatBoost residual к M0, выбранный среди 13 вариантов на пяти folds. На одинаковых development folds RMSE: **0,079287** против **0,090611** у M0; отдельная assessment: **0,082415**. На длительных блоках ошибка выше; официальный test RMSE неизвестен. [Протокол, калибровка и ограничения](docs/analysis/model-research/REPORT.md). Готовый [submission](deliverables/submission.csv) содержит 3 112 проверенных строк.

Для разработки всего Python workspace: `uv sync --frozen`; команды обучения, проверки и интеграции — в [ML README](ml/README.md) и [backend README](backend/README.md).

## Документы для начала разработки

2. [Продукт, приоритеты и матрица критериев](docs/02_PRODUCT_AND_ACCEPTANCE.md).
6. [Общий контракт API и данных](docs/03_API_CONTRACT.md).
7. [Каталог сценариев и пограничных случаев](docs/04_CASES_AND_TESTS.md).

## Структура

```text
backend/                  Django API, PostGIS, Celery, провайдеры, тесты и SPEC
frontend/                 ТЗ Next.js, интерфейса и будущего лендинга
  references/ascend/       распакованный исходный Ascend без изменений
ml/                       самостоятельный terralens_ml, configs, модель и тесты
docs/                     общие спецификации, критерии и план сдачи
  analysis/               результаты фактического аудита, текст/рендеры исходных PDF
scripts/audit_inputs.py    воспроизводимый аудит CSV, архивов и метаданных GLB
```

Исходные пять файлов сохранены в корне. `ml` — отдельный пакет внутри монорепозитория, а не отдельный микросервис: API-worker импортирует тот же код, который использует batch CLI. Ответственность за него входит в backend-направление.

## Выбранная архитектура

Python 3.12 + Django 5.2 LTS / GeoDjango + Django REST Framework, PostgreSQL/PostGIS, Celery, Redis. ML: pandas, NumPy, SciPy, scikit-learn и CatBoost. План frontend: Next.js App Router, TypeScript strict, shadcn/ui, Tailwind CSS, TanStack Query, MapLibre, ECharts; Three.js + GSAP + Lenis для Ascend. Python-зависимости зафиксированы в uv.lock и requirements.lock, контейнерные образы — по digest.

## Важные результаты анализа

- Train: 99 955 строк, 39 полигонов, 30 520 известных значений цели.
- Test: 57 185 строк, 78 полигонов, **3 112** контрольных пропусков.
- Submission: ровно `anon_polygon_id,date,primary_ndvi_pred`, только контрольные строки.
- CSV не содержит координат или контуров AOI. Нельзя размещать эти идентификаторы на карте по выдуманным координатам.
- Требуются две отдельные точки запуска: реальный веб-сервис с автоматическим сбором и автономный batch-инференс.
- Критерии дают суммарно 100 баллов; 30 из них зависят от RMSE. Лендинг не заменяет основной продукт.

## GetLayers


## Повторение аудита

В Python-окружении с pandas и NumPy выполнить из корня:

```sh
python scripts/audit_inputs.py
```

Скрипт не изменяет CSV, не извлекает скрытые ответы и не обучает модели. Результаты: `docs/analysis/input-manifest.json`, `dataset-profile.json`, `dataset-checks.json`, `ascend-assets.json`.

