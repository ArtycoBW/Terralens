"use client";
import { useEffect, useRef, useState } from "react";
export function PlanetView() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let stopped = false,
      dispose: (() => void) | undefined;
    const stop = () => {
      dispose?.();
      dispose = undefined;
      setReady(false);
    };
    const begin = () => {
      if (media.matches) {
        stop();
        return;
      }
      import("./planet")
        .then(({ initPlanet }) => {
          if (stopped || !canvas.current || media.matches) return;
          try {
            dispose = initPlanet(
              canvas.current,
              () => {
                if (!stopped) setReady(true);
              },
              () => stop(),
            );
          } catch {
            stop();
          }
        })
        .catch(stop);
    };
    const lost = () => stop();
    canvas.current?.addEventListener("webglcontextlost", lost);
    const current = canvas.current;
    begin();
    media.addEventListener("change", begin);
    return () => {
      stopped = true;
      dispose?.();
      current?.removeEventListener("webglcontextlost", lost);
      media.removeEventListener("change", begin);
    };
  }, []);
  return (
    <div className="planet-backdrop" aria-hidden="true">
      <div className="planet-poster" />
      <canvas
        ref={canvas}
        className={ready ? "planet-canvas ready" : "planet-canvas"}
      />
    </div>
  );
}
