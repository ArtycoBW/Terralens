# Контракт backend ↔ frontend ↔ ML

Для изменений действует [единый формат коммитов](../CONTRIBUTING.md): `type(scope): описание на русском`.

Версия проектного контракта v1. Это нормативный дизайн, не текущие работающие endpoints. Реализация генерирует `docs/openapi.json` из DRF и TypeScript-типы из него. Backend и frontend не должны независимо менять enum/поля. Изменения контракта сначала фиксируются здесь/в schema и fixtures.

## 1. Общие правила

- Base URL `/api/v1`. JSON UTF-8, snake_case, UUID строки, timestamps ISO8601 UTC, date `YYYY-MM-DD` без timezone-конвертации в UI.
- Float finite либо null. NaN/Infinity в JSON запрещены. NDVI — безразмерный; температура °C, осадки мм/сутки, площадь га.
- GeoJSON Polygon/MultiPolygon, EPSG:4326, координаты `[lon,lat]`. Bbox `[west,south,east,north]`. Geometry version обязательна в run.
- List envelope: `{items:[], next_cursor:null, total:null}`. Default limit 50, max 200; bbox discovery max задаёт capabilities. Series имеет отдельную временную resolution/pagination схему.
- Session cookie HttpOnly; CSRF header `X-CSRFToken` на mutations. Cookie/CSRF bootstrap не требует аккаунта. Приватные ответы не кешируются на публичном CDN.
- `X-Request-ID` на каждом ответе. `Idempotency-Key` обязателен на POST analysis/export/discovery job.
- 200 read/update/reused operation; 201 create; 202 accepted; 204 delete; 400 malformed input; 401 session required/expired; 403 forbidden; 404 inaccessible or missing; 409 version/idempotency conflict; 413 payload too large; 422 domain validation; 429 quota; 503 provider/service unavailable.

Error envelope:

```json
{
  "error": {
    "code": "invalid_geometry",
    "message": "Контур пересекает сам себя. Исправьте выделенную область.",
    "details": {"field": "geometry", "reason": "self_intersection"},
    "retryable": false,
    "request_id": "request-example"
  }
}
```

403 не раскрывает наличие чужих приватных объектов; предпочтительно 404 для object lookup. При backend auth failure внешнего провайдера пользователь получает provider_unavailable/setup_required, а не ошибочную logout-команду.

## 2. Endpoints

| Метод/путь | Запрос | Ответ/назначение |
|---|---|---|
| GET /health/live | — | liveness, без секретов |
| GET /health/ready | — | БД, очередь, model registry; не тяжёлые внешние запросы |
| POST /session | — + bootstrap policy | создать/возобновить guest workspace, cookie; rate limit |
| GET /session | — | workspace_id, role, expires_at, CSRF bootstrap |
| DELETE /session | CSRF | logout/expire guest session |
| GET /capabilities | — | limits, providers, supported_modes, active_model, feature_flags |
| GET /regions?q=&country= | явный поиск | items RegionSummary |
| GET /regions/{id} | — | bbox/geometry/source, fetched_at |
| POST /discoveries | region_id, bbox, sources | 202 {discovery_id,job_id}; bounded discovery |
| GET /discoveries/{id} | cursor, limit | status, items CandidatePolygon, source_status, coverage |
| GET /polygons | filters, bbox, cursor | сохранённые поля текущего workspace |
| POST /polygons | name, geometry OR candidate_id, crop_type nullable | 201 Polygon; источник candidate валидируется сервером |
| GET /polygons/{id} | — | Polygon с current_version |
| PATCH /polygons/{id} | name/crop metadata/geometry + expected_version | 200; geometry change создаёт новую версию |
| DELETE /polygons/{id} | expected_version | 204 soft delete; cancel active jobs |
| GET /polygons/{id}/analyses | cursor | история AnalysisRun |
| POST /analyses | polygon_id/version, period, mode, sources, options | 202 run_id/job_id; idempotency |
| GET /analyses/{id} | — | status, summary, snapshot/model versions, warnings |
| GET /analyses/{id}/series | from,to,resolution=daily/weekly/monthly,cursor | items DailyPoint, actual_resolution, next_cursor |
| GET /analyses/{id}/anomalies | severity, cursor | items AnomalyPeriod |
| GET /analyses/{id}/quality | — | coverage, exclusions, gaps, reference/model metadata |
| GET /jobs/{id} | — | state, stage, progress, retryable, result |
| POST /jobs/{id}/cancel | — | 202 cancel_requested; terminal job 200 unchanged |
| POST /jobs/{id}/retry | prior failed/cancelled job | 202 новый job с parent_job_id; frozen run config |
| POST /exports | run_id,format=csv/geojson/json | 202 export_id/job_id |
| GET /exports/{id} | — | status, filename, hash, expires_at, download_url nullable |
| GET /exports/{id}/download | session | streaming file /410 expired |
| GET /models | — | опубликованные ModelSummary, metrics scopes |
| POST /comparisons | run_ids ≤4,alignment | 200 summaries/series refs, не новые ML-расчёты |

Session создание — исключение для bootstrap без существующего CSRF; проверять origin, SameSite, rate limits. Остальные mutations требуют сессию/CSRF. Unauthenticated health/capabilities возвращают только публичную безопасную информацию.

## 3. Domain schemas

`RegionSummary`: id,name,country_code,bbox,provider,external_id,fetched_at.

`CandidatePolygon`: candidate_id,geometry,bbox,area_ha,name nullable,source,source_ref,source_date,confidence nullable,boundary_kind=`mapped_landuse|derived_cropland_candidate`,expires_at. Не связывать candidate с benchmark AOI.

