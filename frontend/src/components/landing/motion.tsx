"use client";
import { useEffect } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
gsap.registerPlugin(ScrollTrigger);

export function LandingMotion() {
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
      // Hero из серверного HTML виден с первого кадра, без ожидания загрузки.
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
      const visibility = () => (document.hidden ? lenis.stop() : lenis.start());
      document.addEventListener("visibilitychange", visibility);
      return () => {
        document.removeEventListener("visibilitychange", visibility);
        context.revert();
        gsap.ticker.remove(tick);
        lenis.destroy();
      };
    });
    return () => match.revert();
  }, []);
  return null;
}
