"use client";
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
    <div className="page-pad">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Воспроизводимое восстановление</p>
          <h1>Модели и валидация</h1>
          <p className="small muted">
            Версии артефактов и фактические метрики из реестра сервера.
          </p>
        </div>
      </div>
      <ErrorNotice error={models.error} retry={() => models.refetch()} />
      <div className="notice mb-5">
        Это локальная валидация на анонимном benchmark. Assessment повторно
        использовал известные данные и не является слепым тестом. Официальный
        результат организаторов пока не опубликован.
      </div>
      {models.isPending ? (
        <p>Загружаем реестр…</p>
      ) : !models.data?.length ? (
        <div className="empty">Модель пока не зарегистрирована оператором.</div>
      ) : (
        models.data.map((m) => (
          <section className="panel stack mb-5" key={m.id}>
            <div className="page-heading">
              <div>
                <h2>{m.id}</h2>
                <p className="micro muted">
                  Зарегистрирована{" "}
                  {new Date(m.created_at).toLocaleString("ru-RU")} ·{" "}
                  {m.supported_modes.join(", ")}
                </p>
              </div>
              <span className="pill">{m.active ? "Активная" : "Архивная"}</span>
            </div>
            <p className="micro muted break-all">
              SHA-256 манифеста: {m.artifact_hash}
            </p>
            <div className="scroll-table">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Разбиение / сценарий</th>
                    <th>RMSE</th>
                    <th>MAE</th>
                    <th>N</th>
                    <th>GapScore</th>
                  </tr>
                </thead>
                <tbody>
                  {metricRows(m.metrics).map((r, i) => (
                    <tr key={i}>
                      <td>{r.split}</td>
                      <td>{number(r.rmse, 5)}</td>
                      <td>{number(r.mae, 5)}</td>
                      <td>{number(r.n, 0)}</td>
                      <td>{number(r.gap, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
