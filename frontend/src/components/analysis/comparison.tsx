"use client";
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
  const colours = ["#5df0a8", "#80aaff", "#efc783", "#c3a2ed"];
  return (
    <div className="page-pad">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Контекст вместо рейтинга</p>
          <h1>Сравнение полей и сезонов</h1>
          <p className="small muted">
            До четырёх завершённых анализов. Выбор сохраняется в ссылке.
          </p>
        </div>
        <span className="pill">{ids.length} / 4</span>
      </div>
      <div className="panel stack">
        <div className="actions">
          <label className="field">
            Совмещение рядов
            <select
              value={alignment}
              onChange={(e) => update(ids, e.target.value as typeof alignment)}
            >
              <option value="calendar">Абсолютные даты</option>
              <option value="day_of_year">Месяц и день (сезоны)</option>
            </select>
          </label>
          <Button variant="outline" onClick={() => update([])}>
            Снять выбор
          </Button>
        </div>
        <ErrorNotice error={fields.error || histories.error || compare.error} />
        {ids.length > 4 && (
          <p role="alert">В ссылке больше четырёх анализов. Снимите лишние.</p>
        )}
        <div className="comparison-picker">
          {histories.data
            ?.filter((r) =>
              ["completed", "partial", "no_data"].includes(r.state),
            )
            .map((r) => (
              <label className="comparison-choice" key={r.id}>
                <input
                  type="checkbox"
                  checked={ids.includes(r.id)}
                  disabled={!ids.includes(r.id) && ids.length >= 4}
                  onChange={(e) =>
                    update(
                      e.target.checked
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
              </label>
            ))}
        </div>
        {!histories.isPending &&
          !histories.data?.some((r) =>
            ["completed", "partial", "no_data"].includes(r.state),
          ) && (
            <div className="empty">
              Сначала завершите хотя бы один анализ.{" "}
              <Link className="text-primary" href="/app/polygons">
                Открыть поля →
              </Link>
            </div>
          )}
        {!ids.length && (
          <p className="muted small">Выберите анализы для сравнения.</p>
        )}
        {compare.isFetching && ids.length > 0 && (
          <p aria-live="polite">Обновляем сравнение…</p>
        )}
        {compare.data && (
          <>
            <div className="notice">
              Разные культуры, геометрии и доли восстановленных данных
              ограничивают сравнимость. NDVI не является оценкой урожайности.
            </div>
            {compare.data.warnings.map((w) => (
              <p className="small muted" key={w}>
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
            <p className="micro muted">
              {compare.data.alignment_rule} · 29 февраля сохраняется, даты без
              данных остаются разрывами.
            </p>
            <div className="scroll-table">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Дата / месяц-день</th>
                    {compare.data.aligned_series.map((s, i) => (
                      <th key={s.run_id}>Ряд {i + 1}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compare.data.axis.map((key) => (
                    <tr key={key}>
                      <td>{key}</td>
                      {compare.data!.aligned_series.map((s) => (
                        <td key={s.run_id}>
                          {number(
                            s.points.find((p) => p.alignment_key === key)
                              ?.reconstructed,
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
