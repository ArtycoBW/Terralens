"use client";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import { SelectControl, SelectOption } from "@/components/ui/select-control";

import { Label } from "@/components/ui/label";

import { Badge } from "@/components/ui/badge";

import { useState } from "react";
import dynamic from "next/dynamic";
import data from "@/data/benchmark.json";
import { number } from "@/lib/api";
import { chartBase } from "@/lib/charts";
const Chart = dynamic(() => import("./chart").then((m) => m.Chart), {
  ssr: false,
});
export function Benchmark() {
  const [id, setId] = useState(data.polygons[0]?.id || "");
  const p = data.polygons.find((p) => p.id === id);
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            Анонимный конкурсный набор
          </p>
          <h1>Бенчмарк восстановления</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Опубликованные предсказания только для скрытых целевых точек.
          </p>
        </div>
        <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
          Модель {data.model_id}
        </Badge>
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4 [&>div]:border-0 [&>div]:border-l [&>div]:border-border [&>div]:bg-transparent [&>div]:py-3">
        <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
          <p className="text-sm text-muted-foreground">Целевых строк</p>
          <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em]">
            {number(data.rows, 0)}
          </p>
        </div>
        <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
          <p className="text-sm text-muted-foreground">AOI с предсказаниями</p>
          <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em]">
            {data.polygons.length}
          </p>
        </div>
        <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
          <p className="text-sm text-muted-foreground">
            Географическая привязка
          </p>
          <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em] text-lg mt-2">
            Отсутствует
          </p>
        </div>
        <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
          <p className="text-sm text-muted-foreground">Официальный RMSE</p>
          <p className="mt-2 font-mono text-3xl font-normal tracking-[-0.055em]">
            —
          </p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Истинные скрытые цели недоступны
          </p>
        </div>
      </div>
      <div className="rounded-md border border-warning/25 bg-warning/5 px-4 py-3 text-sm leading-relaxed break-words text-warning mb-5">
        AOI анонимизированы и не показаны на карте. Предсказания не являются
        измерениями; расстояния между целевыми датами могут быть неравномерными.
      </div>
      <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
        <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
          Анонимный AOI
          <SelectControl value={id} onValueChange={(value) => setId(value)}>
            {data.polygons.map((p) => (
              <SelectOption key={p.id} value={p.id}>
                {p.id} · {p.points.length} целей
              </SelectOption>
            ))}
          </SelectControl>
        </Label>
        {p && (
          <>
            <Chart
              height={330}
              option={{
                ...chartBase,
                xAxis: { type: "time" },
                yAxis: { ...chartBase.yAxis, name: "NDVI" },
                series: [
                  {
                    name: "Предсказанные цели",
                    type: "scatter",
                    symbolSize: 6,
                    itemStyle: { color: "#d5e78b" },
                    data: p.points.map((p) => [p.date, p.value]),
                  },
                ],
              }}
            />
            <div className="max-w-full overflow-auto max-h-[360px]">
              <Table className="text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>Дата цели</TableHead>
                    <TableHead>primary_ndvi_pred</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {p.points.map((p) => (
                    <TableRow key={p.date}>
                      <TableCell>{p.date}</TableCell>
                      <TableCell>{number(p.value, 6)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
        <p className="text-xs leading-relaxed text-muted-foreground break-all">
          Источник: {data.source} · SHA-256: {data.sha256}
        </p>
      </section>
      <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 mt-5 grid min-w-0 gap-4">
        <h2>Воспроизвести submission</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          CLI работает отдельно от веб-приложения; обучение и инференс
          выполняются в Python.
        </p>
        <pre className="max-w-full overflow-auto rounded-md border border-border bg-background p-4 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">
          python -m terralens_ml predict --input test-dataset.csv --output
          submission.csv --model ml/artifacts/final/manifest.json{"\n"}python -m
          terralens_ml validate-submission --input test-dataset.csv --submission
          submission.csv
        </pre>
      </section>
    </div>
  );
}
