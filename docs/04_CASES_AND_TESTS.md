# Каталог сценариев и проверок

Для изменений действует [единый формат коммитов](../CONTRIBUTING.md): `type(scope): описание на русском`.

Это конечный проверяемый набор известных классов случаев, а не обещание охватить любое возможное поведение внешнего мира. Новые обнаруженные случаи добавляются с ID и ожидаемым результатом. P0/P1 тестируются до сдачи; P2/P3 — если функция включена.

## 1. Пользовательские пути

| ID | Сценарий | Ожидаемый результат | Проверка |
|---|---|---|---|
| UX-01 | новый посетитель открывает /app | карта и пояснение первого шага, гостевая сессия | E2E |
| UX-02 | вводит неоднозначный регион | несколько подписанных результатов, явный выбор | UI fixture |
| UX-03 | выбирает регион с доступными farmland | реальные контуры и источник | live smoke |
| UX-04 | контуров нет | empty, возможность рисования; не error | E2E |
| UX-05 | Overpass недоступен | provider error/retry, рисование доступно | integration |
| UX-06 | выбирает готовый контур и период | сохраняется Polygon и AnalysisRun | E2E real API |
| UX-07 | рисует/исправляет контур | preview площади, валидное сохранение | browser |
| UX-08 | запускает анализ и обновляет страницу | восстановлен тот же run/job | E2E |
| UX-09 | дважды нажимает запуск | один логический job | concurrent integration |
| UX-10 | меняет выбранное поле во время ответа | старый response не заменяет новый выбор | UI race test |
| UX-11 | нажимает аномальный период | график фокусируется на нужных датах | E2E |
| UX-12 | нет аномалий и достаточно данных | normal с покрытием | contract/UI |
| UX-13 | наблюдений нет | no_data, не normal | end-to-end |
| UX-14 | удаляет сохранённый полигон | исчезает из активных, связанный job отменяется | integration |
| UX-15 | редактирует геометрию после анализа | новая версия; старый результат подписан | integration/UI |
| UX-16 | сравнивает разные культуры | понятное предупреждение сопоставимости | E2E P1 |
| UX-17 | экспортирует/истекает ссылка | правильный файл/новый export | E2E P1 |
| UX-18 | возвращается к прошлому сезону | явно исторический snapshot, не «сейчас» | UI |

## 2. Геометрии

| ID | Вход | Ожидаемый результат |
|---|---|---|
| GEO-01 | обычный Polygon | нормализация и сохранение |
| GEO-02 | MultiPolygon/отверстия | площадь/маска учитывают состав и holes |
| GEO-03 | самопересечение | 422, причина, ввод сохранён |
| GEO-04 | незамкнутое кольцо | детерминированная нормализация либо 422 по documented policy |
| GEO-05 | меньше 3 различных вершин/нулевая площадь | 422 |
| GEO-06 | lat/lon вне границ, NaN/Infinity | 422/400, без тяжёлых вычислений |
| GEO-07 | слишком большая площадь/число вершин | 422 с фактическим лимитом |
| GEO-08 | антимеридиан | корректное split либо понятное unsupported, не глобальный bbox |
| GEO-09 | поле меньше пикселя MODIS | coarse-resolution flag, не точная полевая оценка |
| GEO-10 | полигон за пределами cropland | предупреждение применимости, разрешён ручной выбор |
| GEO-11 | карта генерализует сложный контур | ingestion использует оригинальную геометрию |
| GEO-12 | смена bbox/региона во время discovery | отмена/изоляция результата старого запроса |

## 3. Данные и интеграции

