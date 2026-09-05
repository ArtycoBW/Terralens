"use client";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { useHydrated } from "./motion-preference";
export function PlanetView() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  const hydrated = useHydrated();
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let stopped = false,
      initiated = false,
      failed = false,
      revealTimer: ReturnType<typeof setTimeout> | undefined,
      dispose: (() => void) | undefined;
    const stop = () => {
      dispose?.();
      dispose = undefined;
      clearTimeout(revealTimer);
      initiated = false;
      setReady(false);
    };
    const begin = () => {
      if (
        stopped ||
        initiated ||
        failed ||
        media.matches ||
        scrollY > innerHeight * 1.25
      )
        return;
      initiated = true;
      import("./planet")
        .then(({ initPlanet }) => {
          if (stopped || !canvas.current || media.matches) return;
          try {
            dispose = initPlanet(
              canvas.current,
              () => {
                revealTimer = setTimeout(() => {
                  if (!stopped) setReady(true);
                }, 2000);
              },
              () => {
                failed = true;
                stop();
              },
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
    // The local poster paints immediately; expensive shaders start on user input.
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
    const preference = () => {
      if (media.matches) stop();
    };
    media.addEventListener("change", preference);
    return () => {
      stopped = true;
      clearTimeout(revealTimer);
      dispose?.();
      current?.removeEventListener("webglcontextlost", lost);
      media.removeEventListener("change", preference);
      inputEvents.forEach((event) => window.removeEventListener(event, begin));
    };
  }, []);
  return (
    <div className="pointer-events-none fixed inset-0 z-0" aria-hidden="true">
      <Image
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
        data-ready={ready}
        className="absolute inset-0 h-full w-full opacity-0 transition-opacity duration-700 data-[ready=true]:opacity-100"
      />
    </div>
  );
}
