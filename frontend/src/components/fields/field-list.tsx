"use client";
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
    <div className="page-pad">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Ваши территории</p>
          <h1>Мои поля</h1>
          <p className="small muted">
            Контуры, культуры и история спутниковых наблюдений.
          </p>
        </div>
        <Button asChild>
          <Link href="/app">+ Добавить поле</Link>
        </Button>
      </div>
      <div className="panel stack">
        <div className="filter-row">
          <label className="field">
            Статус анализа
            <select
              aria-label="Статус анализа"
              value={state}
              onChange={(e) => setState(e.target.value)}
            >
              <option value="">Все статусы</option>
              <option value="none">Ещё не запущен</option>
              {[
                "queued",
                "running",
                "completed",
                "partial",
                "no_data",
                "failed",
                "cancelled",
              ].map((value) => (
                <option key={value} value={value}>
                  {label[value] || value}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Поиск
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Название поля"
            />
          </label>
          <label className="field">
            Культура
            <select value={crop} onChange={(e) => setCrop(e.target.value)}>
              <option value="">Все культуры</option>
              {Array.from(
                new Set(query.data?.map((p) => p.crop_type || "unknown")),
              ).map((c) => (
                <option key={c} value={c}>
                  {c === "unknown" ? "Неизвестна" : c}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Регион
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="">Все регионы</option>
              {Array.from(
                new Set(query.data?.map((p) => p.region_id || "manual")),
              ).map((c) => (
                <option key={c} value={c}>
                  {c === "manual" ? "Без привязки к региону" : c}
                </option>
              ))}
            </select>
          </label>
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
          <div className="empty">
            {query.data?.length
              ? "Нет полей по выбранным фильтрам"
              : "Добавьте первое поле на карте"}
          </div>
        ) : (
          <div className="scroll-table">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Поле</th>
                  <th>Площадь</th>
                  <th>Культура</th>
                  <th>Контур</th>
                  <th>Последний анализ</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link
                        className="text-primary"
                        href={`/app/polygons/${p.id}`}
                      >
                        {p.name} ↗
                      </Link>
                      <p className="micro muted">
                        Обновлено{" "}
                        {new Date(p.updated_at).toLocaleDateString("ru-RU")}
                      </p>
                    </td>
                    <td>{number(p.area_ha, 2)} га</td>
                    <td>{p.crop_type || "Неизвестна"}</td>
                    <td>
                      <span className="pill">
                        {p.source} · v{p.current_version}
                      </span>
                    </td>
                    <td>
                      {p.latest_run_id && latest.data?.[p.latest_run_id] && (
                        <div className="stack mb-2">
                          <Status value={latest.data[p.latest_run_id].state} />
                          <span className="micro muted">
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
                        <span className="muted">Ещё не запущен</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