| ID | Случай | Требуемое поведение |
|---|---|---|
| DATA-01 | текущие train/test | профиль совпадает с audit, 3 112 target mask |
| DATA-02 | не-UTF8/плохой delimiter/отсутствующий столбец | schema error с именем, не молчаливое угадывание |
| DATA-03 | дубликат (AOI,date) с разными значениями | reject/report conflict |
| DATA-04 | год/DOY отсутствует или не совпадает | derive from date + warning о несовпадении |
| DATA-05 | leap day, годовая граница, длинный межсезонный gap | календарно правильные расстояния, без склейки сезонов |
| DATA-06 | все динамические признаки скрытой строки null | pipeline даёт finite prediction через честный fallback |
| DATA-07 | природный gap и synthetic=False | не включать в submission |
| DATA-08 | NDVI вне [−1,1], огромный EVI | raw сохранён, clean quality flag; metric target не переписан |
| DATA-09 | отрицательные осадки | малый epsilon normalizes с флагом, большие invalid |
| DATA-10 | несколько сенсоров в день | raw отдельно, fusion policy versioned |
| DATA-11 | весь полигон в облаках | no suitable pixels, не NDVI=0 |
| DATA-12 | S2 за 2010 год | source_not_available для периода, доступные другие источники |
| DATA-13 | MODIS composite | период/дата доступности сохранены, не 16 независимых observations |
| DATA-14 | нет weather, спутник есть | partial + NDVI, причины погоды не утверждаются |
| DATA-15 | weather есть, спутника нет | no_data/insufficient_support, не здоровое поле |
| DATA-16 | 429/Retry-After | bounded backoff, progress, UI не зависает |
| DATA-17 | timeout/500 одной коллекции | retry/partial с конкретным source |
| DATA-18 | auth revoked/provider schema changed | понятная неретрайная ошибка, никаких фиктивных данных |
| DATA-19 | свежий и старый источник одновременно | provenance каждого snapshot, не общий fake updated_at |
| DATA-20 | одинаковый запрос после изменения geometry/config/model | новый cache key |
| DATA-21 | расхождение источников | quality/disagreement signal и видимые raw |
| DATA-22 | неизвестная культура/регион | unknown/fallback и confidence, не crash |

## 4. ML и оценка

| ID | Случай | Проверка |
|---|---|---|
| ML-01 | одна скрытая точка между двумя | M0 среднее; M1 вес по календарному времени |
| ML-02 | несколько последовательных gaps | не использовать восстановленные точки как true labels |
| ML-03 | только левый/правый сосед | явный edge fallback, origin extrapolated/fallback |
| ML-04 | вообще нет соседей | finite train-prior для submission; low confidence/unavailable live |
| ML-05 | новый AOI/последний год | отдельные метрики holdout и fallback |
| ML-06 | изменение скрытых целей после masking | features/predictions неизменны |
| ML-07 | status/zscore присутствуют в train | не входят в reconstruction features |
| ML-08 | n_reference_years/std отсутствуют | zscore=null, insufficient_reference |
| ML-09 | std=0/почти 0 | не бесконечный z; degenerate_reference |
| ML-10 | z ровно −1 / −2 | −1 normal, −2 stress по исходным границам |
| ML-11 | один выброс на фоне нормальных точек | single alert/quality, не доказанный длительный стресс |
| ML-12 | несколько отрицательных наблюдений | period с duration и независимым evidence count |
| ML-13 | длинная интерполяция ниже нормы | confidence снижена, нет вымышленных observed confirmations |
| ML-14 | сезонная уборка | альтернативная гипотеза, не автоматический диагноз засухи |
| ML-15 | отрицательный сигнал + дождей нет | plausible weather stress, evidence и ограничения |
| ML-16 | realtime использует правого соседа | тест должен обнаружить запрещённый future access |
| ML-17 | интервалы не откалиброваны | null, not_calibrated, никакой случайной полосы |
| ML-18 | разные masks/models сравниваются | experiment runner запрещает некорректную сводную comparison |
| ML-19 | RMSE 0/0,02/0,05/0,08/≥0,10 | GapScore 30/24/15/6/0 |
| ML-20 | private test labels отсутствуют | не вычисляется fake test RMSE |
| ML-21 | shuffle входных строк | predictions по ключам одинаковы |
| ML-22 | другая серия добавлена к локальному интерполятору | нет cross-AOI leakage |
| ML-23 | checkpoint/schema/hash несовместимы | deterministic error или явно выбранный baseline |
| ML-24 | worker против CLI | численно согласованные daily estimates |

## 5. Submission

