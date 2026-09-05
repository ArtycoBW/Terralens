"use client";
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
    <div className="page-pad">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Данные с происхождением</p>
          <h1>Качество наблюдений</h1>
          <p className="muted small">
            Покрытие, пропуски и версии данных по каждому анализу.
          </p>
        </div>
      </div>
      <ErrorNotice error={fields.error || runs.error || caps.error} />
      <section className="panel">
        <div className="scroll-table">
          <table className="data-table">
            <thead>
              <tr>
                <th>Поле / период</th>
                <th>Состояние</th>
                <th>Покрытие QA</th>
                <th>Восстановлено</th>
                <th>Пропуск</th>
                <th>Источники</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link
                      className="text-primary"
                      href={`/app/analyses/${r.id}`}
                    >
                      {fields.data?.find((p) => p.id === r.polygon_id)?.name ||
                        "Поле"}{" "}
                      ↗
                    </Link>
                    <p className="micro muted">
                      {r.period.from} — {r.period.to}
                    </p>
                  </td>
                  <td>
                    <Status value={r.state} />
                  </td>
                  <td>
                    {number(
                      r.summary
                        ? 100 * r.summary.observed_coverage_ratio
                        : null,
                      1,
                    )}
                    %
                  </td>
                  <td>{number(r.summary?.reconstructed_days, 0)} дн.</td>
                  <td>{number(r.summary?.longest_gap_days, 0)} дн.</td>
                  <td>
                    {r.snapshots.map((s) => (
                      <p className="micro" key={s.id}>
                        {s.provider} · {s.status} ·{" "}
                        {new Date(s.retrieved_at).toLocaleDateString("ru-RU")}
                      </p>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!runs.isPending && !runs.data?.length && (
          <div className="empty">
            Пока нет анализов. Качество появится после получения спутниковых
            наблюдений.
          </div>
        )}
      </section>
      <div className="grid-2 mt-5">
        <section className="panel stack">
          <h2>Как читать качество</h2>
          <p className="small muted">
            Покрытие — доля календарных дней с пригодным спутниковым наблюдением
            после маски облаков, теней и проверки пикселей. Восстановленные дни
            не увеличивают покрытие.
          </p>
          <p className="small muted">
            Норма требует минимум трёх пригодных прошлых сезонов. Отсутствующая
            норма или погода снижают уверенность, а отсутствие наблюдений не
            означает здоровое поле.
          </p>
          <p className="small muted">
            S2 и Landsat сохраняются раздельно. Для объединённого ряда приоритет
            имеет Sentinel-2; переключения сенсора отмечаются флагом качества.
          </p>
        </section>
        <section className="panel stack">
          <h2>Подключённые источники</h2>
          {caps.data?.providers.map((p) => (
            <div className="history-row" key={p.id}>
              <span>{p.id}</span>
              <span className="micro muted">{p.provider}</span>
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
