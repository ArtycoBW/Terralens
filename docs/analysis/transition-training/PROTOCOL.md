# Переходы NDVI: дополнение после отклонённого расширения train

Расширение train без новых признаков дало +0,58% points/+0,44% blocks,
выигрыш в3/5 folds и не прошло прежний порог. Этот результат сохранён в
`../expanded-training/development-decision.json`; параметры того опыта
не изменяются. Значения private ground truth ещё не читались.

Следующая и последняя гипотеза этого этапа: расширенный train + семь
локальных признаков: left/right projected, их disagreement, изменение
наклонов, PCHIP estimate/curvature и отличие от linear estimate. PCHIP
строится только по видимым clean observations внутри одного поля/сезона/
непрерывного crop segment; экстраполяция отключена. Края без опоры — NaN.
Теперь85 features; ensemble seeds42/107/211,400depth5, маски и все
гиперпараметры остаются прежними. Новый feature contract требует schema4;
старые артефактыv1–v3 должны работать с прежними predictions.

Пять outer validation folds, 21 AOI до2024, маски42/137 совпадают с
расширенным экспериментом. Global fit в каждом fold исключает все годы
его validation AOI и прежние пять calibration AOI. Final fit при принятии:
34 AOI/2010–2024; calibration отдельно по5 AOI, seed991,90%.

Условия development не ослабляются: ≥1% pooled point gain, blocks не хуже
baseline131aee618934151e, point gain в≥4/5 folds, положительная нижняя
граница95% AOI-bootstrap3000/seed42. Оценить и сравнение с expanded без
новых признаков для разделения эффекта данных/формы. Это development после
просмотра прежних опытов, не новая слепая оценка.

Только если кандидат пройдёт эти условия: один final fit, новая calibration,
фиксация model/prediction hashes, затем один assessment на новых20AOI/2323
контрольных строках по предоставленным ответам. После чтения labels
параметры не меняются. При внешнем RMSE хуже baseline не публиковать модель.
Отдельно проверить warm CPU latency≤1.25 исходного legacy pipeline,
standalone/offline, backend parity, masks/shuffle/границы/JSON. При провале
кандидата оставить старые веса и применить только доказанное ускорение.
