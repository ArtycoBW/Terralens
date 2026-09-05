"use client";
import Image from "next/image";
import { useEffect, useRef, useState, type RefObject } from "react";
import { useHydrated, usePrefersReducedMotion } from "./motion-preference";
import type { HeroSceneState } from "./hero-story-config";
export function PlanetView({ scene }: { scene: RefObject<HeroSceneState> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const hydrated = useHydrated();
  const reducedMotion = usePrefersReducedMotion();
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let stopped = false,
      initiated = false,
      failed = false,
      dispose: (() => void) | undefined;
    const stop = () => {
      dispose?.();
      dispose = undefined;
      initiated = false;
      setReady(false);
    };
    const begin = () => {
      if (
        stopped ||
        initiated ||
        failed ||
        media.matches ||
        !scene.current.active
      )
        return;
      initiated = true;
      import("./planet")
        .then(({ initPlanet }) => {
          if (stopped || !canvas.current || media.matches) {
            initiated = false;
            return;
          }
          try {
            dispose = initPlanet(
              canvas.current,
              () => {
                if (!stopped) setReady(true);
              },
              () => {
                failed = true;
                stop();
              },
              () => ({
                ...scene.current,
                active: scene.current.active && !media.matches,
              }),
            );
          } catch {
            failed = true;
            stop();
          }
        })
        .catch(() => {
          failed = true;
          stop();
        });
    };
    const lost = () => {
      failed = true;
      stop();
    };
    canvas.current?.addEventListener("webglcontextlost", lost);
    const current = canvas.current;
    // Локальный постер виден сразу; тяжёлые шейдеры запускаются при взаимодействии.
    const inputEvents = [
      "pointermove",
      "pointerdown",
      "wheel",
      "touchstart",
      "keydown",
    ] as const;
    inputEvents.forEach((event) =>
      window.addEventListener(event, begin, { passive: true }),
    );
    // Смена настройки приостанавливает кадры, сохраняя живой контекст.
    // forceContextLoss нужен только при окончательном освобождении сцены.
    return () => {
      stopped = true;
      dispose?.();
      current?.removeEventListener("webglcontextlost", lost);
      inputEvents.forEach((event) => window.removeEventListener(event, begin));
    };
  }, [scene]);
  return (
    <div
      className="pointer-events-none absolute inset-0 z-0"
      aria-hidden="true"
    >
      <Image
        data-planet-poster
        src="/assets/earth/planet-poster.webp"
        alt=""
        fill
        preload
        sizes="100vw"
        className="object-cover"
      />
      <canvas
        ref={canvas}
        data-planet
        data-hydrated={hydrated}
        data-ready={ready && !reducedMotion}
        className="absolute inset-0 h-full w-full opacity-0 transition-opacity duration-700 data-[ready=true]:opacity-100"
      />
    </div>
  );
}
