"use client";

import Link from "next/link";
import { useLayoutEffect, useRef } from "react";
import {
  IconArrowDown,
  IconArrowRight,
  IconArrowUpRight,
} from "@tabler/icons-react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { Button } from "@/components/ui/button";
import { PlanetView } from "./planet-view";
import { HERO_CHAPTERS, ramp, type HeroSceneState } from "./hero-story-config";

gsap.registerPlugin(ScrollTrigger);

export function HeroStory() {
  const root = useRef<HTMLElement>(null);
  const scene = useRef<HeroSceneState>({ progress: 0, active: true });

  useLayoutEffect(() => {
    const element = root.current!;
    const stage = element.querySelector<HTMLElement>("[data-hero-stage]")!;
    const panels = Array.from(
      element.querySelectorAll<HTMLElement>("[data-story-panel]"),
    );
    const progressLine = element.querySelector<HTMLElement>(
      "[data-story-progress]",
    )!;
    const counter = element.querySelector<HTMLElement>("[data-story-counter]")!;
    const poster = element.querySelector<HTMLElement>("[data-planet-poster]")!;
    const match = gsap.matchMedia();
    match.add(
      "(prefers-reduced-motion: no-preference) and (min-width: 360px) and (min-height: 680px)",
      () => {
        element.dataset.motion = "true";
        panels
          .slice(1)
          .forEach((panel) => panel.setAttribute("aria-hidden", "true"));
        const paint = (progress: number) => {
          scene.current.progress = progress;
          element.dataset.progress = progress.toFixed(4);
          const opacities = [
            1 - ramp(progress, 0.04, 0.14),
            ...HERO_CHAPTERS.map(
              (chapter) =>
                ramp(progress, chapter.enter[0], chapter.enter[1]) *
                (1 - ramp(progress, chapter.exit[0], chapter.exit[1])),
            ),
          ];
          panels.forEach((panel, index) => {
            const opacity = opacities[index];
            panel.style.opacity = String(opacity);
            panel.style.visibility = opacity < 0.001 ? "hidden" : "visible";
            panel.style.transform = `translateY(${(1 - opacity) * (index === 0 ? -20 : 24)}px)`;
            // Невидимые кнопки не попадают в порядок клавиатурного фокуса.
            panel.inert = opacity < 0.5;
          });
          progressLine.style.transform = `scaleX(${progress})`;
          const chapter =
            progress < 0.16 ? 0 : progress < 0.46 ? 1 : progress < 0.76 ? 2 : 3;
          counter.textContent = `${String(chapter + 1).padStart(2, "0")} / 04`;
          // При недоступном WebGL постер сохраняется, но не мешает чтению.
          poster.style.opacity = String(1 - ramp(progress, 0.04, 0.23) * 0.7);
        };
        const trigger = ScrollTrigger.create({
          trigger: element,
          start: "top top",
          end: () => `+=${element.offsetHeight - stage.offsetHeight}`,
          onUpdate: (self) => paint(self.progress),
          onRefresh: (self) => paint(self.progress),
          invalidateOnRefresh: true,
        });
        paint(trigger.progress);
        // Размер пути должен быть известен остальным секциям и якорным ссылкам.
        const refresh = requestAnimationFrame(() => ScrollTrigger.refresh());
        return () => {
          cancelAnimationFrame(refresh);
          trigger.kill();
          delete element.dataset.motion;
          delete element.dataset.progress;
          scene.current.progress = 0;
          panels.forEach((panel) => {
            panel.removeAttribute("style");
            panel.inert = false;
            panel.removeAttribute("aria-hidden");
          });
          poster.style.removeProperty("opacity");
        };
      },
    );
    const observer = new IntersectionObserver(([entry]) => {
      scene.current.active = entry.isIntersecting;
    });
    observer.observe(element.querySelector("[data-planet]")!);
    return () => {
      observer.disconnect();
      match.revert();
    };
  }, []);

  return (
    <section
      ref={root}
      data-hero
      aria-label="TerraLens: спутниковая аналитика"
      className="group/hero relative z-10 data-[motion=true]:h-[500svh]"
    >
      <div
        data-hero-stage
        className="relative group-data-[motion=true]/hero:sticky group-data-[motion=true]/hero:top-0 group-data-[motion=true]/hero:h-svh group-data-[motion=true]/hero:overflow-clip"
      >
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-svh"
          aria-hidden="true"
        >
          <PlanetView scene={scene} />
        </div>
        <div
          data-story-panel="intro"
          data-hero-copy
          className="relative flex min-h-svh flex-col items-center px-5 pt-[clamp(135px,18svh,200px)] pb-28 text-center group-data-[motion=true]/hero:absolute group-data-[motion=true]/hero:inset-0"
        >
          <div className="max-w-4xl">
            <p className="mb-6 font-mono text-xs text-primary">
              Спутниковая аналитика территорий
            </p>
            <h1 className="text-[clamp(1.6rem,8.5vw,2.65rem)] leading-[1.04] tracking-[-.045em] sm:text-[clamp(2.65rem,5.6vw,5rem)]">
              Состояние полей.
              <br />В динамике сезона.
            </h1>
            <p className="mx-auto mt-6 max-w-lg text-base leading-relaxed text-foreground/85 sm:text-lg">
              Спутниковая история, погода и восстановленный NDVI для каждого
              контура.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
              <Button
                asChild
                size="lg"
                className="h-13 gap-5 rounded-full px-6 text-sm"
              >
                <Link href="/app">
                  Исследовать поле <IconArrowUpRight size={18} />
                </Link>
              </Button>
              <Button
                asChild
                size="lg"
                variant="outline"
                className="h-13 gap-4 rounded-full border-foreground/20 bg-background/90 px-6 text-foreground dark:bg-background/90"
              >
                <a href="#workflow">
                  Как это работает <IconArrowRight size={16} />
                </a>
              </Button>
            </div>
          </div>
        </div>
        {HERO_CHAPTERS.map((chapter, index) => (
          <article
            key={chapter.label}
            data-story-panel={chapter.label}
            data-side={chapter.side}
            className="relative mx-auto max-w-6xl border-t border-border/60 px-6 py-16 group-data-[motion=true]/hero:absolute group-data-[motion=true]/hero:inset-x-0 group-data-[motion=true]/hero:top-[52%] group-data-[motion=true]/hero:border-0 group-data-[motion=true]/hero:py-0 md:px-10 md:group-data-[motion=true]/hero:top-[33%] lg:px-12"
          >
            <div
              className={`max-w-lg ${chapter.side === "right" ? "md:group-data-[motion=true]/hero:ml-[55%]" : "md:group-data-[motion=true]/hero:mr-[55%]"}`}
            >
              <p className="mb-4 flex items-center gap-4 font-mono text-[11px] text-primary sm:mb-6">
                <span className="h-px w-6 bg-primary/65" />0{index + 1} /{" "}
                {chapter.label}
              </p>
              <h2 className="max-w-[14ch] text-[clamp(1.9rem,4.1vw,3.75rem)] leading-[1.07] tracking-[-.04em]">
                {chapter.title}
              </h2>
              <p className="mt-5 max-w-[42ch] text-sm leading-relaxed text-foreground/80 lg:mt-7 lg:text-base">
                {chapter.body}
              </p>
              <p className="mt-6 border-t border-foreground/15 pt-4 font-mono text-[10px] leading-relaxed text-muted-foreground sm:text-[11px] [@media(max-height:780px)]:group-data-[motion=true]/hero:hidden">
                {chapter.detail}
              </p>
            </div>
          </article>
        ))}
        <div className="absolute inset-x-6 bottom-7 hidden items-end justify-between gap-6 group-data-[motion=true]/hero:flex sm:inset-x-10 lg:inset-x-16">
          <div className="w-24 sm:w-40" aria-hidden="true">
            <span
              data-story-counter
              className="font-mono text-[10px] text-foreground/70"
            >
              01 / 04
            </span>
            <div className="mt-3 h-px overflow-hidden bg-foreground/20">
              <div
                data-story-progress
                className="h-full origin-left bg-primary"
                style={{ transform: "scaleX(0)" }}
              />
            </div>
          </div>
          <a
            href="#features"
            className="flex items-center gap-3 rounded-full py-2 font-mono text-[10px] text-foreground/80 hover:text-primary sm:text-[11px]"
          >
            К возможностям <IconArrowDown size={14} />
          </a>
        </div>
      </div>
      <ol
        aria-label="От контура к анализу"
        className="hidden group-data-[motion=true]/hero:sr-only group-data-[motion=true]/hero:block"
      >
        {HERO_CHAPTERS.map((chapter) => (
          <li key={chapter.label}>
            <h2>{chapter.title}</h2>
            <p>{chapter.body}</p>
            <p>{chapter.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
