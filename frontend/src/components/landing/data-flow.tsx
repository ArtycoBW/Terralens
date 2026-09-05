"use client";

import { useRef } from "react";
import {
  IconSatellite,
  IconCloud,
  IconChartLine,
  IconLeaf,
} from "@tabler/icons-react";
import { AnimatedBeam } from "@/components/ui/animated-beam";

export function DataFlow() {
  const container = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null),
    landsat = useRef<HTMLDivElement>(null),
    weather = useRef<HTMLDivElement>(null),
    core = useRef<HTMLDivElement>(null),
    result = useRef<HTMLDivElement>(null);
  return (
    <figure aria-labelledby="data-flow-caption" className="min-w-0">
      <div
        ref={container}
        className="relative grid h-[370px] grid-cols-[1fr_1fr_1fr] items-center gap-2 px-1 sm:px-8"
      >
        <div className="flex h-full flex-col items-center justify-between py-7">
          {[
            [sentinel, IconSatellite, "Sentinel-2"],
            [landsat, IconSatellite, "Landsat 8/9"],
            [weather, IconCloud, "ERA5"],
          ].map(([ref, Icon, label], i) => {
            const Element = Icon as typeof IconSatellite;
            return (
              <div
                key={i}
                className="relative z-10 flex flex-col items-center gap-2 bg-background py-2"
              >
                <div
                  ref={ref as typeof sentinel}
                  className="grid size-10 place-items-center rounded-md border border-border bg-card sm:size-12"
                >
                  <Element size={22} stroke={1.3} />
                </div>
                <span className="font-mono text-[10px] text-muted-foreground sm:text-xs">
                  {label as string}
                </span>
              </div>
            );
          })}
        </div>
        <div className="relative z-10 flex flex-col items-center gap-3">
          <div
            ref={core}
            className="grid size-16 place-items-center rounded-full border border-primary/40 bg-background sm:size-20"
          >
            <IconLeaf size={32} stroke={1.3} className="text-primary" />
          </div>
          <span className="bg-background px-2 text-sm tracking-tight">
            TerraLens
          </span>
        </div>
        <div className="relative z-10 flex flex-col items-center gap-3">
          <div
            ref={result}
            className="grid size-12 place-items-center rounded-md border border-border bg-card sm:size-14"
          >
            <IconChartLine size={27} stroke={1.3} />
          </div>
          <span className="bg-background px-2 text-center font-mono text-[10px] text-muted-foreground sm:text-xs">
            Динамика поля
          </span>
        </div>
        <AnimatedBeam
          containerRef={container}
          fromRef={sentinel}
          toRef={core}
          curvature={-55}
          startXOffset={24}
          endXOffset={-32}
          endYOffset={-12}
          delay={0}
        />
        <AnimatedBeam
          containerRef={container}
          fromRef={landsat}
          toRef={core}
          startXOffset={24}
          endXOffset={-32}
          delay={0.5}
        />
        <AnimatedBeam
          containerRef={container}
          fromRef={weather}
          toRef={core}
          curvature={55}
          startXOffset={24}
          endXOffset={-32}
          endYOffset={12}
          delay={1}
        />
        <AnimatedBeam
          containerRef={container}
          fromRef={core}
          toRef={result}
          startXOffset={32}
          endXOffset={-24}
          delay={2}
        />
      </div>
      <figcaption
        id="data-flow-caption"
        className="mt-1 text-center text-xs leading-relaxed text-muted-foreground"
      >
        Наблюдения и погода объединяются в историю выбранного поля.
      </figcaption>
    </figure>
  );
}
