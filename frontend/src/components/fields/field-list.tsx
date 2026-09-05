"use client";
import { Badge } from "@/components/ui/badge";

import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import { Input } from "@/components/ui/input";

import { SelectControl, SelectOption } from "@/components/ui/select-control";

import { Label } from "@/components/ui/label";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  allPages,
  number,
  label,
  type Polygon,
  type Run,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Status } from "@/components/workspace/common";
export function FieldList() {
  const [search, setSearch] = useState(""),
    [crop, setCrop] = useState(""),
    [region, setRegion] = useState(""),
    [state, setState] = useState("");
  const query = useQuery({
    queryKey: ["polygons"],
    queryFn: ({ signal }) => allPages<Polygon>("polygons", signal),
  });
  const latest = useQuery({
    queryKey: ["latest-runs", query.data?.map((p) => p.latest_run_id)],
    enabled: !!query.data,
    queryFn: async ({ signal }) => {
      const ids = Array.from(
        new Set(
          query.data!.flatMap((p) =>
            p.latest_run_id ? [p.latest_run_id] : [],
          ),
        ),
      );
      const runs: Record<string, Run> = {};
      // Ограничиваем одновременные запросы, чтобы большой список не перегружал API.
      for (let i = 0; i < ids.length; i += 5) {
        for (const r of await Promise.all(
          ids
            .slice(i, i + 5)
            .map((id) => api<Run>(`analyses/${id}`, { signal })),
        ))
          runs[r.id] = r;
      }
      return runs;
    },
    refetchInterval: (q) =>
      Object.values(q.state.data || {}).some((r) =>
        ["queued", "running"].includes(r.state),
      )
        ? 5000
        : false,
  });
  const rows = query.data?.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) &&
      (!crop || (p.crop_type || "unknown") === crop) &&
      (!region || (p.region_id || "manual") === region) &&
      (!state ||
        (p.latest_run_id ? latest.data?.[p.latest_run_id]?.state : "none") ===
          state),
  );
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            Ваши территории
          </p>
          <h1>Мои поля</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Контуры, культуры и история спутниковых наблюдений.
          </p>
        </div>
        <Button asChild>
          <Link href="/app">+ Добавить поле</Link>
        </Button>
      </div>
      <div className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-[1fr_1.2fr_1fr_1fr]">
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Статус анализа
            <SelectControl
              aria-label="Статус анализа"
              value={state}
              onValueChange={(value) => setState(value)}
            >
              <SelectOption value="">Все статусы</SelectOption>
              <SelectOption value="none">Ещё не запущен</SelectOption>
              {[
                "queued",
                "running",
                "completed",
                "partial",
                "no_data",
                "failed",
                "cancelled",
              ].map((value) => (
                <SelectOption key={value} value={value}>
                  {label[value] || value}
                </SelectOption>
              ))}
            </SelectControl>
          </Label>
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Поиск
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Название поля"
            />
          </Label>
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Культура
            <SelectControl
              value={crop}
              onValueChange={(value) => setCrop(value)}
            >
              <SelectOption value="">Все культуры</SelectOption>
              {Array.from(
                new Set(query.data?.map((p) => p.crop_type || "unknown")),
              ).map((c) => (
                <SelectOption key={c} value={c}>
                  {c === "unknown" ? "Неизвестна" : c}
                </SelectOption>
              ))}
            </SelectControl>
          </Label>
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Регион
            <SelectControl
              value={region}
              onValueChange={(value) => setRegion(value)}
            >
              <SelectOption value="">Все регионы</SelectOption>
              {Array.from(
                new Set(query.data?.map((p) => p.region_id || "manual")),
              ).map((c) => (
                <SelectOption key={c} value={c}>
                  {c === "manual" ? "Без привязки к региону" : c}
                </SelectOption>
              ))}
            </SelectControl>
          </Label>
        </div>
        <ErrorNotice
          error={query.error || latest.error}
          retry={() => {
            query.refetch();
            latest.refetch();
          }}
        />
        {query.isPending || (!!state && latest.isPending) ? (
          <p>Загружаем поля…</p>
        ) : !rows?.length ? (
          <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
            {query.data?.length
              ? "Нет полей по выбранным фильтрам"
              : "Добавьте первое поле на карте"}
          </div>
        ) : (
          <div className="max-w-full overflow-auto">
            <Table className="text-sm">
              <TableHeader>
                <TableRow>
                  <TableHead>Поле</TableHead>
                  <TableHead>Площадь</TableHead>
                  <TableHead>Культура</TableHead>
                  <TableHead>Контур</TableHead>
                  <TableHead>Последний анализ</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <Link
                        className="text-primary"
                        href={`/app/polygons/${p.id}`}
                      >
                        {p.name} ↗
                      </Link>
                      <p className="text-xs leading-relaxed text-muted-foreground">
                        Обновлено{" "}
                        {new Date(p.updated_at).toLocaleDateString("ru-RU")}
                      </p>
                    </TableCell>
                    <TableCell>{number(p.area_ha, 2)} га</TableCell>
                    <TableCell>{p.crop_type || "Неизвестна"}</TableCell>
                    <TableCell>
                      <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
                        {p.source} · v{p.current_version}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {p.latest_run_id && latest.data?.[p.latest_run_id] && (
                        <div className="grid min-w-0 gap-4 mb-2">
                          <Status value={latest.data[p.latest_run_id].state} />
                          <span className="text-xs leading-relaxed text-muted-foreground">
                            {new Date(
                              latest.data[p.latest_run_id].created_at,
                            ).toLocaleDateString("ru-RU")}
                          </span>
                        </div>
                      )}
                      {p.latest_run_id ? (
                        <Link
                          className="text-primary"
                          href={`/app/analyses/${p.latest_run_id}`}
                        >
                          Открыть результат →
                        </Link>
                      ) : (
                        <span className="text-muted-foreground">
                          Ещё не запущен
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
