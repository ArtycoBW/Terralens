"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  IconArrowLeft,
  IconArrowRight,
  IconArrowUpRight,
} from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { usePrefersReducedMotion, useHydrated } from "./motion-preference";

const outputs = [
  {
    name: "Ежедневный ряд",
    format: "CSV",
    description:
      "Наблюдения, восстановленные значения и погода для собственных расчётов.",
    image: "season",
  },
  {
    name: "Контур и результат",
    format: "GeoJSON",
    description:
      "Геометрия поля с итогами исследования для вашей геоинформационной системы.",
    image: "fields",
  },
  {
    name: "Полное исследование",
    format: "JSON",
    description:
      "Результаты, аномалии, качество и параметры анализа в одном файле.",
    image: "satellite",
  },
  {
    name: "Происхождение данных",
    format: "Manifest",
    description:
      "Источники, версия модели и контрольные суммы рядом с каждым экспортом.",
    image: "weather",
  },
];
const P = {
  slots: 12,
  cardRatio: 1.36,
  radiusK: 3,
  arcDepth: 0.7,
  drag: 0.16,
  damp: 0.94,
};

/** GetLayers Carousel Spotlight: вогнутое кольцо preserve-3d, инерция и точная остановка. */
export function Outputs() {
  const hydrated = useHydrated();
  const stage = useRef<HTMLDivElement>(null),
    ring = useRef<HTMLDivElement>(null);
  const actions = useRef<{
    go: (delta: number) => void;
    focus: (index: number) => void;
  } | null>(null);
  const [active, setActive] = useState(0);
  const reduce = usePrefersReducedMotion();
  useEffect(() => {
    const element = stage.current!,
      belt = ring.current!;
    const step = 360 / P.slots;
    let rot = 0,
      vel = 0,
      dragging = false,
      lastX = 0,
      downX = 0,
      moved = false;
    let targetIndex = 0,
      settled = true,
      lastRot = NaN,
      lastCard = -1,
      frame = 0,
      visible = false;
    function render() {
      if (rot !== lastRot) {
        belt.style.setProperty("--rot", `${rot}deg`);
        lastRot = rot;
      }
      const slot = ((Math.round(-rot / step) % P.slots) + P.slots) % P.slots;
      const current = slot % outputs.length;
      for (const [index, card] of Array.from(belt.children).entries())
        (card as HTMLElement).dataset.front = String(index === slot);
      if (current !== lastCard) {
        lastCard = current;
        setActive(current);
      }
    }
    function tick() {
      frame = 0;
      if (!visible || document.hidden) return;
      if (!dragging) {
        rot += vel;
        vel *= P.damp;
        if (Math.abs(vel) < 0.05) {
          if (!settled) {
            targetIndex = Math.round(-rot / step);
            settled = true;
          }
          const diff = -targetIndex * step - rot;
          if (Math.abs(diff) < 0.01 || reduce) {
            rot = -targetIndex * step;
            vel = 0;
          } else rot += diff * 0.14;
        } else settled = false;
      }
      render();
      if (dragging || Math.abs(vel) > 0.001 || rot !== -targetIndex * step)
        frame = requestAnimationFrame(tick);
    }
    function wake() {
      if (!frame && visible && !document.hidden)
        frame = requestAnimationFrame(tick);
    }
    function focusSlot(slot: number) {
      const current = Math.round(-rot / step);
      let distance =
        (((slot - (current % P.slots)) % P.slots) + P.slots) % P.slots;
      if (distance > P.slots / 2) distance -= P.slots;
      targetIndex = current + distance;
      settled = true;
      vel = 0;
      wake();
    }
    actions.current = {
      go: (delta) => {
        targetIndex = Math.round(-rot / step) + delta;
        settled = true;
        vel = 0;
        wake();
      },
      focus: (index) => {
        const current = Math.round(-rot / step);
        let distance =
          (((index - (current % outputs.length)) % outputs.length) +
            outputs.length) %
          outputs.length;
        if (distance > outputs.length / 2) distance -= outputs.length;
        targetIndex = current + distance;
        settled = true;
        vel = 0;
        wake();
      },
    };
    function layout() {
      const width = element.clientWidth;
      const cardWidth = Math.min(238, Math.max(150, width * 0.17));
      element.style.setProperty("--cw", `${cardWidth}px`);
      element.style.setProperty("--ch", `${cardWidth * P.cardRatio}px`);
      element.style.setProperty("--r", `${cardWidth * P.radiusK}px`);
      element.style.setProperty(
        "--push",
        `${cardWidth * P.radiusK * (1 - P.arcDepth)}px`,
      );
      element.style.perspective = `${Math.max(700, width * 0.8)}px`;
    }
    const down = (event: PointerEvent) => {
      dragging = true;
      moved = false;
      lastX = downX = event.clientX;
      vel = 0;
      settled = false;
      element.setPointerCapture(event.pointerId);
      wake();
    };
    const move = (event: PointerEvent) => {
      if (!dragging) return;
      const dx = event.clientX - lastX;
      lastX = event.clientX;
      if (Math.abs(event.clientX - downX) > 6) moved = true;
      const delta = -dx * P.drag;
      rot += delta;
      vel = delta;
      wake();
    };
    const up = (event: PointerEvent) => {
      dragging = false;
      settled = false;
      if (element.hasPointerCapture(event.pointerId))
        element.releasePointerCapture(event.pointerId);
      if (!moved) {
        const card = document
          .elementFromPoint(event.clientX, event.clientY)
          ?.closest<HTMLElement>("[data-output-slot]");
        if (card && belt.contains(card))
          focusSlot(Number(card.dataset.outputSlot));
      }
      wake();
    };
    const cancel = () => {
      dragging = false;
      vel = 0;
      settled = false;
      wake();
    };
    const keys = (event: KeyboardEvent) => {
      if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
        event.preventDefault();
        actions.current?.go(event.key === "ArrowRight" ? 1 : -1);
      }
    };
    const resizing = new ResizeObserver(layout);
    resizing.observe(element);
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      wake();
    });
    observer.observe(element.closest("section")!);
    element.addEventListener("pointerdown", down);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", cancel);
    element.addEventListener("keydown", keys);
    document.addEventListener("visibilitychange", wake);
    layout();
    return () => {
      cancelAnimationFrame(frame);
      resizing.disconnect();
      observer.disconnect();
      element.removeEventListener("pointerdown", down);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", cancel);
      element.removeEventListener("keydown", keys);
      document.removeEventListener("visibilitychange", wake);
      actions.current = null;
    };
  }, [reduce]);
  const current = outputs[active];
  return (
    <section
      id="results"
      aria-label="Форматы результатов"
      className="relative z-10 h-svh min-h-[740px] overflow-hidden border-t border-border/50 bg-background"
    >
      <div className="pointer-events-none relative z-10 px-5 pt-[clamp(100px,13vh,155px)] text-center">
        <h2 className="text-[clamp(2.1rem,4.5vw,4.5rem)] leading-[1.05] tracking-[-.045em]">
          Данные остаются
          <br />в ваших руках.
        </h2>
      </div>
      <div
        ref={stage}
        data-output-stage
        role="region"
        aria-label="Галерея форматов: перетаскивайте или используйте стрелки"
        tabIndex={0}
        className="absolute inset-x-0 top-[30%] bottom-[23%] grid cursor-grab touch-pan-y place-items-center outline-none select-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring active:cursor-grabbing [perspective:1200px]"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute text-[28vh] font-medium tracking-tighter text-foreground/[.035]"
        >
          {String(active + 1).padStart(2, "0")}
        </div>
        <div
          ref={ring}
          aria-hidden="true"
          className="relative z-10 h-0 w-0 transform-3d [transform:translateZ(var(--push,210px))_rotateY(var(--rot,0deg))]"
        >
          {Array.from({ length: P.slots }, (_, slot) => {
            const item = outputs[slot % outputs.length];
            return (
              <div
                key={slot}
                data-output-slot={slot}
                data-front={slot === 0}
                style={
                  { "--a": `${(slot * 360) / P.slots}deg` } as CSSProperties
                }
                className="group/card absolute h-[var(--ch,324px)] w-[var(--cw,238px)] transform-3d backface-hidden [left:calc(var(--cw,238px)/-2)] [top:calc(var(--ch,324px)/-2)] [transform:rotateY(var(--a))_translateZ(calc(var(--r,714px)*-1))]"
              >
                <div className="absolute inset-0 overflow-hidden rounded-2xl border border-foreground/15 bg-card shadow-xl transition-transform duration-400 backface-hidden group-hover/card:scale-105 motion-reduce:transition-none">
                  <Image
                    src={`/assets/earth/${item.image}.webp`}
                    alt=""
                    fill
                    sizes="238px"
                    draggable={false}
                    className="object-cover"
                  />
                  <div className="absolute inset-0 bg-linear-to-t from-background/95 via-background/20 to-background/20" />
                  <span className="absolute top-4 left-4 font-mono text-xs text-foreground">
                    .{item.format.toLowerCase()}
                  </span>
                  <h3 className="absolute inset-x-4 bottom-5 text-xl leading-tight tracking-tight text-foreground">
                    {item.name}
                  </h3>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="absolute inset-x-5 bottom-12 z-20 mx-auto max-w-xl text-center sm:bottom-16">
        <div className="flex items-center justify-between gap-5">
          <Button
            variant="outline"
            size="icon"
            className="shrink-0 rounded-full"
            aria-label="Предыдущий формат"
            disabled={!hydrated}
            onClick={() => actions.current?.go(-1)}
          >
            <IconArrowLeft size={18} />
          </Button>
          <div aria-live="polite" className="min-w-0">
            <p className="text-lg font-medium">{current.name}</p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {current.description}
            </p>
          </div>
          <Button
            variant="outline"
            size="icon"
            className="shrink-0 rounded-full"
            aria-label="Следующий формат"
            disabled={!hydrated}
            onClick={() => actions.current?.go(1)}
          >
            <IconArrowRight size={18} />
          </Button>
        </div>
        <div className="mt-5 flex justify-center gap-2">
          {outputs.map((item, index) => (
            <Button
              key={item.format}
              variant="ghost"
              size="icon"
              className="size-8 rounded-full"
              aria-label={`Показать ${item.format}`}
              disabled={!hydrated}
              aria-pressed={active === index}
              onClick={() => actions.current?.focus(index)}
            >
              <span
                className={
                  active === index
                    ? "size-1.5 rounded-full bg-primary"
                    : "size-1.5 rounded-full bg-muted-foreground/50"
                }
              />
            </Button>
          ))}
        </div>
        <Link
          href="/app/polygons"
          className="mt-3 inline-flex items-center gap-2 py-2 text-sm text-primary"
        >
          К исследованиям <IconArrowUpRight size={16} />
        </Link>
      </div>
    </section>
  );
}
