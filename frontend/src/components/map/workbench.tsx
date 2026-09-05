"use client";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { Input } from "@/components/ui/input";

import { Label } from "@/components/ui/label";

import { Badge } from "@/components/ui/badge";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  IconSearch as Search,
  IconArrowUpRight as ArrowUpRight,
  IconMapPin as MapPin,
  IconPlus as Plus,
} from "@tabler/icons-react";
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
import { ErrorNotice, Disclosure } from "@/components/workspace/common";
import { useWorkspace } from "@/components/workspace/provider";
import { JobProgress } from "@/components/workspace/job-progress";
const FieldMap = dynamic(() => import("./field-map").then((m) => m.FieldMap), {
  ssr: false,
  loading: () => (
    <div className="map-wrap relative h-[65dvh] min-h-[430px] overflow-hidden rounded-md border border-border/70 bg-secondary min-[801px]:h-[calc(100dvh-185px)] flex min-h-40 flex-col items-center justify-center gap-4 rounded-md border border-dashed border-border px-6 py-12 text-center text-sm leading-relaxed text-muted-foreground">
      Загружаем карту…
    </div>
  ),
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
  const [selectedPanel, setSelectedPanel] = useState<string | null>(null);
  const panel = selectedPanel ?? (geometryValue ? "create" : "search");
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
      setSelectedPanel("create");
      setSelected(null);
      form.setValue("name", c.name || "Новое поле");
      form.setValue("geometry", JSON.stringify(c.geometry));
      setFocus(c.bbox);
    }
  }
  return (
    <div className="min-w-0 px-4 py-5 sm:px-6 lg:px-8 lg:py-6 [&_h1]:text-[clamp(1.65rem,2.5vw,2.25rem)] [&_h1]:font-normal [&_h1]:leading-tight [&_h1]:tracking-[-0.035em] [&_h2]:text-xl [&_h2]:font-medium [&_h2]:tracking-tight">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-5 [&>div:first-child]:min-w-0 [&_h1]:mb-2">
        <div>
          <h1>Рабочая карта</h1>
          <p className="text-muted-foreground text-sm leading-relaxed">
            Найдите территорию, выберите поле и изучите его историю.
          </p>
        </div>
        <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
          {fields.data?.length ?? 0} / {caps.data?.limits.max_polygons ?? "—"}{" "}
          полей
        </Badge>
      </div>
      <div className="mb-4 min-[801px]:hidden">
        <Button variant="outline" onClick={() => setMobile(!mobile)}>
          {mobile ? "Показать карту" : "Показать панель"}
        </Button>
      </div>
      <div
        className={`group/map grid min-w-0 gap-4 min-[801px]:grid-cols-[300px_minmax(0,1fr)] min-[1280px]:grid-cols-[340px_minmax(0,1fr)] ${mobile ? "is-panel-open" : ""}`}
      >
        <section
          className="hidden content-start rounded-md border border-border/70 bg-card/50 p-4 min-[801px]:grid min-[801px]:max-h-[calc(100dvh-185px)] min-[801px]:overflow-auto max-[800px]:group-[.is-panel-open]/map:grid grid min-w-0 gap-4"
          aria-label="Управление полями"
        >
          <Tabs
            value={panel}
            onValueChange={setSelectedPanel}
            className="min-w-0"
          >
            <TabsList className="mb-4 h-11 w-full rounded-xl bg-secondary/60 p-1">
              <TabsTrigger value="search" className="rounded-lg">
                Поиск
              </TabsTrigger>
              <TabsTrigger value="create" className="rounded-lg">
                Создать
              </TabsTrigger>
              <TabsTrigger value="fields" className="rounded-lg">
                Поля
              </TabsTrigger>
            </TabsList>
            <TabsContent value="search" className="grid gap-4">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  regions.mutate();
                }}
                className="grid min-w-0 gap-4"
              >
                <div>
                  <p className="mb-2 font-mono text-[11px] tracking-wide text-muted-foreground">
                    Найти территорию
                  </p>
                  <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                    Город или регион
                    <div className="flex items-center gap-2 [&_input]:min-w-0">
                      <Input
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
                  </Label>
                </div>
                <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                  Код страны (необязательно)
                  <Input
                    value={country}
                    onChange={(e) => setCountry(e.target.value.toUpperCase())}
                    maxLength={2}
                    pattern="[A-Za-z]{2}"
                    placeholder="DE"
                  />
                </Label>
              </form>
              <ErrorNotice error={regions.error} />
              {regions.data && (
                <div className="grid gap-1 [&_button]:h-auto [&_button]:justify-start [&_button]:whitespace-normal [&_button]:border [&_button]:border-border/60 [&_button]:bg-secondary/40 [&_button]:px-3 [&_button]:py-3 [&_button]:text-left [&_small]:block [&_small]:text-xs [&_small]:text-muted-foreground">
                  {regions.data.items.length ? (
                    regions.data.items.map((r) => (
                      <Button
                        variant="ghost"
                        key={r.id}
                        onClick={() => {
                          setFocus(r.bbox);
                          regions.reset();
                        }}
                      >
                        <MapPin size={14} />
                        {r.name}
                      </Button>
                    ))
                  ) : (
                    <p className="text-muted-foreground text-sm leading-relaxed">
                      Регион не найден.
                    </p>
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
              <p className="text-xs leading-relaxed text-muted-foreground">
                Приблизьте карту: область поиска до{" "}
                {caps.data?.limits.max_discovery_area_km2 ?? 2500} км². OSM
                содержит не все поля.
              </p>
              <ErrorNotice error={discover.error || candidates.error} />
              {discovery && (
                <JobProgress
                  id={discovery.job_id}
                  onRetry={(j) => setDiscovery({ ...discovery, job_id: j.id })}
                />
              )}
              <div className="grid gap-1 [&_button]:h-auto [&_button]:justify-start [&_button]:whitespace-normal [&_button]:border [&_button]:border-border/60 [&_button]:bg-secondary/40 [&_button]:px-3 [&_button]:py-3 [&_button]:text-left [&_small]:block [&_small]:text-xs [&_small]:text-muted-foreground">
                {candidates.data?.map((c) => (
                  <Button
                    variant="ghost"
                    key={c.candidate_id}
                    onClick={() => select(c.candidate_id)}
                  >
                    {c.name || "Контур OSM"} · {number(c.area_ha, 1)} га
                  </Button>
                ))}
                {candidates.data?.length === 0 && (
                  <p className="text-muted-foreground text-sm leading-relaxed">
                    В выбранной области контуры не найдены. Нарисуйте свой
                    участок.
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                className="justify-start px-0 text-primary"
                onClick={() => setSelectedPanel("create")}
              >
                Уже есть контур? Создать поле ↗
              </Button>
            </TabsContent>
            <TabsContent value="create" className="grid gap-4">
              <p className="mb-2 font-mono text-[11px] tracking-wide text-muted-foreground">
                Сохранить поле
              </p>
              <form
                className="grid min-w-0 gap-4"
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
                <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                  Название
                  <Input
                    {...form.register("name")}
                    placeholder="Название участка"
                  />
                </Label>
                <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                  Культура
                  <Input {...form.register("crop")} placeholder="Неизвестна" />
                </Label>
                <Disclosure
                  title="Контур GeoJSON / ввод без карты"
                  autoOpen={!!geometryValue}
                >
                  <Label className="grid min-w-0 gap-2 text-sm font-normal text-muted-foreground">
                    <span className="sr-only">Геометрия GeoJSON</span>
                    <Textarea
                      {...form.register("geometry")}
                      onChange={(e) => {
                        setCandidate(null);
                        form.setValue("geometry", e.target.value);
                      }}
                      placeholder='{"type":"Polygon","coordinates":[…]}'
                    />
                  </Label>
                </Disclosure>
                {candidate && (
                  <Badge className="w-fit max-w-full shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground">
                    Выбран контур OSM · {number(candidate.area_ha, 1)} га
                  </Badge>
                )}
                {Object.values(form.formState.errors).map((e, i) => (
                  <p
                    role="alert"
                    className="text-destructive text-sm leading-relaxed"
                    key={i}
                  >
                    {e.message}
                  </p>
                ))}
                <ErrorNotice error={formError || create.error} />
                <Button disabled={create.isPending || !caps.data}>
                  <Plus size={15} />
                  Сохранить поле
                </Button>
              </form>
            </TabsContent>
            <TabsContent value="fields" className="grid gap-4">
              <p className="mb-2 font-mono text-[11px] tracking-wide text-muted-foreground">
                Мои поля
              </p>
              <ErrorNotice
                error={fields.error}
                retry={() => fields.refetch()}
              />
              {fields.isPending ? (
                <p>Загружаем поля…</p>
              ) : !fields.data?.length ? (
                <p className="text-muted-foreground text-sm leading-relaxed">
                  Пока нет полей. Нарисуйте первый контур или вставьте GeoJSON.
                </p>
              ) : (
                <div className="grid gap-1 [&_button]:h-auto [&_button]:justify-start [&_button]:whitespace-normal [&_button]:border [&_button]:border-border/60 [&_button]:bg-secondary/40 [&_button]:px-3 [&_button]:py-3 [&_button]:text-left [&_small]:block [&_small]:text-xs [&_small]:text-muted-foreground">
                  {fields.data.map((p) => (
                    <Button
                      variant="ghost"
                      key={p.id}
                      onClick={() => select(p.id)}
                    >
                      <MapPin size={14} />
                      <span>
                        {p.name}
                        <small>
                          {number(p.area_ha, 1)} га · версия {p.current_version}
                        </small>
                      </span>
                    </Button>
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </section>
        <div className="relative min-w-0 max-[800px]:group-[.is-panel-open]/map:hidden">
          <FieldMap
            items={items}
            focus={focus}
            onBounds={setViewport}
            onSelect={select}
            onDraw={(geometry) => {
              setCandidate(null);
              form.setValue("geometry", JSON.stringify(geometry));
              setMobile(true);
              setSelectedPanel("create");
            }}
          />
          {selected && (
            <div className="absolute right-5 bottom-16 left-5 flex flex-col items-start justify-between gap-4 rounded-md border border-border bg-card/95 p-5 xl:flex-row xl:items-center">
              <div>
                <span className="mb-2 text-xs font-medium text-muted-foreground">
                  ВЫБРАННОЕ ПОЛЕ
                </span>
                <h2>{selected.name}</h2>
                <p className="text-muted-foreground text-sm leading-relaxed">
                  {number(selected.area_ha, 2)} га ·{" "}
                  {selected.crop_type || "Культура неизвестна"}
                </p>
              </div>
              <Button asChild>
                <Link href={`/app/polygons/${selected.id}`}>
                  Открыть анализ <ArrowUpRight size={16} />
                </Link>
              </Button>
              <Button
                variant="ghost"
                aria-label="Закрыть карточку"
                className="absolute top-1 right-1 size-8! p-0! text-xl text-muted-foreground"
                onClick={() => setSelected(null)}
              >
                ×
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
