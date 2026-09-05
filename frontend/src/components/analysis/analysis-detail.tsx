"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  allPages,
  number,
  label,
  terminalRun,
  type Run,
  type Point,
  type Anomaly,
  type Polygon,
  type Schema,
} from "@/lib/api";
import { ndviOption, chartBase } from "@/lib/charts";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  ErrorNotice,
  Status,
  JsonDetails,
} from "@/components/workspace/common";
import { JobProgress } from "@/components/workspace/job-progress";
import { Explanation, readableMessage } from "./explanation";
import { Exports } from "./exports";
const Chart = dynamic(() => import("./chart").then((m) => m.Chart), {
  ssr: false,
  loading: () => <div className="empty">Загружаем график…</div>,
});
export function AnalysisDetail({ id }: { id: string }) {
  const client = useQueryClient();
  const run = useQuery({
    queryKey: ["run", id],
    queryFn: ({ signal }) => api<Run>(`analyses/${id}`, { signal }),
    refetchInterval: (q) =>
      q.state.data && terminalRun(q.state.data.state) ? false : 2000,
  });
  const complete =
    !!run.data && ["completed", "partial", "no_data"].includes(run.data.state);
  const points = useQuery({
    queryKey: ["series", id],
    queryFn: ({ signal }) =>
      allPages<Point>(`analyses/${id}/series?resolution=daily`, signal),
    enabled: complete,
  });
  const anomalies = useQuery({
    queryKey: ["anomalies", id],
    queryFn: ({ signal }) =>
      allPages<Anomaly>(`analyses/${id}/anomalies`, signal),
    enabled: complete,
  });
  const quality = useQuery({
    queryKey: ["quality", id],
    queryFn: () => api<Schema["QualityResponse"]>(`analyses/${id}/quality`),
    enabled: complete,
  });
  const polygon = useQuery({
    queryKey: ["polygon", run.data?.polygon_id],
    queryFn: () => api<Polygon>(`polygons/${run.data!.polygon_id}`),
    enabled: !!run.data,
  });
  const [tab, setTab] = useState("dynamics");
  const [range, setRange] = useState<[string, string]>(),
    [date, setDate] = useState(""),
    [severity, setSeverity] = useState("");
  const chart = useMemo(
    () => ndviOption(points.data || [], anomalies.data || [], range),
    [points.data, anomalies.data, range],
  );
  const selected = points.data?.find((p) => p.date === date);
  const visible = anomalies.data?.filter(
    (a) => !severity || a.severity === severity,
  );
  if (run.isPending) return <div className="page-pad">Загружаем анализ…</div>;
  if (!run.data)
    return (
      <div className="page-pad">
        <ErrorNotice error={run.error} />
        <Link href="/app/polygons">Вернуться к полям</Link>
      </div>
    );
  const r = run.data,
    s = r.summary;
  return (
    <div className="page-pad">
      <Link className="small muted" href={`/app/polygons/${r.polygon_id}`}>
        ← Паспорт поля
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow mt-5">
            Спутниковая аналитика / версия контура {r.polygon_version}
          </p>
          <h1>{polygon.data?.name || "Анализ поля"}</h1>
          <p className="small muted">
            {r.period.from} — {r.period.to} · Ретроспективный режим
          </p>
        </div>
        <Status value={r.state} />
      </div>
      <ErrorNotice
        error={run.error || points.error || anomalies.error || quality.error}
      />
      {polygon.data && polygon.data.current_version !== r.polygon_version && (
        <div className="notice mb-5">
          Этот анализ относится к предыдущей версии контура. Геометрия поля с
          тех пор изменилась.
        </div>
      )}
      {r.job_id && (!complete || r.state === "failed") && (
        <JobProgress
          id={r.job_id}
          onRetry={() => client.invalidateQueries({ queryKey: ["run", id] })}
        />
      )}
      <div className="stack">
        {r.warnings.map((w, i) => (
          <div className="notice" key={i}>
            {readableMessage(w)}
          </div>
        ))}
      </div>
      {s && (
        <div className="metrics mt-5">
          <div className="panel">
            <p className="metric-label">Последняя оценка NDVI</p>
            <p className="metric">{number(s.latest_estimate?.value)}</p>
            <p className="micro muted">
              {s.latest_estimate
                ? `${s.latest_estimate.date} · ${label[s.latest_estimate.origin]}`
                : "Нет пригодных значений"}
            </p>
          </div>
          <div className="panel">
            <p className="metric-label">Покрытие наблюдениями</p>
            <p className="metric">
              {number(s.observed_coverage_ratio * 100, 1)}
              <span className="text-base">%</span>
            </p>
            <p className="micro muted">
              {s.observed_days} из {s.total_days} дней после QA
            </p>
          </div>
          <div className="panel">
            <p className="metric-label">Максимальный пропуск</p>
            <p className="metric">
              {s.longest_gap_days}
              <span className="text-base"> дн.</span>
            </p>
            <p className="micro muted">
              Восстановлено {s.reconstructed_days} дней
            </p>
          </div>
          <div className="panel">
            <p className="metric-label">Состояние за период</p>
            <div className="my-3">
              <Status value={s.overall_status} />
            </div>
            <p className="micro muted">Сигналов: {s.anomaly_period_count}</p>
          </div>
        </div>
      )}
      {complete && (
        <Tabs value={tab} onValueChange={setTab} className="mt-5">
          <TabsList className="w-full justify-start overflow-auto">
            <TabsTrigger value="dynamics">Динамика NDVI</TabsTrigger>
            <TabsTrigger value="anomalies">
              Аномалии ({anomalies.data?.length ?? "…"})
            </TabsTrigger>
            <TabsTrigger value="quality">Качество и источники</TabsTrigger>
            <TabsTrigger value="export">Экспорт</TabsTrigger>
          </TabsList>
          <TabsContent value="dynamics">
            <section className="panel">
              <div className="page-heading">
                <div>
                  <h2>Растительность в контексте сезона</h2>
                  <p className="small muted">
                    Точки — спутниковые наблюдения; пунктир — восстановленный
                    ряд
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRange(undefined)}
                >
                  Сбросить масштаб
                </Button>
              </div>
              {points.isPending ? (
                <div className="empty">Загружаем ежедневный ряд…</div>
              ) : !points.data?.length ? (
                <div className="empty">Нет значений за этот период</div>
              ) : (
                <Chart option={chart} onDate={setDate} />
              )}
              <p className="micro muted">
                Разброс сезонной нормы (±σ) и интервал прогноза — разные
                величины. Интервал откалиброван на benchmark; для реальных
                территорий покрытие не подтверждено.
              </p>
              <div className="actions mt-5">
                <label className="field">
                  Выбрать дату (клавиатура)
                  <input
                    type="date"
                    min={r.period.from}
                    max={r.period.to}
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                  />
                </label>
                {selected && (
                  <p className="small">
                    {label[selected.origin]} · NDVI{" "}
                    {number(selected.reconstructed)} ·{" "}
                    {selected.source_sensor || "Источник отсутствует"} · пропуск{" "}
                    {selected.gap_days} дн.
                  </p>
                )}
              </div>
              {selected && (
                <JsonDetails
                  value={selected}
                  title={`Все значения за ${selected.date}`}
                />
              )}
            </section>
            <section className="panel mt-5">
              <h2>Температура и осадки</h2>
              <p className="small muted">
                Погода в центре поля · °C и мм на отдельных осях
              </p>
              {points.data && (
                <Chart
                  height={300}
                  option={{
                    ...chartBase,
                    xAxis: {
                      ...chartBase.xAxis,
                      data: points.data.map((p) => p.date),
                    },
                    yAxis: [
                      { ...chartBase.yAxis, name: "°C" },
                      {
                        ...chartBase.yAxis,
                        name: "мм",
                        splitLine: { show: false },
                      },
                    ],
                    series: [
                      {
                        name: "Температура, °C",
                        type: "line",
                        data: points.data.map((p) => p.weather.temperature_c),
                        showSymbol: false,
                        connectNulls: false,
                        itemStyle: { color: "#efba7a" },
                      },
                      {
                        name: "Осадки, мм",
                        type: "bar",
                        yAxisIndex: 1,
                        data: points.data.map(
                          (p) => p.weather.precipitation_mm,
                        ),
                        itemStyle: { color: "#769dda" },
                      },
                    ],
                  }}
                />
              )}
            </section>
            <section className="panel mt-5">
              <h2>Значения и наличие источников</h2>
              <p className="small muted">
                Полный ежедневный ряд; «—» означает отсутствие данных
              </p>
              <div className="scroll-table max-h-[440px]">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Дата</th>
                      <th>Raw</th>
                      <th>После QA</th>
                      <th>Оценка</th>
                      <th>Происхождение</th>
                      <th>S2</th>
                      <th>Landsat</th>
                      <th>Норма</th>
                      <th>Z-score</th>
                      <th>Флаги</th>
                    </tr>
                  </thead>
                  <tbody>
                    {points.data?.map((p) => (
                      <tr key={p.date} data-selected={p.date === date}>
                        <td>
                          <button
                            className="text-primary"
                            onClick={() => setDate(p.date)}
                          >
                            {p.date}
                          </button>
                        </td>
                        <td>{number(p.observed_primary)}</td>
                        <td>{number(p.clean_primary)}</td>
                        <td>{number(p.reconstructed)}</td>
                        <td>{label[p.origin]}</td>
                        <td>{number(p.sensors.sentinel2)}</td>
                        <td>{number(p.sensors.landsat)}</td>
                        <td>{number(p.climatology_mean)}</td>
                        <td>{number(p.zscore)}</td>
                        <td className="micro">
                          {p.quality_flags.join(", ") || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </TabsContent>
          <TabsContent value="anomalies">
            <section className="panel stack">
              <div className="page-heading">
                <div>
                  <h2>Обнаруженные отклонения</h2>
                  <p className="small muted">
                    Алгоритмический сигнал требует проверки на месте
                  </p>
                </div>
                <label className="field">
                  Уровень
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                  >
                    <option value="">Все уровни</option>
                    <option value="stress">Стресс</option>
                    <option value="critical">Критично</option>
                  </select>
                </label>
              </div>
              {anomalies.isPending ? (
                <p>Загружаем события…</p>
              ) : !visible?.length ? (
                <div className="empty">
                  {s?.overall_status === "insufficient_data" ||
                  r.state === "no_data"
                    ? "Недостаточно данных для надёжного поиска аномалий"
                    : severity
                      ? "Нет событий выбранного уровня"
                      : "Аномалий по текущим правилам не найдено"}
                </div>
              ) : (
                visible.map((a) => (
                  <article className="anomaly-card" key={a.id}>
                    <div className="actions">
                      <Status value={a.severity} />
                      <span className="pill">
                        Уверенность: {label[a.confidence]}
                      </span>
                      <span className="micro muted">
                        {a.event_kind === "single_observation_alert"
                          ? "Единичное наблюдение"
                          : "Устойчивый период"}
                      </span>
                    </div>
                    <h3 className="mt-3">
                      {a.start_date} — {a.end_date}
                    </h3>
                    <p className="small muted">
                      Пик: {a.peak_date} · Z-score {number(a.min_z)} ·
                      Подтверждающих наблюдений: {a.observed_evidence_count} ·
                      Восстановлено {number(a.reconstructed_fraction * 100, 1)}%
                    </p>
                    <Explanation value={a.explanation} />
                    <JsonDetails
                      value={a.causes}
                      title="Возможные объяснения (гипотезы)"
                    />
                    <p className="micro muted mt-2">
                      Проверьте агротехнические работы, культуру и полевые
                      наблюдения. По спутниковому сигналу нельзя установить
                      причину однозначно.
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3"
                      onClick={() => {
                        setRange([a.start_date, a.end_date]);
                        setDate(a.peak_date);
                        setTab("dynamics");
                      }}
                    >
                      Показать период на графике
                    </Button>
                  </article>
                ))
              )}
            </section>
          </TabsContent>
          <TabsContent value="quality">
            <section className="panel stack">
              <h2>Достоверность результата</h2>
              <p className="small muted">
                Модель {r.model_version} · Конфигурация {r.config_version} ·
                Результат {r.result_version || "не опубликован"}
              </p>
              {quality.data && (
                <>
                  <p className="small">
                    {quality.data.observed_days_definition}
                  </p>
                  <JsonDetails
                    value={quality.data.exclusions}
                    title="Причины исключения наблюдений"
                  />
                  <JsonDetails
                    value={quality.data.reference}
                    title="История для сезонной нормы"
                  />
                  <JsonDetails
                    value={quality.data.model}
                    title="Модель и ограничения"
                  />
                </>
              )}
              <h3>Снимки источников</h3>
              {r.snapshots.map((snapshot) => (
                <div key={snapshot.id} className="history-row">
                  <div>
                    <p>{snapshot.provider}</p>
                    <p className="micro muted">
                      Получено{" "}
                      {new Date(snapshot.retrieved_at).toLocaleString("ru-RU")}
                    </p>
                    <p className="micro muted break-all">
                      SHA-256 {snapshot.checksum}
                    </p>
                  </div>
                  <Status value={snapshot.status} />
                </div>
              ))}
              <p className="micro muted">
                Анализ относится к сохранённым снимкам данных. Повтор с
                обновлением источников может дать другой результат.
              </p>
            </section>
          </TabsContent>
          <TabsContent value="export">
            <section className="panel stack">
              <h2>Экспорт исследования</h2>
              <p className="small muted">
                {r.period.from} — {r.period.to} · Это данные реального поля;
                конкурсный submission формируется отдельно.
              </p>
              <Exports runId={id} />
            </section>
          </TabsContent>
        </Tabs>
      )}
      {!complete && terminalRun(r.state) && (
        <div className="empty mt-5">
          Результат не опубликован. Откройте паспорт поля для нового анализа.
        </div>
      )}
    </div>
  );
}
