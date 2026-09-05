# Улучшение восстановления: выбор на development и повторная диагностика

По зафиксированному development-протоколу выбран **`local_mixed`**: pooled RMSE **0,072445** для отдельных точек и **0,101430** для календарных блоков. Предыдущая модель на тех же контрольных ключах получила **0,079287 / 0,129204**. Снижение — **8,63% / 21,50%**. Дополнительное смешивание с исторической моделью отклонено по заранее заданному условию отсутствия ухудшения обеих метрик.

Кандидат выбран только по development. После фиксации параметров выполнены обучение, калибровка и повторная диагностика; артефакт `e156fcdadef59ed0` скопирован в `ml/artifacts/final`. Официальный test RMSE неизвестен.

## Зафиксированный протокол

[Протокол](protocol.md) подготовлен до расчёта шести вариантов. Сохранены прежние 21 selection AOI, годы до 2024, пять GroupKFold по AOI и validation mask seeds 42/137. Все маскируемые динамические поля, включая цель, сенсоры, погоду и готовую климатологию, исключаются до пересчёта признаков. Оценка использует неизменённые y_true.

Основной выбор: минимальный pooled `development_points` RMSE **среди кандидатов, у которых pooled `development_blocks` RMSE не выше `previous`**. После выбора признаков допускается ровно одно ранее зафиксированное правило смешивания M4/M5, без подбора новых порогов или весов. Это правило принимается, только если не ухудшает ни points, ни blocks относительно выбранного кандидата.

Восемь AOI старого holdout по-прежнему полностью исключены из выбора. Calibration, assessment и temporal значения не использовались для выбора кандидата или правила смешивания. После фиксации выбора выполнен полный прогон. Эти выборки уже просматривались в предыдущей работе; повторные оценки являются диагностикой на знакомых данных, а не новым слепым holdout.

Точный состав folds, конфигурации и SHA-256 исходного train: [split_manifest.json](split_manifest.json). Финальная конфигурация выбора: [selected_config.json](selected_config.json). Hashes development masks и неизменяемого файла прогнозов: [selection_evidence.json](selection_evidence.json).

## Шесть вариантов

| Кандидат | Points RMSE, N=4482 | Blocks RMSE, N=4430 | Прошёл ограничение по blocks |
|---|---:|---:|---|
| `previous` | 0.079287 | 0.129204 | да |
| `local_160` | 0.076876 | 0.133972 | нет |
| `local_400` | 0.074953 | 0.134162 | нет |
| `local_repeated` | 0.072766 | 0.124046 | да |
| `local_mixed` | 0.072445 | 0.101430 | да |
| `local_mixed_linear` | 0.073568 | 0.101267 | да |

- `previous` воспроизводит предыдущую CatBoost residual модель: 160 деревьев, M0 как база, без погоды.
- `local_160` добавляет локальные признаки и `masked_training_priors`: два ближайших пригодных наблюдения с каждой стороны, расстояния в календарных днях, локальные наклоны, линейную оценку и count/mean/std окон ±14/30/60 дней. Priors внутреннего обучающего примера рассчитываются после его маскирования. Этот вариант меняет два элемента одновременно, поэтому их индивидуальный вклад здесь не измерен.
- `local_400` увеличивает число деревьев до 400.
- `local_repeated` использует три повторения внутренних обучающих масок отдельных точек.
- `local_mixed` сохраняет три повторения и добавляет внутренние блоковые маски длиной 8/15/30/45/65 календарных дней. Validation masks остаются общими для всех кандидатов.
- `local_mixed_linear` меняет базу residual correction с M0 на линейную интерполяцию. Он немного лучше по blocks, но хуже по основной point-метрике, поэтому не выбран.

Простое добавление локальных признаков улучшает points, но у `local_160` и `local_400` ухудшает blocks. Ограничение по blocks не позволило выбрать эти варианты. Обучение на смеси точечных и блоковых пропусков дало улучшение обоих режимов. Погода не входит в выбранную модель; AOI ID не является признаком. Календарь, соседние сенсорные значения и локальные признаки вычисляются из доступного контекста внутри поля и сезона.

Полные N, RMSE, MAE, bias, p95 и локальный GapScore всех шести вариантов сохранены в [metrics_features.csv](metrics_features.csv). Низкая ошибка отдельных точек не означает надёжного восстановления произвольно длинных gaps: development block RMSE остаётся выше 0,10.

## Парное сравнение и устойчивость по полям

