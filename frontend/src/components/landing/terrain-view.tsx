"use client";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "./motion-preference";
import {
  IconPlus,
  IconMinus,
  IconRefresh,
  IconRotate3d,
} from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TERRAIN_MARKERS, type TerrainController } from "./terrain-data";

export function TerrainView() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const markers = useRef<(HTMLButtonElement | null)[]>([]);
  const controller = useRef<TerrainController | null>(null);
  const reduce = usePrefersReducedMotion();
  const [started, setStarted] = useState(false);
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const enabled = reduce === false || started;
  useEffect(() => {
    const element = canvas.current;
    if (!element || !enabled) return;
    let cancelled = false;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        import("./terrain-scene")
          .then(({ mountTerrain }) => {
            if (cancelled) return;
            try {
              controller.current = mountTerrain(
                element,
                markers.current,
                !reduce,
              );
              setReady(true);
            } catch {
              setReady(false);
            }
          })
          .catch(() => {
            if (!cancelled) setReady(false);
          });
      },
      { rootMargin: "100px" },
    );
    observer.observe(element);
    const lost = () => {
      if (!cancelled) setReady(false);
      markers.current.forEach((marker) => {
        if (marker) marker.dataset.visible = "false";
      });
    };
    element.addEventListener("webglcontextlost", lost);
    return () => {
      cancelled = true;
      observer.disconnect();
      element.removeEventListener("webglcontextlost", lost);
      controller.current?.dispose();
      controller.current = null;
      element.dataset.ready = "false";
    };
  }, [enabled, reduce]);
  return (
    <figure className="min-w-0" aria-label="Интерактивная модель рельефа">
      <div
        className="group/terrain relative aspect-[1.12] min-h-80 w-full overflow-hidden rounded-2xl border border-border/50 bg-card/40"
        data-lenis-prevent
      >
        <div className="pointer-events-none absolute inset-x-5 top-5 z-10 flex items-center justify-between gap-3">
          <span className="font-mono text-[10px] tracking-wide text-muted-foreground">
            МОДЕЛЬ РЕЛЬЕФА
          </span>
          <span className="text-[10px] text-muted-foreground">Иллюстрация</span>
        </div>
        <Image
          src="/assets/earth/terrain-poster.webp"
          alt="Иллюстрация объёмного рельефа с линиями высоты"
          fill
          sizes="(max-width: 1000px) 100vw, 55vw"
          className="object-contain group-has-[[data-ready=true]]/terrain:invisible"
        />
        <canvas
          ref={canvas}
          data-terrain
          tabIndex={ready ? 0 : -1}
          role="img"
          aria-label="Рельеф: стрелки вращают, плюс и минус изменяют масштаб, Home сбрасывает вид"
          className="absolute inset-0 h-full w-full cursor-grab touch-none invisible outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring active:cursor-grabbing data-[ready=true]:visible"
          onKeyDown={(event) => {
            const action = {
              ArrowLeft: () => controller.current?.rotate(-0.18),
              ArrowRight: () => controller.current?.rotate(0.18),
              ArrowUp: () => controller.current?.rotate(0, -0.12),
              ArrowDown: () => controller.current?.rotate(0, 0.12),
              "+": () => controller.current?.zoom(0.85),
              "=": () => controller.current?.zoom(0.85),
              "-": () => controller.current?.zoom(1.15),
              Home: () => controller.current?.reset(),
            }[event.key];
            if (action) {
              event.preventDefault();
              action();
            }
          }}
        />
        <TooltipProvider delayDuration={100}>
          {TERRAIN_MARKERS.map((marker, i) => (
            <Tooltip
              key={marker.id}
              open={active === i}
              onOpenChange={(open) => setActive(open ? i : null)}
            >
              <TooltipTrigger asChild>
                <Button
                  ref={(el) => {
                    markers.current[i] = el;
                  }}
                  variant="ghost"
                  size="icon"
                  aria-label={`Метка: ${marker.title}`}
                  className="absolute top-0 left-0 z-20 hidden size-10 rounded-full hover:bg-transparent data-[visible=true]:inline-flex"
                  onClick={() => setActive(active === i ? null : i)}
                >
                  <span className="absolute size-7 rounded-full border border-primary/60 bg-primary/15 motion-safe:animate-ping [animation-duration:2.6s]" />
                  <span className="relative size-3 rounded-full border-2 border-background bg-primary shadow-[0_0_0_4px_#ebfc7225]" />
                </Button>
              </TooltipTrigger>
              <TooltipContent
                side="top"
                sideOffset={8}
                className="max-w-60 rounded-xl border border-border bg-popover p-4 text-foreground shadow-xl"
              >
                <p className="font-medium">{marker.title}</p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  {marker.text}
                </p>
              </TooltipContent>
            </Tooltip>
          ))}
        </TooltipProvider>
        <div className="absolute inset-x-0 bottom-4 z-10 flex justify-center">
          {ready ? (
            <div className="flex items-center gap-1 rounded-full border border-border bg-background/90 p-1 backdrop-blur">
              <Button
                variant="ghost"
                size="icon"
                className="size-10 rounded-full"
                aria-label="Приблизить рельеф"
                onClick={() => controller.current?.zoom(0.8)}
              >
                <IconPlus size={17} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-10 rounded-full"
                aria-label="Отдалить рельеф"
                onClick={() => controller.current?.zoom(1.25)}
              >
                <IconMinus size={17} />
              </Button>
              <span className="mx-1 h-4 w-px bg-border" />
              <Button
                variant="ghost"
                size="icon"
                className="size-10 rounded-full"
                aria-label="Сбросить вид рельефа"
                onClick={() => controller.current?.reset()}
              >
                <IconRefresh size={17} />
              </Button>
            </div>
          ) : !enabled ? (
            <Button
              variant="outline"
              className="rounded-full"
              onClick={() => setStarted(true)}
            >
              <IconRotate3d size={18} />
              Исследовать в 3D
            </Button>
          ) : (
            <span className="rounded-full bg-background/80 px-4 py-2 text-xs text-muted-foreground">
              Статичный вид рельефа
            </span>
          )}
        </div>
      </div>
      <figcaption className="mt-4 text-center text-xs leading-relaxed text-muted-foreground">
        {ready
          ? "Перетаскивайте для вращения. Колесо или кнопки меняют масштаб."
          : "Рельеф помогает увидеть, как положение участка влияет на условия поля."}
      </figcaption>
    </figure>
  );
}
