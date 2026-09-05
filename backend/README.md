# Backend TerraLens

Django/GeoDjango, DRF, PostgreSQL/PostGIS, Celery/Redis. API и worker используют один `terralens_ml`. Frontend и отдельный ML HTTP-сервис здесь не создаются.

## Docker

```sh
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 backend worker
```

Включён готовый модельный артефакт. Compose последовательно поднимает PostGIS/Redis, запускает migrate/register_model, затем API/worker/scheduler. База и результаты хранятся в volumes. Все опубликованные порты привязаны к 127.0.0.1.

При регистрации модель копируется в `ARTIFACT_ROOT/models/<manifest-hash>`; run ссылается на эту неизменяемую версию. Переобучение файла исходного checkpoint не переписывает прошлые версии.

Swagger: http://localhost:8000/api/v1/docs. OpenAPI: http://localhost:8000/api/v1/schema. Health: `/api/v1/health/live` и `/api/v1/health/ready`.

Полезные команды:

```sh
docker compose run --rm backend python manage.py migrate
docker compose run --rm backend python manage.py register_model
docker compose run --rm backend python manage.py reconcile_jobs
docker compose run --rm backend python manage.py cleanup_retention
docker compose run --rm backend python manage.py seed_demo
docker compose run --rm --no-deps batch predict --input test-dataset.csv --output artifacts/submission-docker.csv --model ml/artifacts/final/manifest.json
docker compose stop
```

`seed_demo` создаёт отдельное гостевое пространство и реальный датированный OSM-контур, возвращает UUID для операторских проверок. Она не выдаёт готовый результат за новый сбор и не создаёт браузерную сессию. Для пользовательского сценария ниже есть HTTP smoke.

## Локальная разработка

```sh
uv sync --frozen
docker compose up -d postgres redis
uv run --frozen python backend/manage.py migrate
uv run --frozen python backend/manage.py register_model
uv run --frozen python backend/manage.py runserver 127.0.0.1:8000
```

В отдельных терминалах из backend: `../.venv/bin/celery -A config worker --pool=solo --loglevel=INFO` и `../.venv/bin/celery -A config beat --loglevel=INFO --schedule=/tmp/terralens-celerybeat`.

На macOS настройки находят GEOS/GDAL в wheels Shapely/rasterio. На Linux нужны системные GEOS/GDAL/PROJ; контейнер устанавливает их сам. Не запускайте локальные и контейнерные workers одновременно против одной очереди: пути артефактов между окружениями различаются.

## Реальный HTTP-сценарий

```sh
uv run --frozen python scripts/api_smoke.py
```

Скрипт создаёт гостевую сессию, сохраняет реальный контур из записанного OSM-ответа, запускает новый анализ через API и ожидает Celery. Затем проверяет CSV/GeoJSON/JSON-экспорт, доступ к manifest и контрольные суммы; выполняет 40 чтений с concurrency=4. Запросы, job/run, полный пагинированный ряд и замеры сохраняются в `artifacts/api-smoke`, session cookies туда не попадают. По умолчанию проверяется 01–10.06.2024, Sentinel-2+Landsat+погода, без исторической нормы. `--reference-years 3` включает дополнительный исторический сбор. `--geometry` принимает локальный GeoJSON Feature для другого поля, например `backend/tests/fixtures/seville.geojson`. `--sources` ограничивает источники; `--skip-exports` и `--read-checks 0` отключают дополнительные проверки.

Самостоятельная проверка провайдеров: `uv run --frozen python scripts/live_spike.py --geometry backend/tests/fixtures/potsdam.geojson --output artifacts/spike`. Ограниченный spike помечает scene_limit/partial при превышении лимита. Проверенные два региона и многолетние снимки описаны в `docs/analysis/live-validation`.

## API и доступ

Создать сессию: POST `/session`, JSON `{}`, заголовок `Origin` текущего разрешённого origin. Ответ содержит csrf_token, браузер получает HttpOnly session cookie. Все последующие mutations требуют `X-CSRFToken`; создание analysis/discovery/export также требует `Idempotency-Key`. Чтение и изменение приватных ресурсов фильтруются по workspace. Гостевое пространство действует семь дней.

Маршруты реализованы для health/session/capabilities, поиска региона, discovery, CRUD полигонов, истории и запуска анализов, ряда/аномалий/качества, задач с отменой/повтором, экспорта, моделей и сравнений. `crop_seasons` хранит непересекающиеся датированные культуры; анализ фиксирует их версии в config. Сравнение до четырёх runs выравнивает календарные даты или MM-DD, сохраняя 29 февраля и флаги качества. Точная shape — [OpenAPI](../docs/openapi.json). В Next.js следует проксировать `/api/v1` на backend под тем же origin; долгие вычисления опрашиваются через jobs и не держат HTTP-соединение. Обычный proxy timeout — 60 секунд; сбор не требует увеличивать его до длительности Celery-задачи.

