"use client";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import { Badge } from "@/components/ui/badge";

import { useQuery } from "@tanstack/react-query";
import { allPages, number } from "@/lib/api";
import { ErrorNotice, JsonDetails } from "@/components/workspace/common";
type Model = {
  id: string;
  active: boolean;
  artifact_hash: string;
  created_at: string;
  supported_modes: string[];
  metrics: Record<string, unknown> | null;
};
export function metricRows(
  value: unknown,
  path = "",
): {
  split: string;
  rmse: number | null;
  mae: number | null;
  n: number | null;
  gap: number | null;
}[] {
  if (!value || typeof value !== "object") return [];
  const v = value as Record<string, unknown>;
  if (typeof v.rmse === "number")
    return [
      {
        split: path,
        rmse: v.rmse,
        mae: typeof v.mae === "number" ? v.mae : null,
        n: typeof v.n === "number" ? v.n : null,
        gap: typeof v.gap_score === "number" ? v.gap_score : null,
      },
    ];
  return Object.entries(v).flatMap(([k, x]) =>
    metricRows(x, path ? `${path} / ${k}` : k),
  );
}
export function Models() {
  const models = useQuery({
    queryKey: ["models"],
    queryFn: ({ signal }) => allPages<Model>("models", signal),
  });
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">
            Воспроизводимое восстановление
          </p>
          <h1>Модели и валидация</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Версии артефактов и фактические метрики из реестра сервера.
          </p>
        </div>
      </div>
      <ErrorNotice error={models.error} retry={() => models.refetch()} />
      <div className="rounded-md border border-warning/25 bg-warning/5 px-4 py-3 text-sm leading-relaxed break-words text-warning mb-5">
        Это локальная валидация на анонимном benchmark. Assessment повторно
        использовал известные данные и не является слепым тестом. Официальный
        результат организаторов пока не опубликован.
      </div>
      {models.isPending ? (
        <p>Загружаем реестр…</p>
      ) : !models.data?.length ? (
        <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
          Модель пока не зарегистрирована оператором.
        </div>
      ) : (
        models.data.map((m) => (
          <section
            className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4 mb-5"
            key={m.id}
          >
            <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
              <div>
                <h2>{m.id}</h2>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  Зарегистрирована{" "}
                  {new Date(m.created_at).toLocaleString("ru-RU")} ·{" "}
                  {m.supported_modes.join(", ")}
                </p>
              </div>
              <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
                {m.active ? "Активная" : "Архивная"}
              </Badge>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground break-all">
              SHA-256 манифеста: {m.artifact_hash}
            </p>
            <div className="max-w-full overflow-auto">
              <Table className="text-sm">
                <TableHeader>
                  <TableRow>
                    <TableHead>Разбиение / сценарий</TableHead>
                    <TableHead>RMSE</TableHead>
                    <TableHead>MAE</TableHead>
                    <TableHead>N</TableHead>
                    <TableHead>GapScore</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {metricRows(m.metrics).map((r, i) => (
                    <TableRow key={i}>
                      <TableCell>{r.split}</TableCell>
                      <TableCell>{number(r.rmse, 5)}</TableCell>
                      <TableCell>{number(r.mae, 5)}</TableCell>
                      <TableCell>{number(r.n, 0)}</TableCell>
                      <TableCell>{number(r.gap, 2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <JsonDetails
              value={m.metrics}
              title="Полный протокол локальных метрик"
            />
          </section>
        ))
      )}
    </div>
  );
}
