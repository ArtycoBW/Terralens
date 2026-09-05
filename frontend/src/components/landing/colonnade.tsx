"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { IconArrowUpRight } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const chapters = [
  {
    name: "Территория",
    title: "Начните с вашего поля",
    text: "Контур на карте, из OpenStreetMap или вашего GeoJSON.",
    action: "Открыть карту",
    href: "/app",
    position: "50% 50%",
    image: "/assets/earth/fields.webp",
  },
  {
    name: "Наблюдения",
    title: "Увидьте историю с орбиты",
    text: "Доступные снимки Sentinel-2 и Landsat за выбранный период.",
    action: "Выбрать поле",
    href: "/app/polygons",
    position: "65% 30%",
    image: "/assets/earth/satellite.webp",
  },
  {
    name: "Динамика",
    title: "Найдите изменения в сезоне",
    text: "Восстановленный NDVI и сравнение до четырёх анализов.",
    action: "Сравнить сезоны",
    href: "/app/compare",
    position: "50% 50%",
    image: "/assets/earth/season.webp",
  },
  {
    name: "Контекст",
    title: "Проверьте каждый сигнал",
    text: "Погода, сезонная норма и происхождение каждого значения.",
    action: "Проверить качество",
    href: "/app/data-quality",
    position: "50% 50%",
    image: "/assets/earth/weather.webp",
  },
] as const;

// GetLayers Colonnade: preserve the upward conveyor, 900ms curve and silent reset.
const layer =
  "absolute inset-0 translate-y-[101%] transition-transform duration-900 ease-[cubic-bezier(.76,0,.18,1)] data-[motion=in]:translate-y-0 data-[motion=out]:-translate-y-[101%] motion-reduce:transition-none";
