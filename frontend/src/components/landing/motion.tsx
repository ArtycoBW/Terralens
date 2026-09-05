"use client";
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
gsap.registerPlugin(ScrollTrigger);
export function LandingMotion() {
  const curtain = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const match = gsap.matchMedia();
    match.add("(prefers-reduced-motion: no-preference)", () => {
      const lenis = new Lenis({
        duration: 1.05,
        smoothWheel: true,
        anchors: true,
        prevent: (node) => !!node.closest('[role="dialog"], [role="listbox"]'),
      });
      lenis.on("scroll", ScrollTrigger.update);
      const tick = (seconds: number) => lenis.raf(seconds * 1000);
      gsap.ticker.add(tick);
      let done = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let ceiling: ReturnType<typeof setTimeout> | undefined;
      const originalOverflow = document.documentElement.style.overflow;
      const context = gsap.context(() => {
        document
          .querySelectorAll("[data-landing] [data-reveal]")
          .forEach((element) => {
            gsap.from(element, {
              y: 24,
              duration: 0.85,
              ease: "power2.out",
              scrollTrigger: { trigger: element, start: "top 93%", once: true },
              clearProps: "transform",
            });
          });
      });
      const reveal = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        clearTimeout(ceiling);
        context.add(() => {
          // Open the visual gate as the curtain STARTS its exit.
          gsap.from("[data-hero] [data-intro]", {
            y: 22,
            duration: 1,
            stagger: 0.11,
            ease: "power3.out",
            clearProps: "transform",
          });
          gsap.from("[data-hero-image]", {
            scale: 1.06,
            duration: 1.8,
            ease: "power2.out",
            clearProps: "transform",
          });
          if (curtain.current)
            gsap.to(curtain.current, {
              yPercent: -100,
              duration: 0.8,
              ease: "power3.inOut",
              onComplete: () => {
                if (curtain.current) curtain.current.style.display = "none";
                document.documentElement.style.overflow = originalOverflow;
                lenis.start();
              },
            });
        });
        try {
          sessionStorage.setItem("terralens-intro", "seen");
        } catch {}
      };
      let first = true;
      try {
        first = !sessionStorage.getItem("terralens-intro");
      } catch {}
      if (first && curtain.current) {
        curtain.current.style.display = "grid";
        document.documentElement.style.overflow = "hidden";
        lenis.stop();
        const started = performance.now();
        const hero =
          document.querySelector<HTMLImageElement>("[data-hero-image]");
        Promise.allSettled([document.fonts.ready, hero?.decode()]).then(() => {
          if (!done)
            timer = setTimeout(
              reveal,
              Math.max(0, 900 - (performance.now() - started)),
            );
        });
        ceiling = setTimeout(reveal, 2600);
      } else reveal();
      const visibility = () => {
        if (document.hidden) lenis.stop();
        else if (done) lenis.start();
      };
      document.addEventListener("visibilitychange", visibility);
      return () => {
        done = true;
        clearTimeout(timer);
        clearTimeout(ceiling);
        document.documentElement.style.overflow = originalOverflow;
        if (curtain.current) curtain.current.style.display = "none";
        document.removeEventListener("visibilitychange", visibility);
        context.revert();
        gsap.ticker.remove(tick);
        lenis.destroy();
      };
    });
    return () => match.revert();
  }, []);
  return (
    <div
      ref={curtain}
      aria-hidden="true"
      className="fixed inset-0 z-50 hidden place-items-center bg-background"
    >
      <span className="text-3xl tracking-[-.05em]">
        TerraLens<span className="ml-1 text-primary">.</span>
      </span>
    </div>
  );
}
