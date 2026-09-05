"use client";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  allPages,
  api,
  number,
  type Polygon,
  type Run,
  type Capabilities,
} from "@/lib/api";
import {
  ErrorNotice,
  Status,
  JsonDetails,
} from "@/components/workspace/common";
export function QualityOverview() {
  const fields = useQuery({
    queryKey: ["polygons"],
    queryFn: ({ signal }) => allPages<Polygon>("polygons", signal),
  });
  const runs = useQuery({
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
  const caps = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Capabilities>("capabilities"),
  });
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            Данные с происхождением
          </p>
          <h1>Качество наблюдений</h1>
          <p className="text-muted-foreground text-sm leading-relaxed">
            Покрытие, пропуски и версии данных по каждому анализу.
          </p>
        </div>
      </div>
      <ErrorNotice error={fields.error || runs.error || caps.error} />
      <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6">
        <div className="max-w-full overflow-auto">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>Поле / период</TableHead>
                <TableHead>Состояние</TableHead>
                <TableHead>Покрытие QA</TableHead>
                <TableHead>Восстановлено</TableHead>
                <TableHead>Пропуск</TableHead>
                <TableHead>Источники</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data?.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      className="text-primary"
                      href={`/app/analyses/${r.id}`}
                    >
                      {fields.data?.find((p) => p.id === r.polygon_id)?.name ||
                        "Поле"}{" "}
                      ↗
                    </Link>
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      {r.period.from} — {r.period.to}
                    </p>
                  </TableCell>
                  <TableCell>
                    <Status value={r.state} />
                  </TableCell>
                  <TableCell>
                    {number(
                      r.summary
                        ? 100 * r.summary.observed_coverage_ratio
                        : null,
                      1,
                    )}
                    %
                  </TableCell>
                  <TableCell>
                    {number(r.summary?.reconstructed_days, 0)} дн.
                  </TableCell>
                  <TableCell>
                    {number(r.summary?.longest_gap_days, 0)} дн.
                  </TableCell>
                  <TableCell>
                    {r.snapshots.map((s) => (
                      <p className="text-xs leading-relaxed" key={s.id}>
                        {s.provider} · {s.status} ·{" "}
                        {new Date(s.retrieved_at).toLocaleDateString("ru-RU")}
                      </p>
                    ))}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {!runs.isPending && !runs.data?.length && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
            Пока нет анализов. Качество появится после получения спутниковых
            наблюдений.
          </div>
        )}
      </section>
      <div className="grid min-w-0 gap-6 xl:grid-cols-2 mt-5">
        <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
          <h2>Как читать качество</h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Покрытие — доля календарных дней с пригодным спутниковым наблюдением
            после маски облаков, теней и проверки пикселей. Восстановленные дни
            не увеличивают покрытие.
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Норма требует минимум трёх пригодных прошлых сезонов. Отсутствующая
            норма или погода снижают уверенность, а отсутствие наблюдений не
            означает здоровое поле.
          </p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            S2 и Landsat сохраняются раздельно. Для объединённого ряда приоритет
            имеет Sentinel-2; переключения сенсора отмечаются флагом качества.
          </p>
        </section>
        <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
          <h2>Подключённые источники</h2>
          {caps.data?.providers.map((p) => (
            <div
              className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 py-4 text-sm last:border-0"
              key={p.id}
            >
              <span>{p.id}</span>
              <span className="text-xs leading-relaxed text-muted-foreground">
                {p.provider}
              </span>
            </div>
          ))}
          <JsonDetails
            value={caps.data?.limits}
            title="Текущие ограничения сервера"
          />
        </section>
      </div>
    </div>
  );
}