Скрипт `scripts/compare_reconstruction.py` сначала оставляет только `development_points` и `development_blocks`, затем требует точного совпадения ключей `scope,fold,mask_seed,anon_polygon_id,date`, y_true и gap_days. Сопоставлены **8 912 строк**, без потерь или лишних ключей; 4 482 points и 4 430 blocks относятся к 21 AOI.

Для парной разницы RMSE выполнены 3 000 bootstrap-повторов, seed=42. Пересэмплируются целые AOI, сохраняя внутри них разные сезоны и повторные маски. Положительный выигрыш означает меньшую ошибку новой модели.

| Scope | Выигрыш RMSE | 95% AOI-bootstrap интервал |
|---|---:|---:|
| Points | 0,006842 | 0,005246…0,008445 |
| Blocks | 0,027774 | 0,021308…0,034302 |

В каждом из пяти folds улучшились обе метрики:

| Fold | Points: previous → local_mixed | Blocks: previous → local_mixed |
|---|---:|---:|
| 0 | 0.079115 → 0.070767 | 0.133176 → 0.096541 |
| 1 | 0.083506 → 0.076228 | 0.123312 → 0.103990 |
| 2 | 0.076148 → 0.071088 | 0.121257 → 0.097075 |
| 3 | 0.073164 → 0.066257 | 0.127717 → 0.103555 |
| 4 | 0.083440 → 0.076756 | 0.138991 → 0.106175 |

Это development-оценки после выбора из нескольких конфигураций. Bootstrap показывает устойчивость парной разницы по имеющимся AOI, но не устраняет смещение от выбора лучшего кандидата на этой же development-выборке. Данные и поля уже использовались в предыдущем исследовании; нового географического или слепого подтверждения нет.

Полные результаты сравнения, per-fold метрики и gap-срезы: [comparison.json](comparison.json), краткие значения: [metrics_comparison.csv](metrics_comparison.csv).

## Почему дополнительный M4 route отклонён

До сравнения с новыми признаками на старых development OOF было выбрано единственное простое правило:

```text
gap_days > 30: 50% выбранной модели + 50% M4 history residual
иначе: выбранная модель
```

На старом M5 это правило снижало block RMSE с 0,129204 до 0,111492, практически не меняя points. Историческая часть оказалась полезной именно для длинных пропусков. Новый `local_mixed` уже устраняет значительную часть этой ошибки.

| Вариант | Points RMSE | Blocks RMSE |
|---|---:|---:|
| `local_mixed` | 0,072445 | 0,101430 |
| Фиксированный M4 route | 0,072391 | 0,101551 |

Смешивание ухудшает blocks на **0,000122**, поэтому нарушает установленное условие и **не принято**. 95% парные bootstrap-интервалы его выигрыша относительно `local_mixed` включают ноль для обоих scopes: points −0,000066…0,000218; blocks −0,002706…0,002542. Дополнительные веса, пороги и правила после этого сравнения не проверялись.

Решение сохранено в [decision.json](decision.json). Большие raw predictions остаются вне Git. [comparison.json](comparison.json) ссылается на сохранённый `artifacts/improvement-features/development-predictions.csv` и его SHA-256; полный прогон перезаписал обычный `predictions.csv`, сохранив неизменным этот development evidence.

## Воспроизведение development-этапа

```sh
uv run --frozen python -m terralens_ml research --config ml/configs/improvement.yaml --development-only
cp artifacts/improvement-features/predictions.csv artifacts/improvement-features/development-predictions.csv
uv run --frozen python scripts/compare_reconstruction.py \
  --baseline artifacts/research/predictions.csv \
  --candidate artifacts/improvement-features/development-predictions.csv \
  --candidate-name local_mixed \
  --secondary artifacts/research/predictions.csv \
  --output artifacts/improvement-comparison
```

После development-команды файл `predictions.csv` следует сохранить как `development-predictions.csv` до запуска полного исследования. Число кандидатов, параметры и mask seeds задаёт `ml/configs/improvement.yaml`. Скрипт сравнения не обучает модели и не выбирает веса или пороги.

## Финальная калибровка и повторная диагностика

После фиксации `local_mixed` выполнен полный research по той же конфигурации. Проверено точное равенство всех development DataFrame до и после полного прогона: **53 472 строки для шести кандидатов, по 8 912 на каждого**. Изменений параметров, дополнительных ансамблей и подбора по диагностическим результатам не было.

