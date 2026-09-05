"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  allPages,
  number,
  ApiError,
  type Polygon,
  type Run,
  type Capabilities,
  type Schema,
} from "@/lib/api";
import { parseGeometry, validPeriod, bounds } from "@/lib/geometry";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  ErrorNotice,
  Status,
  JsonDetails,
} from "@/components/workspace/common";
const EditableMap = dynamic(
  () => import("@/components/map/field-map").then((m) => m.FieldMap),
  { ssr: false },
);
export function FieldDetail({ id }: { id: string }) {
  const client = useQueryClient(),
    router = useRouter();
  const polygon = useQuery({
    queryKey: ["polygon", id],
    queryFn: ({ signal }) => api<Polygon>(`polygons/${id}`, { signal }),
  });
  const history = useQuery({
    queryKey: ["history", id],
    queryFn: ({ signal }) => allPages<Run>(`polygons/${id}/analyses`, signal),
  });
  const caps = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Capabilities>("capabilities"),
  });
  const [from, setFrom] = useState("2024-06-01"),
    [to, setTo] = useState("2024-06-30"),
    [years, setYears] = useState(3),
    [sources, setSources] = useState(["sentinel2", "landsat", "era5_land"]),
    [refresh, setRefresh] = useState(false),
    [validation, setValidation] = useState<Error | null>(null);
  const key = useRef<{ body: string; key: string } | null>(null);
  const analyse = useMutation({
    mutationFn: () => {
      const p = polygon.data!,
        c = caps.data!;
      if (
        !validPeriod(
          from,
          to,
          c.supported_period.from,
          c.supported_period.to,
          c.limits.max_period_days,
        )
      )
        throw new Error(
          `Допустимый период: ${c.supported_period.from} — ${c.supported_period.to}, не более ${c.limits.max_period_days} дней`,
        );
      if (!sources.some((s) => s === "sentinel2" || s === "landsat"))
        throw new Error("Выберите спутниковый источник");
      const body = JSON.stringify({
        polygon_id: id,
        polygon_version: p.current_version,
        period: { from, to },
        sources,
        mode: "retrospective",
        options: { climatology_years: years, refresh_sources: refresh },
      });
      if (key.current?.body !== body)
        key.current = { body, key: crypto.randomUUID() };
      return api<Schema["RunAccepted"]>("analyses", {
        method: "POST",
        body,
        idempotencyKey: key.current.key,
      });
    },
    onSuccess: (r) => {
      key.current = null;
      client.invalidateQueries({ queryKey: ["history", id] });
      router.push(`/app/analyses/${r.run_id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      api(`polygons/${id}`, {
        method: "DELETE",
        body: JSON.stringify({
          expected_version: polygon.data!.current_version,
        }),
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["polygons"] });
      router.push("/app/polygons");
    },
  });
  if (polygon.isPending) return <div className="page-pad">Загружаем поле…</div>;
  if (!polygon.data)
    return (
      <div className="page-pad">
        <ErrorNotice error={polygon.error} />
        <Link href="/app/polygons">Вернуться к полям</Link>
      </div>
    );
  const p = polygon.data;
  return (
    <div className="page-pad">
      <Link href="/app/polygons" className="small muted">
        ← Все поля
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow mt-5">
            Паспорт территории / v{p.current_version}
          </p>
          <h1>{p.name}</h1>
          <p className="small muted">
            {number(p.area_ha, 2)} га · {p.crop_type || "Культура неизвестна"} ·
            Источник контура: {p.source}
          </p>
        </div>
        <FieldEditor
          key={`${p.id}-${p.current_version}-${p.updated_at}`}
          polygon={p}
        />
      </div>
      <ErrorNotice error={polygon.error || remove.error || validation} />
      <div className="grid-2">
        <section className="panel stack">
          <div>
            <h2>Новый анализ</h2>
            <p className="small muted">
              История растительности за выбранный период
            </p>
          </div>
          <div className="grid-2">
            <label className="field">
              Начало периода
              <input
                type="date"
                value={from}
                min={caps.data?.supported_period.from}
                max={caps.data?.supported_period.to}
                onChange={(e) => setFrom(e.target.value)}
              />
            </label>
            <label className="field">
              Конец периода
              <input
                type="date"
                value={to}
                min={from}
                max={caps.data?.supported_period.to}
                onChange={(e) => setTo(e.target.value)}
              />
            </label>
          </div>
          <fieldset className="stack">
            <legend className="field mb-2">Источники данных</legend>
            {[
              ["sentinel2", "Sentinel-2 · Earth Search"],
              ["landsat", "Landsat 8/9 · Planetary Computer"],
              ["era5_land", "Погода · ERA5 Seamless"],
            ].map(([s, t]) => (
              <label className="check-row" key={s}>
                <input
                  type="checkbox"
                  checked={sources.includes(s)}
                  onChange={(e) =>
                    setSources(
                      e.target.checked
                        ? [...sources, s]
                        : sources.filter((v) => v !== s),
                    )
                  }
                />
                {t}
              </label>
            ))}
          </fieldset>
          <label className="field">
            Предыдущих сезонов для нормы
            <select
              value={years}
              onChange={(e) => setYears(Number(e.target.value))}
            >
              {[0, 1, 2, 3, 4, 5].map((y) => (
                <option key={y} value={y}>
                  {y === 0
                    ? "Без сезонной нормы"
                    : `${y} ${y === 1 ? "сезон" : "сезонов"}`}
                </option>
              ))}
            </select>
          </label>
          <p className="micro muted">
            Для устойчивой нормы нужно от 3 сезонов. История увеличивает время
            сбора снимков; при недостатке данных результат будет явно отмечен.
          </p>
          <label className="check-row">
            <input
              type="checkbox"
              checked={refresh}
              onChange={(e) => setRefresh(e.target.checked)}
            />
            Обновить данные источников, минуя кэш
          </label>
          <ErrorNotice error={analyse.error || caps.error} />
          <Button
            disabled={analyse.isPending || !caps.data?.active_model}
            onClick={() => analyse.mutate()}
          >
            {analyse.isPending
              ? "Запускаем…"
              : "Запустить спутниковый анализ →"}
          </Button>
          {caps.data && !caps.data.active_model && (
            <p role="alert">
              Модель не зарегистрирована. Оператору нужно выполнить
              register_model.
            </p>
          )}
        </section>
        <section className="panel stack">
          <h2>История анализов</h2>
          <ErrorNotice error={history.error} retry={() => history.refetch()} />
          {history.isPending ? (
            <p>Загружаем историю…</p>
          ) : history.data?.length ? (
            history.data.map((r) => (
              <Link
                key={r.id}
                className="history-row"
                href={`/app/analyses/${r.id}`}
              >
                <div>
                  <p>
                    {r.period.from} — {r.period.to}
                  </p>
                  <small className="muted">
                    Версия контура {r.polygon_version}
                    {r.polygon_version !== p.current_version
                      ? " · предыдущая геометрия"
                      : ""}
                  </small>
                </div>
                <Status value={r.state} />
              </Link>
            ))
          ) : (
            <div className="empty">Анализов пока нет. Запустите первый.</div>
          )}
        </section>
      </div>
      <section className="panel mt-5">
        <h2>Происхождение и история культур</h2>
        <div className="scroll-table">
          <table className="data-table">
            <thead>
              <tr>
                <th>Начало</th>
                <th>Конец</th>
                <th>Культура</th>
                <th>Источник</th>
              </tr>
            </thead>
            <tbody>
              {p.crop_seasons.map((s) => (
                <tr key={s.id}>
                  <td>{s.season_start}</td>
                  <td>{s.season_end}</td>
                  <td>{s.crop_type || "Неизвестна"}</td>
                  <td>{s.origin}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!p.crop_seasons.length && (
          <p className="small muted mt-3">
            Сезонная история не указана. Уверенность сравнения с нормой может
            быть снижена.
          </p>
        )}
        <JsonDetails
          value={{
            geometry: p.geometry,
            geometry_hash: p.geometry_hash,
            source_ref: p.source_ref,
          }}
          title="Геометрия и происхождение"
        />
        <Button
          variant="destructive"
          size="sm"
          className="mt-5"
          disabled={remove.isPending}
          onClick={() => {
            setValidation(null);
            if (
              window.confirm(
                `Удалить поле «${p.name}» и связанную историю? Это действие нельзя отменить.`,
              )
            )
              remove.mutate();
          }}
        >
          Удалить поле
        </Button>
      </section>
    </div>
  );
}
function FieldEditor({ polygon: p }: { polygon: Polygon }) {
  const client = useQueryClient();
  const editGeometry = useMemo(
    () => parseGeometry(JSON.stringify(p.geometry)),
    [p.geometry],
  );
  const mapFocus = useMemo(() => bounds(editGeometry), [editGeometry]);
  const [mapOpen, setMapOpen] = useState(false);
  const [open, setOpen] = useState(false),
    [name, setName] = useState(p.name),
    [crop, setCrop] = useState(p.crop_type || ""),
    [geometry, setGeometry] = useState(JSON.stringify(p.geometry)),
    [seasons, setSeasons] = useState(
      p.crop_seasons.map(({ season_start, season_end, crop_type }) => ({
        season_start,
        season_end,
        crop_type,
      })),
    );
  const mutation = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Название обязательно");
      return api<Polygon>(`polygons/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_version: p.current_version,
          name: name.trim(),
          crop_type: crop || null,
          geometry: parseGeometry(geometry),
          crop_seasons: seasons,
        }),
      });
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["polygon", p.id] });
      client.invalidateQueries({ queryKey: ["polygons"] });
      setOpen(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">Редактировать поле</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Паспорт поля</DialogTitle>
          <DialogDescription>
            Изменение геометрии создаст новую версию. Прошлые анализы останутся
            в истории.
          </DialogDescription>
        </DialogHeader>
        <div className="stack">
          <label className="field">
            Название поля
            <input
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            Текущая культура
            <input
              maxLength={100}
              value={crop}
              onChange={(e) => setCrop(e.target.value)}
            />
          </label>
          <label className="field">
            Геометрия GeoJSON
            <textarea
              value={geometry}
              onChange={(e) => setGeometry(e.target.value)}
            />
          </label>
          <Button variant="outline" onClick={() => setMapOpen(!mapOpen)}>
            {mapOpen ? "Скрыть карту" : "Редактировать контур на карте"}
          </Button>
          {mapOpen && (
            <div className="edit-map">
              <EditableMap
                items={[]}
                focus={mapFocus}
                editable={editGeometry}
                onSelect={() => {}}
                onBounds={() => {}}
                onDraw={(g) => setGeometry(JSON.stringify(g))}
              />
              <p className="micro muted">
                Выберите контур, затем перетаскивайте вершины; промежуточные
                точки добавляют вершины. GeoJSON выше обновляется автоматически.
              </p>
            </div>
          )}
          <h3>Сезоны культур</h3>
          {seasons.map((s, i) => (
            <div className="season-row" key={i}>
              <label className="field">
                Начало
                <input
                  type="date"
                  value={s.season_start}
                  onChange={(e) =>
                    setSeasons(
                      seasons.map((v, j) =>
                        i === j ? { ...v, season_start: e.target.value } : v,
                      ),
                    )
                  }
                />
              </label>
              <label className="field">
                Конец
                <input
                  type="date"
                  value={s.season_end}
                  onChange={(e) =>
                    setSeasons(
                      seasons.map((v, j) =>
                        i === j ? { ...v, season_end: e.target.value } : v,
                      ),
                    )
                  }
                />
              </label>
              <label className="field">
                Культура
                <input
                  value={s.crop_type || ""}
                  onChange={(e) =>
                    setSeasons(
                      seasons.map((v, j) =>
                        i === j
                          ? { ...v, crop_type: e.target.value || null }
                          : v,
                      ),
                    )
                  }
                />
              </label>
              <Button
                aria-label={`Удалить сезон ${i + 1}`}
                variant="ghost"
                onClick={() => setSeasons(seasons.filter((_, j) => i !== j))}
              >
                ×
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            disabled={seasons.length >= 50}
            onClick={() =>
              setSeasons([
                ...seasons,
                { season_start: "", season_end: "", crop_type: null },
              ])
            }
          >
            Добавить сезон
          </Button>
          <ErrorNotice error={mutation.error} />
          {mutation.error instanceof ApiError &&
            mutation.error.code === "version_conflict" && (
              <Button
                variant="outline"
                onClick={() =>
                  client.invalidateQueries({ queryKey: ["polygon", p.id] })
                }
              >
                Загрузить актуальную версию
              </Button>
            )}
          <Button
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Сохранить изменения
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
