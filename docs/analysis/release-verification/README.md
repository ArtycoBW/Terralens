# Проверки перед публикацией

05.09.2026. Проверена финальная модель `25a39f51737d1012`; исходные данные и frontend не изменялись.

- **82 теста** прошли на PostgreSQL/PostGIS. Ruff, проверка миграций, Django system checks, OpenAPI без предупреждений и сравнение lock export прошли. Предупреждения pytest касаются устаревающего оператора внутри зависимостей rasterio/affine.
- [Автономный запуск](offline-evidence.json): окружение содержит только ML и его зависимости; Django/Celery/Redis отсутствуют, socket connections запрещены. Два результата побайтно одинаковы, по 3 112 строк.
- [Контейнерный batch](submission-evidence.json): тот же submission получен в Linux arm64, без запуска БД/Redis. SHA совпадает с macOS и включённым `deliverables/submission.csv`.
- [Пустая БД и artifact volume](clean-start.json): отдельный Compose project, все миграции и регистрация модели выполнены с нуля. Проверен тестовый пароль с символами, зарезервированными в URL: Compose передаёт параметры БД отдельно, не конкатенирует DSN. [Лог миграций](clean-start-migrations.txt).
- При первом чистом запуске выявлен преждевременный healthcheck PostgreSQL: `pg_isready` через Unix socket видел временный init-сервер. Исправленный healthcheck проверяет TCP, после чего повторный старт с пустыми volumes проходит.

Для проверки чистого запуска использовался изолированный проект `terralens-release-check` и порты 8001/54330/56380. Его тестовые volumes удаляются после проверки; основные пользовательские volumes не затрагиваются. API smoke сохраняет только данные результата, без session cookies и CSRF tokens. Для каждого запуска требуется пустой каталог output.

Повторить основные проверки:

```sh
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen ruff check ml backend scripts
uv run --frozen ruff format --check ml backend scripts
uv run --frozen python backend/manage.py makemigrations --check --dry-run
uv run --frozen python backend/manage.py spectacular --file /tmp/terralens-schema.json --format openapi-json --validate --fail-on-warn
```

Команды установки только ML и запуска с запрещённой сетью:

```sh
uv venv .venv-release
uv pip install --python .venv-release/bin/python -c requirements.lock ./ml
.venv-release/bin/python scripts/verify_offline.py --require-standalone
```

Исследовательский артефакт создан до итогового коммита: `git_revision` указывает базовую ревизию, а `source_sha256` фиксирует точное содержимое финальных ML-модулей. Значение проверено после форматирования. Веса и параметры не менялись после assessment.

## HTTP → Celery → источники → экспорт

[Финальный smoke Севильи](api-smoke-seville/run.json) выполнен на чистом Compose project. Новый полигон прошёл реальный сбор двух спутников и ERA5-Seamless, расчёт, сохранение PostGIS и экспорт CSV/GeoJSON/JSON. Все три файла скачаны, checksums и доступ к отдельным manifest проверены. Температура и осадки доступны за все 11 дней.

В этом повторном запросе три S2 COG чтения завершились RasterioIOError (неполные TIFF tiles), что отличается от отдельного успешного регионального сбора. Ошибки сохранены как scene_unavailable; Landsat дал один пригодный день, остальные десять восстановлены. История не запрашивалась (climatology_years=0), поэтому результат честно partial/insufficient_data. Это также проверка сохранения полезного результата при частичном отказе источника.

40 обычных чтений с concurrency=4: p95 **25.7 мс**, max 74.3 мс; создание анализа **107.0 мс**. Это локальная небольшая БД, не оценка предельной нагрузки.