`Polygon`: id,workspace_id,name,region_id nullable,current_version,geometry,geometry_hash,area_ha,source,source_ref,crop_type nullable,created_at,updated_at,latest_run_id nullable. В список допускается geometry omission при explicit lightweight=true.

Run creation example (UUID значения иллюстративны; это schema example, не реальный run):

```json
{
  "polygon_id": "10000000-0000-4000-8000-000000000001",
  "polygon_version": 1,
  "period": {"from": "2024-04-01", "to": "2024-10-30"},
  "mode": "retrospective",
  "sources": ["sentinel2", "landsat", "era5_land"],
  "options": {"climatology_years": 5, "refresh_sources": false}
}
```

Response 202: `{run_id, job_id, state:"queued", reused:false}`. Повтор операции возвращает тот же pair с reused=true; shape не меняется.

`AnalysisRun`: id,polygon_id,polygon_version,mode,period,state,job_id,model_version,config_version,created_at,completed_at nullable,snapshots[],warnings[],summary nullable,result_version nullable.

`summary`: observed_days,total_days,observed_coverage_ratio,reconstructed_days,unavailable_days,longest_gap_days,anomaly_period_count,overall_status=`normal|stress|critical|insufficient_data`,latest_estimate={date,value,origin} nullable. Critical/normal относится к выбранному периоду/правилу агрегации, `summary_rule` указывает алгоритм. Latest estimate не используется как недатированное «сейчас».

`DailyPoint` (полная shape всех nullable полей стабильна):

```json
{
  "date": "2024-06-14",
  "observed_primary": null,
  "clean_primary": null,
  "reconstructed": 0.54,
  "origin": "interpolated",
  "source_sensor": null,
  "sensors": {"sentinel2": null, "landsat": null, "modis": null},
  "climatology_mean": 0.62,
  "climatology_std": 0.08,
  "zscore": -1.0,
  "prediction_interval": {"lower": null, "upper": null, "level": null, "method": "not_calibrated"},
  "weather": {"temperature_c": 24.0, "precipitation_mm": null, "provider": "era5_land"},
  "support_count": 2,
  "gap_days": 8,
  "quality_flags": ["weather_missing"],
  "reference_years": 5
}
```

Числа примера условны. `reconstructed` — итоговое значение continuous series, включая сохранённое clean observation на наблюдаемой дате; различие указывает origin. `clean_primary` при rejected observation=null, raw остаётся observed_primary. origin=unavailable требует reconstructed=null. Observed coverage считается по пригодным наблюдениям, не по числу восстановленных точек; точное определение `observed_days` закрепить в schema description.

При `resolution=weekly|monthly` возвращается отдельная `AggregatedPoint` schema: bucket_start/end, estimate_mean/min/max, observed_count, available_day_count, total_day_count, minimum_z, quality_flags. Не выдавать агрегированное среднее за daily observed и не усреднять границы prediction interval с заявлением прежнего уровня покрытия. Негативные интервалы всегда запрашиваются независимо в точных датах. Диапазон response включает `actual_resolution`, чтобы frontend подписывал масштаб.

`AnomalyPeriod`: id,run_id,start_date,end_date,peak_date,severity=`stress|critical`,confidence=`low|medium|high`,event_kind=`persistent_period|single_observation_alert`,min_z nullable,integrated_deficit nullable,observed_evidence_count,reconstructed_fraction,quality_flags,causes[],explanation,review_status.

`causes[]`: code, label, confidence, evidence[] {metric,value,unit,period,source},counter_evidence[]. `explanation`: title,summary,observations[],possible_causes[],recommended_checks[],limitations[]. Длительность периода — inclusive dates; вычисление не подменяет evidence_count.

## 4. State machine и ошибки

Job state: `queued|running|succeeded|failed|cancelled`; run state: `queued|running|completed|partial|no_data|failed|cancelled`. Job succeeded может иметь run partial/no_data. Job.progress — число 0…1 или null; Job.stage — стабильный enum из backend ТЗ. Frontend не должен считать job succeeded равным run completed без чтения результата.

`Job`: id,kind,state,stage,progress,attempt,created_at,started_at,finished_at,cancel_requested,retryable,error nullable,result={type,id} nullable,parent_job_id nullable.

Codes: invalid_geometry, geometry_too_large, version_conflict, unsupported_period, unsupported_mode, empty_sources, quota_exceeded, provider_timeout, provider_rate_limited, provider_auth_required, provider_schema_changed, no_satellite_data, insufficient_reference, model_unavailable, model_schema_mismatch, artifact_expired, idempotency_conflict, session_expired.

Run partial содержит warnings с provider и affected_period/fields; успешные данные доступны. Empty series/no_data возвращаются 200 как результат существующего run; отсутствие самого run —404. Не кодировать состояние отсутствия данных исключительно HTTP-ошибкой.

## 5. Обязательства по интеграции

- Backend публикует OpenAPI и valid JSON examples, frontend types генерируются командой `pnpm api:generate` (должна быть реализована).
- Commit contract fixtures: normal, stress, critical, no_data, partial weather, long_gap, no_reference, failed/cancelled job, invalid geometry, expired session. Fixture header/metadata прямо помечает synthetic example.
- Contract tests проверяют required keys, enums, nullability и единицы; schema diff в CI должен обнаружить breaking change.
- ML → backend adapter маппит значения/quality без округления; UI округляет отображение, export сохраняет достаточную точность.
- Health/session paths и background proxy timeouts описать в deployment README; polling не требует WebSocket/SSE в P0. SSE можно добавить P2 без изменения базового resource API.
