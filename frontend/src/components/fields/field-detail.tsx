"use client";
import { DateField } from "@/components/ui/date-field";
import { Textarea } from "@/components/ui/textarea";

import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

import { SelectControl, SelectOption } from "@/components/ui/select-control";

import { Checkbox } from "@/components/ui/checkbox";

import { Input } from "@/components/ui/input";

import { Label } from "@/components/ui/label";

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
import {
  parseGeometry,
  validPeriod,
  bounds,
  type FieldGeometry,
} from "@/lib/geometry";
import { ConfirmAction } from "@/components/ui/confirm-action";
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
    [refresh, setRefresh] = useState(false);
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
  if (polygon.isPending)
    return (
      <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
        Загружаем поле…
      </div>
    );
  if (!polygon.data)
    return (
      <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
        <ErrorNotice error={polygon.error} />
        <Link href="/app/polygons">Вернуться к полям</Link>
      </div>
    );
  const p = polygon.data;
  return (
    <div className="min-w-0 px-4 py-7 sm:px-7 lg:px-10 lg:py-9 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <Link
        href="/app/polygons"
        className="text-sm leading-relaxed text-muted-foreground"
      >
        ← Все поля
      </Link>
      <div className="mb-7 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground mt-5">
            Паспорт территории / v{p.current_version}
          </p>
          <h1>{p.name}</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {number(p.area_ha, 2)} га · {p.crop_type || "Культура неизвестна"} ·
            Источник контура: {p.source}
          </p>
        </div>
        <FieldEditor
          key={`${p.id}-${p.current_version}-${p.updated_at}`}
          polygon={p}
        />
      </div>
      <ErrorNotice error={polygon.error || remove.error} />
      <div className="grid min-w-0 gap-6 xl:grid-cols-2">
        <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
          <div>
            <h2>Новый анализ</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              История растительности за выбранный период
            </p>
          </div>
          <div className="grid min-w-0 gap-6 xl:grid-cols-2">
            <DateField
              label="Начало периода"
              value={from}
              min={caps.data?.supported_period.from}
              max={caps.data?.supported_period.to}
              onValueChange={(value) => setFrom(value)}
            />
            <DateField
              label="Конец периода"
              value={to}
              min={from}
              max={caps.data?.supported_period.to}
              onValueChange={(value) => setTo(value)}
            />
          </div>
          <fieldset className="grid min-w-0 gap-4">
            <legend className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground mb-2">
              Источники данных
            </legend>
            {[
              ["sentinel2", "Sentinel-2 · Earth Search"],
              ["landsat", "Landsat 8/9 · Planetary Computer"],
              ["era5_land", "Погода · ERA5 Seamless"],
            ].map(([s, t]) => (
              <Label
                className="flex items-center gap-3 text-sm font-normal text-foreground"
                key={s}
              >
                <Checkbox
                  checked={sources.includes(s)}
                  onCheckedChange={(checked) =>
                    setSources(
                      checked === true
                        ? [...sources, s]
                        : sources.filter((v) => v !== s),
                    )
                  }
                />
                {t}
              </Label>
            ))}
          </fieldset>
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Предыдущих сезонов для нормы
            <SelectControl
              value={years}
              onValueChange={(value) => setYears(Number(value))}
            >
              {[0, 1, 2, 3, 4, 5].map((y) => (
                <SelectOption key={y} value={y}>
                  {y === 0
                    ? "Без сезонной нормы"
                    : `${y} ${y === 1 ? "сезон" : "сезонов"}`}
                </SelectOption>
              ))}
            </SelectControl>
          </Label>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Для устойчивой нормы нужно от 3 сезонов. История увеличивает время
            сбора снимков; при недостатке данных результат будет явно отмечен.
          </p>
          <Label className="flex items-center gap-3 text-sm font-normal text-foreground">
            <Checkbox
              checked={refresh}
              onCheckedChange={(checked) => setRefresh(checked === true)}
            />
            Обновить данные источников, минуя кэш
          </Label>
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
        <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 grid min-w-0 gap-4">
          <h2>История анализов</h2>
          <ErrorNotice error={history.error} retry={() => history.refetch()} />
          {history.isPending ? (
            <p>Загружаем историю…</p>
          ) : history.data?.length ? (
            history.data.map((r) => (
              <Link
                key={r.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 py-4 text-sm last:border-0"
                href={`/app/analyses/${r.id}`}
              >
                <div>
                  <p>
                    {r.period.from} — {r.period.to}
                  </p>
                  <small className="text-muted-foreground">
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
            <div className="flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
              Анализов пока нет. Запустите первый.
            </div>
          )}
        </section>
      </div>
      <section className="min-w-0 rounded-md border border-border/70 bg-card p-5 sm:p-6 mt-5">
        <h2>Происхождение и история культур</h2>
        <div className="max-w-full overflow-auto">
          <Table className="text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>Начало</TableHead>
                <TableHead>Конец</TableHead>
                <TableHead>Культура</TableHead>
                <TableHead>Источник</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {p.crop_seasons.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>{s.season_start}</TableCell>
                  <TableCell>{s.season_end}</TableCell>
                  <TableCell>{s.crop_type || "Неизвестна"}</TableCell>
                  <TableCell>{s.origin}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {!p.crop_seasons.length && (
          <p className="text-sm leading-relaxed text-muted-foreground mt-3">
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
        <ConfirmAction
          title="Удалить поле?"
          description={`Поле «${p.name}» и связанная история будут удалены. Это действие нельзя отменить.`}
          action="Удалить поле"
          onConfirm={() => remove.mutateAsync()}
        >
          <Button
            variant="destructive"
            size="sm"
            className="mt-5"
            disabled={remove.isPending}
          >
            Удалить поле
          </Button>
        </ConfirmAction>
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
      const parsedGeometry = parseGeometry(geometry);
      const savedGeometry = p.geometry as FieldGeometry;
      const geometryChanged =
        parsedGeometry.type !== savedGeometry.type ||
        JSON.stringify(parsedGeometry.coordinates) !==
          JSON.stringify(savedGeometry.coordinates);
      return api<Polygon>(`polygons/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_version: p.current_version,
          name: name.trim(),
          crop_type: crop || null,
          ...(geometryChanged ? { geometry: parsedGeometry } : {}),
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
        <div className="grid min-w-0 gap-4">
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Название поля
            <Input
              maxLength={200}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Label>
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Текущая культура
            <Input
              maxLength={100}
              value={crop}
              onChange={(e) => setCrop(e.target.value)}
            />
          </Label>
          <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
            Геометрия GeoJSON
            <Textarea
              value={geometry}
              onChange={(e) => setGeometry(e.target.value)}
            />
          </Label>
          <Button variant="outline" onClick={() => setMapOpen(!mapOpen)}>
            {mapOpen ? "Скрыть карту" : "Редактировать контур на карте"}
          </Button>
          {mapOpen && (
            <div className="[&_.map-wrap]:h-[350px] [&_.map-wrap]:min-h-[350px] [&_.map-legend]:hidden">
              <EditableMap
                items={[]}
                focus={mapFocus}
                editable={editGeometry}
                onSelect={() => {}}
                onBounds={() => {}}
                onDraw={(g) => setGeometry(JSON.stringify(g))}
              />
              <p className="text-xs leading-relaxed text-muted-foreground">
                Выберите контур, затем перетаскивайте вершины; промежуточные
                точки добавляют вершины. GeoJSON выше обновляется автоматически.
              </p>
            </div>
          )}
          <h3>Сезоны культур</h3>
          {seasons.map((s, i) => (
            <div
              className="grid grid-cols-2 items-end gap-3 sm:grid-cols-[1fr_1fr_1fr_32px]"
              key={i}
            >
              <DateField
                label="Начало"
                value={s.season_start}
                onValueChange={(value) =>
                  setSeasons(
                    seasons.map((v, j) =>
                      i === j ? { ...v, season_start: value } : v,
                    ),
                  )
                }
              />
              <DateField
                label="Конец"
                value={s.season_end}
                onValueChange={(value) =>
                  setSeasons(
                    seasons.map((v, j) =>
                      i === j ? { ...v, season_end: value } : v,
                    ),
                  )
                }
              />
              <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                Культура
                <Input
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
              </Label>
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
