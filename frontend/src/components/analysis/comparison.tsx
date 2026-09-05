"use client";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import { Checkbox } from "@/components/ui/checkbox";

import { SelectControl, SelectOption } from "@/components/ui/select-control";

import { Label } from "@/components/ui/label";

import { Badge } from "@/components/ui/badge";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  allPages,
  number,
  type Polygon,
  type Run,
  type Schema,
} from "@/lib/api";
import { chartBase } from "@/lib/charts";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Status } from "@/components/workspace/common";
const Chart = dynamic(() => import("./chart").then((m) => m.Chart), {
  ssr: false,
});
export function Comparison() {
  const params = useSearchParams(),
    router = useRouter();
  const ids = (params.get("runs") || "").split(",").filter(Boolean);
  const alignment =
    params.get("alignment") === "day_of_year" ? "day_of_year" : "calendar";
  const fields = useQuery({
    queryKey: ["polygons"],
    queryFn: ({ signal }) => allPages<Polygon>("polygons", signal),
  });
  const histories = useQuery({
    queryKey: ["all-runs", fields.data?.map((p) => p.id)],
    queryFn: async ({ signal }) =>
      (
        await Promise.all(
          fields.data!.map((p) =>
            allPages<Run>(`polygons/${p.id}/analyses`, signal),
          ),
        )
      ).flat(),
    enabled: !!fields.data,
  });
  const compare = useQuery({
    queryKey: ["comparison", ids, alignment],
    queryFn: () =>
      api<Schema["ComparisonResponse"]>("comparisons", {
        method: "POST",
        body: JSON.stringify({ run_ids: ids, alignment }),
      }),
    enabled: ids.length > 0 && ids.length <= 4,
    retry: false,
  });
  function update(next: string[], mode = alignment) {
    router.replace(`/app/compare?runs=${next.join(",")}&alignment=${mode}`, {
      scroll: false,
    });
  }
  const colours = ["#d5e78b", "#80aaff", "#efc783", "#c3a2ed"];
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            Контекст вместо рейтинга
          </p>
          <h1>Сравнение полей и сезонов</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            До четырёх завершённых анализов. Выбор сохраняется в ссылке.
          </p>
        </div>
        <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
          {ids.length} / 4
        </Badge>
      </div>
      <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
        <div className="flex flex-wrap items-end gap-3">
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Совмещение рядов
            <SelectControl
              value={alignment}
              onValueChange={(value) => update(ids, value as typeof alignment)}
            >
              <SelectOption value="calendar">Абсолютные даты</SelectOption>
              <SelectOption value="day_of_year">
                Месяц и день (сезоны)
              </SelectOption>
            </SelectControl>
          </Label>
          <Button variant="outline" onClick={() => update([])}>
            Снять выбор
          </Button>
        </div>
        <ErrorNotice error={fields.error || histories.error || compare.error} />
        {ids.length > 4 && (
          <p role="alert">В ссылке больше четырёх анализов. Снимите лишние.</p>
        )}
        <div className="grid max-h-[360px] gap-3 overflow-auto lg:grid-cols-2">
          {histories.data
            ?.filter((r) =>
              ["completed", "partial", "no_data"].includes(r.state),
            )
            .map((r) => (
              <Label
                className="flex min-w-0 items-center gap-3 rounded-md border border-border p-4 text-sm font-normal has-[[data-state=checked]]:border-primary/45 has-[[data-state=checked]]:bg-primary/5 [&_small]:mt-1 [&_small]:block [&_small]:text-xs [&_small]:text-muted-foreground [&_[data-slot=badge]]:ml-auto"
                key={r.id}
              >
                <Checkbox
                  checked={ids.includes(r.id)}
                  disabled={!ids.includes(r.id) && ids.length >= 4}
                  onCheckedChange={(checked) =>
                    update(
                      checked === true
                        ? [...ids, r.id]
                        : ids.filter((id) => id !== r.id),
                    )
                  }
                />
                <span>
                  {fields.data?.find((p) => p.id === r.polygon_id)?.name ||
                    r.polygon_id}
                  <small>
                    {r.period.from} — {r.period.to} · v{r.polygon_version}
                  </small>
                </span>
                <Status value={r.state} />
              </Label>
            ))}
        </div>
        {!histories.isPending &&
          !histories.data?.some((r) =>
            ["completed", "partial", "no_data"].includes(r.state),
          ) && (
            <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
              Сначала завершите хотя бы один анализ.{" "}
              <Link className="text-primary" href="/app/polygons">
                Открыть поля →
              </Link>
            </div>
          )}
        {!ids.length && (
          <p className="text-muted-foreground text-sm leading-relaxed">
            Выберите анализы для сравнения.
          </p>
        )}
        {compare.isFetching && ids.length > 0 && (
          <p aria-live="polite">Обновляем сравнение…</p>
        )}
        {compare.data && (
          <>
            <div className="rounded-md border border-warning/25 bg-warning/5 px-4 py-3 text-sm leading-relaxed break-words text-warning">
              Разные культуры, геометрии и доли восстановленных данных
              ограничивают сравнимость. NDVI не является оценкой урожайности.
            </div>
            {compare.data.warnings.map((w) => (
              <p
                className="text-sm leading-relaxed text-muted-foreground"
                key={w}
              >
                {w}
              </p>
            ))}
            <Chart
              option={{
                ...chartBase,
                xAxis: { ...chartBase.xAxis, data: compare.data.axis },
                yAxis: { ...chartBase.yAxis, name: "NDVI" },
                series: compare.data.aligned_series.map((s, i) => ({
                  name: `${i + 1}. ${fields.data?.find((p) => p.id === compare.data!.items.find((r) => r.run.id === s.run_id)?.run.polygon_id)?.name || s.run_id.slice(0, 8)}`,
                  type: "line",
                  showSymbol: false,
                  connectNulls: false,
                  itemStyle: { color: colours[i] },
                  lineStyle: { type: "dashed" },
                  data: compare.data!.axis.map(
                    (key) =>
                      s.points.find((p) => p.alignment_key === key)
                        ?.reconstructed ?? null,
                  ),
                })),
              }}
            />
            <p className="text-xs leading-relaxed text-muted-foreground">
              {compare.data.alignment_rule} · 29 февраля сохраняется, даты без
              данных остаются разрывами.
            </p>
            <div className="max-w-full overflow-auto">
              <Table className="text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата / месяц-день</TableHead>
                    {compare.data.aligned_series.map((s, i) => (
                      <TableHead key={s.run_id}>Ряд {i + 1}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {compare.data.axis.map((key) => (
                    <TableRow key={key}>
                      <TableCell>{key}</TableCell>
                      {compare.data!.aligned_series.map((s) => (
                        <TableCell key={s.run_id}>
                          {number(
                            s.points.find((p) => p.alignment_key === key)
                              ?.reconstructed,
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