| ID | Проверка | Результат |
|---|---|---|
| SUB-01 | текущий test | 3 112 строк, точные ключи mask=True |
| SUB-02 | другая длина test | count выведен из mask, не захардкожен |
| SUB-03 | лишняя/пропущенная/дублированная строка | validator fail |
| SUB-04 | NaN/inf/string prediction | fail с ключом |
| SUB-05 | pandas index/лишние columns | fail |
| SUB-06 | нет synthetic gaps | header-only + явный отчёт |
| SUB-07 | два одинаковых запуска | совпадение результатов/manifest policy |
| SUB-08 | процесс упал во время записи | нет частично опубликованного submission |

## 6. Очереди, безопасность, эксплуатация

| ID | Случай | Требуемое поведение |
|---|---|---|
| OPS-01 | duplicate delivery Celery | одна финальная публикация |
| OPS-02 | падение worker | heartbeat/reconciliation, bounded retry |
| OPS-03 | cancel queued/running/terminal | согласованная state machine |
| OPS-04 | cancel и completion одновременно | транзакционное правило, нет двух противоречивых terminal states |
| OPS-05 | БД/Redis временно недоступны | readiness fail, понятный retry, нет потери persisted run |
| OPS-06 | ID другого workspace | доступ закрыт для detail/job/export/download |
| OPS-07 | mutation без CSRF | reject |
| OPS-08 | guest session expired | недоступны private results, UI предлагает новую сессию |
| OPS-09 | произвольный URL/путь/модель во входе | SSRF/path traversal/deserialization отвергнуты |
| OPS-10 | source text содержит HTML/script | текст экранирован |
| OPS-11 | export user label начинается с формулы | безопасный CSV label |
| OPS-12 | invalid Idempotency-Key body reuse | 409, без новой операции |
| OPS-13 | fresh clone + docker compose | приложение/миграции/артефакт запускаются по README |
| OPS-14 | batch без сети/БД | успешно работает с локальным artifact |
| OPS-15 | квоты исчерпаны | 429/422, retry_after/limits видны |

## 7. Frontend, Ascend, доступность

| ID | Случай | Проверка |
|---|---|---|
| FE-QA-01 | 360/390/768/1440/1920 px | нет перекрытий controls, graph/table доступны |
| FE-QA-02 | keyboard-only | регион/полигон/анализ/аномалия/экспорт проходимы |
| FE-QA-03 | screenreader/200% zoom | semantic labels, focus и читаемость |
| FE-QA-04 | reduced motion | планета статична, Lenis отключён, смысл сохранён |
| FE-QA-05 | WebGL disabled/context lost/GLB failed | poster и действующий CTA |
| FE-QA-06 | repeated landing↔app/StrictMode | нет дублирования canvas/RAF/listeners и утечек |
| FE-QA-07 | hidden tab/offscreen | остановка animation work |
| FE-QA-08 | tiles API недоступен | доступна геометрия/табличная альтернатива |
| FE-QA-09 | поздний ответ/range changes | не смешиваются run/даты |
| FE-QA-10 | null values | «нет данных», разрыв линии, не 0 |
| FE-QA-11 | frontend в production | mocks отключены; GetLayers provenance существует |
| FE-QA-12 | график 15-летней истории | отзывчивый zoom/brush, аномалии не теряются |
| FE-QA-13 | no-JS marketing | заголовок/CTA видны |
| FE-QA-14 | все navigation/CTA | нет placeholder ссылок и ложных переходов |

## 8. Стратегия тестирования

Unit: чистая математика, masks, schemas, intervals, state transitions. Integration: PostGIS/DRF/workspace/idempotency/storage/providers с записанными fixtures. Contract: response-schema и enums. E2E: ключевые пользовательские пути. Live smoke: ограниченный набор реальных запросов с датой/провайдером; не запускать дорогое многолетнее скачивание в каждом CI.

Финальное доказательство: протокол с ID, status, командой/окружением, датой и ссылкой на артефакт. Наличие тест-кейса в этом документе не означает, что он уже пройден. Не писать тесты, которые только повторяют структуру JSX; проверять смысл действий и вычислений.
