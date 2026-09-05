"use client";
import { DateField } from "@/components/ui/date-field";
import { Badge } from "@/components/ui/badge";

import { SelectControl, SelectOption } from "@/components/ui/select-control";

import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import { Label } from "@/components/ui/label";

import Link from "next/link";
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
export function AnalysisDetail({ id }: { id: string }) {
  const client = useQueryClient();
  // Load the chart while the worker runs, so publication needs no second loader.
  const chartModule = useQuery({
    queryKey: ["analysis-chart-module"],
    queryFn: async () => (await import("./chart")).Chart,
    staleTime: Infinity,
    retry: 1,
  });
  const Chart = chartModule.data;
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
  const preparingResult =
    complete &&
    (points.isPending || anomalies.isPending || chartModule.isPending);
  const selected = points.data?.find((p) => p.date === date);
  const visible = anomalies.data?.filter(
    (a) => !severity || a.severity === severity,
  );
  if (run.isPending)
    return (
      <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
        Загружаем анализ…
      </div>
    );
  if (!run.data)
    return (
      <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
        <ErrorNotice error={run.error} />
        <Link href="/app/polygons">Вернуться к полям</Link>
      </div>
    );
  const r = run.data,
    s = r.summary;
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <Link
        className="text-sm leading-relaxed text-muted-foreground"
        href={`/app/polygons/${r.polygon_id}`}
      >
        ← Паспорт поля
      </Link>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground mt-5">
            Спутниковая аналитика / версия контура {r.polygon_version}
          </p>
          <h1>{polygon.data?.name || "Анализ поля"}</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {r.period.from} — {r.period.to} · Ретроспективный режим
          </p>
        </div>
        <Status value={r.state} />
      </div>
      <ErrorNotice
        error={
          run.error ||
          points.error ||
          anomalies.error ||
          quality.error ||
          chartModule.error
        }
      />
      {polygon.data && polygon.data.current_version !== r.polygon_version && (
        <div className="rounded-md border border-warning/25 bg-warning/5 px-4 py-3 text-sm leading-relaxed break-words text-warning mb-5">
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
      {preparingResult && (
        <div
          role="status"
          className="rounded-md border border-border bg-secondary/30 p-4 text-sm text-muted-foreground"
        >
          Анализ рассчитан. Подготавливаем результат…
        </div>
      )}
      {chartModule.isError && (
        <Button variant="outline" onClick={() => chartModule.refetch()}>
          Повторить загрузку графика
        </Button>
      )}
      <div className="grid min-w-0 gap-4">
        {r.warnings.map((w, i) => (
          <div
            className="rounded-md border border-warning/25 bg-warning/5 px-4 py-3 text-sm leading-relaxed break-words text-warning"
            key={i}
          >
            {readableMessage(w)}
          </div>
        ))}
      </div>
      {s && !preparingResult && (
        <div className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4 [&>div]:border-0 [&>div]:border-l [&>div]:border-border [&>div]:bg-transparent [&>div]:py-3 mt-5">
          <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
            <p className="text-sm text-muted-foreground">
              Последняя оценка NDVI
            </p>
            <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em]">
              {number(s.latest_estimate?.value)}
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {s.latest_estimate
                ? `${s.latest_estimate.date} · ${label[s.latest_estimate.origin]}`
                : "Нет пригодных значений"}
            </p>
          </div>
          <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
            <p className="text-sm text-muted-foreground">
              Покрытие наблюдениями
            </p>
            <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em]">
              {number(s.observed_coverage_ratio * 100, 1)}
              <span className="text-base">%</span>
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {s.observed_days} из {s.total_days} дней после QA
            </p>
          </div>
          <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
            <p className="text-sm text-muted-foreground">
              Максимальный пропуск
            </p>
            <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em]">
              {s.longest_gap_days}
              <span className="text-base"> дн.</span>
            </p>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Восстановлено {s.reconstructed_days} дней
            </p>
          </div>
          <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
            <p className="text-sm text-muted-foreground">Состояние за период</p>
            <div className="my-3">
              <Status value={s.overall_status} />
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Сигналов: {s.anomaly_period_count}
            </p>
          </div>
        </div>
      )}
      {complete && !preparingResult && (
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
            <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
              <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
                <div>
                  <h2>Растительность в контексте сезона</h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
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
              {!points.data?.length ? (
                <div className="flex min-h-40 items-center justify-center rounded-md border border-dashed border-border p-6 text-sm text-muted-foreground">
                  {points.isError
                    ? "Ежедневный ряд недоступен"
                    : "Нет значений за этот период"}
                </div>
              ) : Chart ? (
                <Chart option={chart} onDate={setDate} />
              ) : null}
              <p className="text-xs leading-relaxed text-muted-foreground">
                Разброс сезонной нормы (±σ) и интервал прогноза — разные
                величины. Интервал откалиброван на benchmark; для реальных
                территорий покрытие не подтверждено.
              </p>
              <div className="flex flex-wrap items-end gap-3 mt-5">
                <DateField
                  label="Выбрать дату (клавиатура)"
                  min={r.period.from}
                  max={r.period.to}
                  value={date}
                  onValueChange={(value) => setDate(value)}
                />
                {selected && (
                  <p className="text-sm leading-relaxed">
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
            <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 mt-5">
              <h2>Температура и осадки</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Погода в центре поля · °C и мм на отдельных осях
              </p>
              {points.data && Chart && (
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
            <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 mt-5">
              <h2>Значения и наличие источников</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Полный ежедневный ряд; «—» означает отсутствие данных
              </p>
              <div className="max-w-full overflow-auto max-h-[440px]">
                <Table className="text-sm">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Дата</TableHead>
                      <TableHead>Raw</TableHead>
                      <TableHead>После QA</TableHead>
                      <TableHead>Оценка</TableHead>
                      <TableHead>Происхождение</TableHead>
                      <TableHead>S2</TableHead>
                      <TableHead>Landsat</TableHead>
                      <TableHead>Норма</TableHead>
                      <TableHead>Z-score</TableHead>
                      <TableHead>Флаги</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {points.data?.map((p) => (
                      <TableRow key={p.date} data-selected={p.date === date}>
                        <TableCell>
                          <Button
                            variant="ghost"
                            className="text-primary"
                            onClick={() => setDate(p.date)}
                          >
                            {p.date}
                          </Button>
                        </TableCell>
                        <TableCell>{number(p.observed_primary)}</TableCell>
                        <TableCell>{number(p.clean_primary)}</TableCell>
                        <TableCell>{number(p.reconstructed)}</TableCell>
                        <TableCell>{label[p.origin]}</TableCell>
                        <TableCell>{number(p.sensors.sentinel2)}</TableCell>
                        <TableCell>{number(p.sensors.landsat)}</TableCell>
                        <TableCell>{number(p.climatology_mean)}</TableCell>
                        <TableCell>{number(p.zscore)}</TableCell>
                        <TableCell className="text-xs leading-relaxed">
                          {p.quality_flags.join(", ") || "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          </TabsContent>
          <TabsContent value="anomalies">
            <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
              <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
                <div>
                  <h2>Обнаруженные отклонения</h2>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Алгоритмический сигнал требует проверки на месте
                  </p>
                </div>
                <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                  Уровень
                  <SelectControl
                    value={severity}
                    onValueChange={(value) => setSeverity(value)}
                  >
                    <SelectOption value="">Все уровни</SelectOption>
                    <SelectOption value="stress">Стресс</SelectOption>
                    <SelectOption value="critical">Критично</SelectOption>
                  </SelectControl>
                </Label>
              </div>
              {anomalies.isPending ? (
                <p>Загружаем события…</p>
              ) : !visible?.length ? (
                <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
                  {s?.overall_status === "insufficient_data" ||
                  r.state === "no_data"
                    ? "Недостаточно данных для надёжного поиска аномалий"
                    : severity
                      ? "Нет событий выбранного уровня"
                      : "Аномалий по текущим правилам не найдено"}
                </div>
              ) : (
                visible.map((a) => (
                  <article
                    className="rounded-md border border-border bg-secondary/20 p-5"
                    key={a.id}
                  >
                    <div className="flex flex-wrap items-end gap-3">
                      <Status value={a.severity} />
                      <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
                        Уверенность: {label[a.confidence]}
                      </Badge>
                      <span className="text-xs leading-relaxed text-muted-foreground">
                        {a.event_kind === "single_observation_alert"
                          ? "Единичное наблюдение"
                          : "Устойчивый период"}
                      </span>
                    </div>
                    <h3 className="mt-3">
                      {a.start_date} — {a.end_date}
                    </h3>
                    <p className="text-sm leading-relaxed text-muted-foreground">
                      Пик: {a.peak_date} · Z-score {number(a.min_z)} ·
                      Подтверждающих наблюдений: {a.observed_evidence_count} ·
                      Восстановлено {number(a.reconstructed_fraction * 100, 1)}%
                    </p>
                    <Explanation value={a.explanation} />
                    <JsonDetails
                      value={a.causes}
                      title="Возможные объяснения (гипотезы)"
                    />
                    <p className="text-xs leading-relaxed text-muted-foreground mt-2">
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
            <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
              <h2>Достоверность результата</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Модель {r.model_version} · Конфигурация {r.config_version} ·
                Результат {r.result_version || "не опубликован"}
              </p>
              {quality.data && (
                <>
                  <p className="text-sm leading-relaxed">
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
                <div
                  key={snapshot.id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 py-4 text-sm last:border-0"
                >
                  <div>
                    <p>{snapshot.provider}</p>
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      Получено{" "}
                      {new Date(snapshot.retrieved_at).toLocaleString("ru-RU")}
                    </p>
                    <p className="text-xs leading-relaxed text-muted-foreground break-all">
                      SHA-256 {snapshot.checksum}
                    </p>
                  </div>
                  <Status value={snapshot.status} />
                </div>
              ))}
              <p className="text-xs leading-relaxed text-muted-foreground">
                Анализ относится к сохранённым снимкам данных. Повтор с
                обновлением источников может дать другой результат.
              </p>
            </section>
          </TabsContent>
          <TabsContent value="export">
            <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
              <h2>Экспорт исследования</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {r.period.from} — {r.period.to} · Это данные реального поля;
                конкурсный submission формируется отдельно.
              </p>
              <Exports runId={id} />
            </section>
          </TabsContent>
        </Tabs>
      )}
      {!complete && terminalRun(r.state) && (
        <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground mt-5">
          Результат не опубликован. Откройте паспорт поля для нового анализа.
        </div>
      )}
    </div>
  );
}