export function Colonnade() {
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const current = useRef(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const media = useRef<(HTMLDivElement | null)[]>([]);
  const heads = useRef<(HTMLDivElement | null)[]>([]);
  const cleanups = useRef<(() => void)[]>([]);

  function move(element: HTMLDivElement | null, state: "in" | "out") {
    if (!element) return;
    if (state === "in" && element.dataset.motion === "out") {
      element.style.transition = "none";
      element.dataset.motion = "rest";
      void element.offsetHeight;
      element.style.transition = "";
    }
    element.dataset.motion = state;
  }
  function activate(index: number, focus = false) {
    if (index !== current.current) {
      move(media.current[current.current], "out");
      move(heads.current[current.current], "out");
      move(media.current[index], "in");
      move(heads.current[index], "in");
      current.current = index;
      setActive(index);
    }
    if (focus) buttons.current[index]?.focus();
  }
  useEffect(() => {
    for (const element of [...media.current, ...heads.current]) {
      if (!element) continue;
      const reset = (event: TransitionEvent) => {
        if (
          event.target !== element ||
          event.propertyName !== "transform" ||
          element.dataset.motion !== "out"
        )
          return;
        element.style.transition = "none";
        element.dataset.motion = "rest";
        void element.offsetHeight;
        element.style.transition = "";
      };
      element.addEventListener("transitionend", reset);
      cleanups.current.push(() =>
        element.removeEventListener("transitionend", reset),
      );
    }
    const cleanup = cleanups.current;
    return () => {
      cleanup.forEach((fn) => fn());
      cleanups.current = [];
    };
  }, []);
  return (
    <section
      id="features"
      aria-label="Возможности TerraLens"
      className="relative z-10 scroll-mt-0 bg-background"
    >
      <div
        ref={root}
        className="relative isolate h-svh min-h-[760px] overflow-hidden bg-background min-[861px]:min-h-[640px]"
      >
        <div
          role="tablist"
          aria-label="Возможности"
          className="absolute inset-0 flex flex-col max-[860px]:top-[380px] min-[861px]:flex-row"
        >
          {chapters.map((chapter, i) => (
            <div
              key={chapter.name}
              className={cn(
                "relative min-h-16 min-w-0 basis-0 overflow-hidden border-t border-border/60 transition-[flex-grow] duration-900 ease-[cubic-bezier(.76,0,.18,1)] first:border-0 min-[861px]:border-t-0 min-[861px]:border-l motion-reduce:transition-none",
                active === i ? "grow-[3.4] min-[861px]:grow-[2.5]" : "grow",
              )}
            >
              <div
                ref={(el) => {
                  media.current[i] = el;
                }}
                data-motion={i === 0 ? "in" : "rest"}
                className={layer}
                aria-hidden="true"
              >
                <Image
                  src={chapter.image}
                  alt=""
                  fill
                  sizes="(max-width: 860px) 100vw, 48vw"
                  className="object-cover brightness-[.7]"
                  style={{ objectPosition: chapter.position }}
                />
              </div>
              <Button
                ref={(el) => {
                  buttons.current[i] = el;
                }}
                id={`chapter-${i}`}
                role="tab"
                aria-selected={active === i}
                aria-controls={`chapter-panel-${i}`}
                aria-label={chapter.name}
                tabIndex={active === i ? 0 : -1}
                variant="ghost"
                className="absolute inset-0 h-full w-full items-end justify-start rounded-none p-5 text-left font-normal hover:bg-transparent focus-visible:ring-inset min-[861px]:p-7"
                onPointerEnter={() => {
                  if (matchMedia("(hover: hover) and (pointer: fine)").matches)
                    activate(i);
                }}
                onClick={() => activate(i)}
                onFocus={() => activate(i)}
                onKeyDown={(event) => {
                  const next =
                    event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? 3
                        : ["ArrowRight", "ArrowDown"].includes(event.key)
                          ? (i + 1) % 4
                          : ["ArrowLeft", "ArrowUp"].includes(event.key)
                            ? (i + 3) % 4
                            : null;
                  if (next != null) {
                    event.preventDefault();
                    activate(next, true);
                  }
                }}
              >
                <span
                  className={cn(
                    "flex w-full items-center justify-between text-base tracking-tight min-[861px]:text-xl",
                    active === i ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {chapter.name}
                  <IconArrowUpRight
                    size={18}
                    className={active === i ? "opacity-100" : "opacity-0"}
                  />
                </span>
              </Button>
            </div>
          ))}
        </div>
        <div className="pointer-events-none absolute top-24 right-5 left-5 hidden text-center font-mono text-xs text-muted-foreground min-[861px]:block">
          Возможности TerraLens
        </div>
        <div className="pointer-events-none absolute inset-x-5 top-[104px] h-[260px] overflow-hidden min-[861px]:inset-x-[15%] min-[861px]:top-[24%] min-[861px]:h-[350px]">
          {chapters.map((chapter, i) => (
            <div
              key={chapter.name}
              ref={(el) => {
                heads.current[i] = el;
              }}
              id={`chapter-panel-${i}`}
              role="tabpanel"
              aria-labelledby={`chapter-${i}`}
              aria-hidden={active !== i}
              inert={active !== i}
              data-motion={i === 0 ? "in" : "rest"}
              className={cn(layer, "flex flex-col items-center text-center")}
            >
              <h2 className="max-w-[680px] text-[clamp(2.1rem,4.8vw,4.5rem)] leading-[1.04] font-normal tracking-[-.045em] text-balance">
                {chapter.title}
              </h2>
              <p className="mt-5 max-w-md text-sm leading-relaxed text-foreground min-[861px]:text-base">
                {chapter.text}
              </p>
              <Button
                asChild
                variant="outline"
                className="pointer-events-auto mt-7 h-11 border-foreground/35 bg-background/85 px-5 font-mono text-xs backdrop-blur-sm hover:bg-foreground hover:text-background"
              >
                <Link href={chapter.href}>
                  {chapter.action}
                  <IconArrowUpRight size={16} />
                </Link>
              </Button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
