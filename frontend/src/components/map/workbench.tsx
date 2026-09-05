"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Search, ArrowUpRight, MapPin, Plus } from "lucide-react";
import {
  api,
  allPages,
  number,
  type Polygon,
  type Capabilities,
  type Schema,
  type Job,
  terminalJob,
} from "@/lib/api";
import { parseGeometry, bounds, type FieldGeometry } from "@/lib/geometry";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/workspace/common";
import { useWorkspace } from "@/components/workspace/provider";
import { JobProgress } from "@/components/workspace/job-progress";
const FieldMap = dynamic(() => import("./field-map").then((m) => m.FieldMap), {
  ssr: false,
  loading: () => <div className="map-wrap empty">Загружаем карту…</div>,
});
const schema = z.object({
  name: z.string().trim().min(1, "Назовите поле").max(200),
  crop: z.string().max(100),
  geometry: z.string().min(1, "Нарисуйте или вставьте контур"),
});
export function Workbench() {
  const { session } = useWorkspace();
  const client = useQueryClient();
  const fields = useQuery({
    queryKey: ["polygons"],
    queryFn: ({ signal }) => allPages<Polygon>("polygons", signal),
  });
  const caps = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Capabilities>("capabilities"),
  });
  const [search, setSearch] = useState(""),
    [country, setCountry] = useState(""),
    [viewport, setViewport] = useState<number[]>([]),
    [focus, setFocus] = useState<number[]>(),
    [candidate, setCandidate] = useState<Schema["CandidateResponse"] | null>(
      null,
    ),
    [discovery, setDiscovery] = useState<{
      discovery_id: string;
      job_id: string;
    } | null>(null),
    [selected, setSelected] = useState<Polygon | null>(null),
    [mobile, setMobile] = useState(false),
    [formError, setFormError] = useState<Error | null>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", crop: "", geometry: "" },
  });
  const { reset: resetDraft, subscribe } = form;
  useEffect(() => {
    const key = `terralens-draft:${session.workspace_id}`;
    try {
      const saved = sessionStorage.getItem(key);
      if (saved) {
        const parsed = schema
          .extend({ name: z.string().max(200) })
          .safeParse(JSON.parse(saved));
        if (parsed.success) resetDraft(parsed.data);
      }
    } catch {}
    return subscribe({
      formState: { values: true },
      callback: ({ values }) => {
        try {
          if (values.geometry)
            sessionStorage.setItem(key, JSON.stringify(values));
          else sessionStorage.removeItem(key);
        } catch {}
      },
    });
  }, [session.workspace_id, resetDraft, subscribe]);
  const geometryValue = useWatch({ control: form.control, name: "geometry" });
  const regions = useMutation({
    mutationFn: () =>
      api<Schema["RegionList"]>(
        `regions?q=${encodeURIComponent(search)}${country ? `&country=${encodeURIComponent(country)}` : ""}`,
      ),
  });
  const discoveryKey = useRef<{ body: string; id: string } | null>(null);
  const discover = useMutation({
    mutationFn: () => {
      const body = JSON.stringify({ bbox: viewport, sources: ["osm"] });
      if (discoveryKey.current?.body !== body)
        discoveryKey.current = { body, id: crypto.randomUUID() };
      return api<Schema["DiscoveryAccepted"]>("discoveries", {
        method: "POST",
        body,
        idempotencyKey: discoveryKey.current.id,
      });
    },
    onSuccess: (r) => {
      setDiscovery(r);
      discoveryKey.current = null;
    },
  });
  const discoveryJob = useQuery({
    queryKey: ["job", discovery?.job_id],
    queryFn: () => api<Job>(`jobs/${discovery!.job_id}`),
    enabled: !!discovery,
    refetchInterval: (q) =>
      q.state.data && terminalJob(q.state.data.state) ? false : 2000,
  });
  const candidates = useQuery({
    queryKey: ["discovery", discovery?.discovery_id, discoveryJob.data?.state],
    queryFn: () =>
      allPages<Schema["CandidateResponse"]>(
        `discoveries/${discovery!.discovery_id}`,
      ),
    enabled: !!discovery && discoveryJob.data?.state === "succeeded",
  });
  const create = useMutation({
    mutationFn: (data: z.infer<typeof schema>) =>
      api<Polygon>("polygons", {
        method: "POST",
        body: JSON.stringify({
          name: data.name,
          crop_type: data.crop || null,
          ...(candidate
            ? { candidate_id: candidate.candidate_id }
            : {
                geometry: parseGeometry(
                  data.geometry,
                  caps.data?.limits.max_vertices,
                ),
              }),
        }),
      }),
    onSuccess: (p) => {
      client.invalidateQueries({ queryKey: ["polygons"] });
      setSelected(p);
      form.reset();
      setCandidate(null);
      setFormError(null);
    },
  });
  const items = useMemo(
    () => [
      ...(fields.data || []).map((p) => ({
        id: p.id,
        name: p.name,
        geometry: p.geometry as FieldGeometry,
      })),
      ...(candidates.data || []).map((c) => ({
        id: c.candidate_id,
        name: c.name || "Контур OSM",
        geometry: c.geometry as FieldGeometry,
        candidate: true,
      })),
    ],
    [fields.data, candidates.data],
  );
  function select(id: string) {
    const p = fields.data?.find((p) => p.id === id);
    if (p) {
      setSelected(p);
      setFocus(bounds(p.geometry as FieldGeometry));
      return;
    }
    const c = candidates.data?.find((c) => c.candidate_id === id);
    if (c) {
      setCandidate(c);
      setSelected(null);
      form.setValue("name", c.name || "Новое поле");
      form.setValue("geometry", JSON.stringify(c.geometry));
      setFocus(c.bbox);
    }
  }
  return (
    <div className="page-pad map-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Наблюдение начинается с контура</p>
          <h1>Рабочая карта</h1>
          <p className="muted small">
            Найдите территорию, выберите поле и изучите его историю.
          </p>
        </div>
        <span className="pill">
          {fields.data?.length ?? 0} / {caps.data?.limits.max_polygons ?? "—"}{" "}
          полей
        </span>
      </div>
      <div className="mobile-map-toggle">
        <Button variant="outline" onClick={() => setMobile(!mobile)}>
          {mobile ? "Показать карту" : "Показать панель"}
        </Button>
      </div>
      <div className={`map-layout ${mobile ? "show-panel" : ""}`}>
        <section className="map-panel stack" aria-label="Управление полями">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              regions.mutate();
            }}
            className="stack"
          >
            <div>
              <p className="nav-label">01 / НАЙТИ ТЕРРИТОРИЮ</p>
              <label className="field">
                Город или регион
                <div className="search-row">
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Например, Potsdam"
                    minLength={2}
                    maxLength={150}
                    required
                  />
                  <Button
                    size="icon"
                    aria-label="Найти регион"
                    disabled={regions.isPending}
                  >
                    <Search size={16} />
                  </Button>
                </div>
              </label>
            </div>
            <label className="field">
              Код страны (необязательно)
              <input
                value={country}
                onChange={(e) => setCountry(e.target.value.toUpperCase())}
                maxLength={2}
                pattern="[A-Za-z]{2}"
                placeholder="DE"
              />
            </label>
          </form>
          <ErrorNotice error={regions.error} />
          {regions.data && (
            <div className="result-list">
              {regions.data.items.length ? (
                regions.data.items.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => {
                      setFocus(r.bbox);
                      regions.reset();
                    }}
                  >
                    <MapPin size={14} />
                    {r.name}
                  </button>
                ))
              ) : (
                <p className="muted small">Регион не найден.</p>
              )}
            </div>
          )}
          <Button
            variant="outline"
            onClick={() => discover.mutate()}
            disabled={
              viewport.length !== 4 ||
              discover.isPending ||
              !!(discoveryJob.data && !terminalJob(discoveryJob.data.state))
            }
          >
            Найти контуры OSM на карте
          </Button>
          <p className="micro muted">
            Приблизьте карту: область поиска до{" "}
            {caps.data?.limits.max_discovery_area_km2 ?? 2500} км². OSM содержит
            не все поля.
          </p>
          <ErrorNotice error={discover.error || candidates.error} />
          {discovery && (
            <JobProgress
              id={discovery.job_id}
              onRetry={(j) => setDiscovery({ ...discovery, job_id: j.id })}
            />
          )}
          <div className="result-list">
            {candidates.data?.map((c) => (
              <button
                key={c.candidate_id}
                onClick={() => select(c.candidate_id)}
              >
                {c.name || "Контур OSM"} · {number(c.area_ha, 1)} га
              </button>
            ))}
            {candidates.data?.length === 0 && (
              <p className="muted small">
                В выбранной области контуры не найдены. Нарисуйте свой участок.
              </p>
            )}
          </div>
          <div className="divider" />
          <p className="nav-label">02 / СОХРАНИТЬ ПОЛЕ</p>
          <form
            className="stack"
            onSubmit={form.handleSubmit((d) => {
              setFormError(null);
              try {
                if (!candidate)
                  parseGeometry(d.geometry, caps.data?.limits.max_vertices);
                create.mutate(d);
              } catch (e) {
                setFormError(e as Error);
              }
            })}
          >
            <label className="field">
              Название
              <input
                {...form.register("name")}
                placeholder="Название участка"
              />
            </label>
            <label className="field">
              Культура
              <input {...form.register("crop")} placeholder="Неизвестна" />
            </label>
            <details open={!!geometryValue}>
              <summary className="small">
                Контур GeoJSON / ввод без карты
              </summary>
              <label className="field">
                <span className="sr-only">Геометрия GeoJSON</span>
                <textarea
                  {...form.register("geometry")}
                  onChange={(e) => {
                    setCandidate(null);
                    form.setValue("geometry", e.target.value);
                  }}
                  placeholder='{"type":"Polygon","coordinates":[…]}'
                />
              </label>
            </details>
            {candidate && (
              <span className="pill">
                Выбран контур OSM · {number(candidate.area_ha, 1)} га
              </span>
            )}
            {Object.values(form.formState.errors).map((e, i) => (
              <p role="alert" className="text-destructive small" key={i}>
                {e.message}
              </p>
            ))}
            <ErrorNotice error={formError || create.error} />
            <Button disabled={create.isPending || !caps.data}>
              <Plus size={15} />
              Сохранить поле
            </Button>
          </form>
          <div className="divider" />
          <p className="nav-label">МОИ ПОЛЯ</p>
          <ErrorNotice error={fields.error} retry={() => fields.refetch()} />
          {fields.isPending ? (
            <p>Загружаем поля…</p>
          ) : !fields.data?.length ? (
            <p className="muted small">
              Пока нет полей. Нарисуйте первый контур или вставьте GeoJSON.
            </p>
          ) : (
            <div className="result-list">
              {fields.data.map((p) => (
                <button key={p.id} onClick={() => select(p.id)}>
                  <MapPin size={14} />
                  <span>
                    {p.name}
                    <small>
                      {number(p.area_ha, 1)} га · версия {p.current_version}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
        <div className="map-stage">
          <FieldMap
            items={items}
            focus={focus}
            onBounds={setViewport}
            onSelect={select}
            onDraw={(geometry) => {
              setCandidate(null);
              form.setValue("geometry", JSON.stringify(geometry));
              setMobile(true);
            }}
          />
          {selected && (
            <div className="field-preview">
              <div>
                <span className="eyebrow">ВЫБРАННОЕ ПОЛЕ</span>
                <h2>{selected.name}</h2>
                <p className="muted small">
                  {number(selected.area_ha, 2)} га ·{" "}
                  {selected.crop_type || "Культура неизвестна"}
                </p>
              </div>
              <Button asChild>
                <Link href={`/app/polygons/${selected.id}`}>
                  Открыть анализ <ArrowUpRight size={16} />
                </Link>
              </Button>
              <button
                aria-label="Закрыть карточку"
                className="preview-close"
                onClick={() => setSelected(null)}
              >
                ×
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