Артефакт обучен на 21 selection AOI до 2024 года; пять calibration AOI и пять assessment AOI не включены в глобальный fit. Восемь старых holdout AOI исключены. Полный training_scope, число обучающих примеров, SHA-256 manifest/model/source/dependency lock/input, hashes split и всех masks сохранены в [diagnostic_evidence.json](diagnostic_evidence.json).

**Assessment и temporal данные уже просматривались ранее. Эти результаты — повторная диагностика фиксированной модели; они не являются новым слепым подтверждением качества.**

| Scope | N | RMSE | Покрытие 90% интервала | Средняя ширина NDVI |
|---|---:|---:|---:|---:|
| assessment_points | 511 | 0.076274 | 91.59% | 0.233040 |
| assessment_blocks | 514 | 0.095032 | 90.86% | 0.334469 |
| temporal_points | 282 | 0.060244 | 95.04% | 0.230918 |
| temporal_blocks | 286 | 0.086499 | 93.36% | 0.333012 |

Калибровка использует 1 173 residual на пяти отдельных AOI: 551 point и 622 block примера. Метод — empirical absolute residual quantiles, nominal level=90%, группы short/long/edge/prior. При N<100 используется pooled fallback. Radius: short 0,114318; long 0,149942; prior 0,202491; edge — pooled 0,143575. Это калибровка ошибки восстановления, а не дисперсия климатологии или ошибка спутникового измерения.

Фактическое покрытие на calibration points/blocks составляет 90,74%/90,03%; эти числа проверяют саму калибровку и не считаются независимой оценкой. Точки одного AOI и повторные маски зависимы, поэтому безусловная гарантия покрытия не заявляется. Данные анонимного benchmark не подтверждают покрытие реальных регионов; live-интервалы сохраняют явную пометку domain shift.

Полный прогон создаёт candidate artifact в `artifacts/improvement-features/model`, как задано в `ml/configs/improvement.yaml`. В этой работе оба JSON-файла затем скопированы в `ml/artifacts/final`; проверено побайтовое совпадение candidate и final без повторного обучения. ID артефакта: **`e156fcdadef59ed0`**.

Для воспроизведения полного прогона после фиксации development-решения:

```sh
uv run --frozen python -m terralens_ml research --config ml/configs/improvement.yaml
cp artifacts/improvement-features/model/model.json ml/artifacts/final/model.json
cp artifacts/improvement-features/model/manifest.json ml/artifacts/final/manifest.json
```

Новый запуск создаёт собственные timestamps и manifest hash. Для регистрации candidate в настроенном backend можно явно указать его путь:

```sh
uv run --frozen python backend/manage.py register_model --manifest artifacts/improvement-features/model/manifest.json
```

Регистрация требует работающей БД и сохраняет собственную неизменяемую копию модели. Копирование файлов в репозитории и переключение backend registry являются отдельными действиями.


## Проверки обновлённого артефакта

- **114 tests passed**: маски и скрытые признаки, crop boundaries, неоднородные индексы, default-конфигурация research, backend/ML parity, API, очередь и экспорт. 31 предупреждение относится к rasterio/affine.
- Ruff check/format и проверка diff прошли. Hash текущего ML source совпадает с manifest.
- Два batch-инференса в отдельном окружении без Django/Celery/Redis, с запрещёнными socket connections, дали побайтно одинаковый submission. Он совпадает с `deliverables/submission.csv`: 3 112 строк, SHA-256 `afb13edc4b3949a87bf2fc4a37c65591ac1ebd8d489b967a69cacd975f246d00`. [Offline evidence](offline-evidence.json).
- Локальный Docker API готов к запросам, registry активировал новую модель; прежние версии сохранены для существующих анализов. Batch внутри Linux-контейнера дал тот же SHA-256, что локальный macOS и отдельное ML-окружение. [Verification](verification.json).
- После проверки research восстановлена совместимость с кандидатом без явно указанного algorithm. Обновлены только метаданные артефакта; веса и результаты остались побайтно прежними. [Metadata refresh](metadata-refresh.json).

Повторный расчёт сохранённых реальных снимков Потсдама и Севильи прошёл с запрещённой сетью. В обоих рядах сохранены два наблюдаемых дня и восстановлены девять из 11 дат; итоговые статусы — normal / insufficient_data. Это проверка адаптера на прежних снимках, без новой загрузки спутниковых данных и без независимых истинных NDVI для gaps. [Live smoke evidence](live-smoke/offline-evidence.json).