Период анализа: 1–366 дней, с 2017 года, конец не позднее пяти дней назад. Максимум 10 000 га, 5 000 вершин, три активных задачи на workspace. Discovery ограничен bbox 2 500 км². Возможности доступны через `/capabilities`.

## Реальные провайдеры

- Sentinel-2 C1 L2A, Earth Search: COG-окна по исходной геометрии, scale/offset из metadata, SCL 4/5/6, маска отверстий, медиана пригодных пикселей, минимум 30% покрытия.
- Landsat 8/9 C2 L2 Tier 1, Planetary Computer: 30 м, scale/offset до индексов, QA_PIXEL/QA_RADSAT. Временные SAS-подписи остаются только в памяти и не попадают в snapshots. Доля пригодных пикселей считается относительно всей площади AOI, включая часть вне сцены.
- Open-Meteo с моделью ERA5-Seamless: температура ERA5-Land, осадки ERA5, UTC daily, °C и мм/сутки, выборка сетки в центроиде. Источник обозначен `open_meteo_era5_seamless`, состав модели сохранён в provenance. Один ERA5-Land не предоставляет осадки через этот API; прежний источник давал null и заменён после live-проверки. В запросах сохранён совместимый ключ `era5_land`.
- Nominatim: явный поиск, общий Redis rate limit и cache. Overpass: farmland ways/multipolygon relations, источник каждого кандидата.

Старая коллекция `sentinel-2-l2a` не используется: live spike обнаружил несогласованность offset. В C1 получены пригодные NDVI. [Документация Earth Search](https://github.com/Element84/earth-search/blob/main/README.md), [сообщение об offset](https://github.com/Element84/earth-search/issues/71), [погодный API](https://open-meteo.com/en/docs/historical-weather-api).

Снимки источников неизменяемые, с query/geometry/config hashes, датой и checksum. При повторе используются проверенные снимки за последние сутки в том же workspace; refresh_sources запрашивает новые. Ключ кеша включает frozen лимит сцен и версию обработки источника. Лимит сцен явно даёт предупреждение. Ошибка одного спутника не отменяет пригодные данные другого. Отсутствие пригодного спутника — no_data; отсутствие погоды или нормы — partial/insufficient_data.

Норма каждой точки использует предыдущие сезоны того же сенсора: смещения S2/Landsat не откалиброваны. Для gap-дней выбирается преобладающий сенсор текущего периода; это видно в `reference_sensor_*` quality flag. Центр нормы — медиана сезонных медиан, масштаб — 1,4826×MAD, минимум три сезона. Неизвестная культура снижает confidence. Калибровка интервалов восстановления получена на benchmark и в live отмечена `domain_shift`.

Scheduler каждые 30 секунд восстанавливает доставку очереди и проверяет heartbeat, каждый час выполняет retention. `WORKSPACE_DAYS`, `EXPORT_DAYS`, `SNAPSHOT_RETENTION_DAYS` и `ARTIFACT_ORPHAN_GRACE_HOURS` настраиваются через окружение. Очистка сначала запрашивает отмену работающих задач, сохраняет связанные snapshots и модельный registry, удаляет только файлы внутри artifact root. PostgreSQL хранит авторитетные состояния; Redis не является единственной копией job.

## Проверки и текущие границы

```sh
uv run --frozen pytest -q
uv run --frozen ruff check ml backend scripts
uv run --frozen ruff format --check ml backend scripts
uv run --frozen python backend/manage.py makemigrations --check --dry-run
uv run --frozen python backend/manage.py spectacular --file docs/openapi.json --format openapi-json --validate --fail-on-warn
```

Тесты используют отдельную PostgreSQL/PostGIS БД и записанные реальные fixtures. Живые запросы в обычных тестах не выполняются. CI проверяет расхождение OpenAPI, миграции, submission и отдельную установку ML без Django/Redis с заблокированными socket connections.

GEE и MODIS не подключены; рабочий путь использует публичные STAC без пользовательских ключей. Raw observations находятся в неизменяемых snapshot-файлах; daily results — JSON в таблице с unique(run,date). Отдельные таблицы Observation/WeatherDay не нужны текущему API и остаются возможным расширением хранения. Подтверждённый диагноз причин, покрытие интервалов на новых регионах, публичный demo workspace и нагрузочная ёмкость не заявляются. Frontend, reverse proxy с публичным доменом и TLS относятся к последующему развёртыванию продукта.
