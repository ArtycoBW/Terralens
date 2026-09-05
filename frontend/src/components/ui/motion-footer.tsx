"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { motion, useInView, useMotionValue, useSpring } from "motion/react";
import { IconArrowUp, IconArrowUpRight, IconLeaf } from "@tabler/icons-react";
import { Button } from "./button";
import { useMotionEnabled } from "@/components/landing/motion-preference";

function MagneticLink({
  href,
  children,
  primary = false,
}: {
  href: string;
  children: React.ReactNode;
  primary?: boolean;
}) {
  const enabled = useMotionEnabled();
  const x = useMotionValue(0),
    y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 220, damping: 24 });
  const springY = useSpring(y, { stiffness: 220, damping: 24 });
  return (
    <motion.div
      style={{ x: enabled ? springX : 0, y: enabled ? springY : 0 }}
      onPointerMove={(event) => {
        if (!enabled || event.pointerType !== "mouse") return;
        const rect = event.currentTarget.getBoundingClientRect();
        x.set((event.clientX - rect.left - rect.width / 2) * 0.09);
        y.set((event.clientY - rect.top - rect.height / 2) * 0.12);
      }}
      onPointerLeave={() => {
        x.set(0);
        y.set(0);
      }}
    >
      <Button
        asChild
        variant={primary ? "default" : "outline"}
        size="lg"
        className="h-14 gap-5 rounded-full px-7 text-sm"
      >
        <Link href={href}>
          {children}
          <IconArrowUpRight size={18} />
        </Link>
      </Button>
    </motion.div>
  );
}

/** User-supplied CinematicFooter: curtain, diagonal ticker, magnetic links, oversized wordmark. */
export function CinematicFooter() {
  const wrapper = useRef<HTMLDivElement>(null);
  const enabled = useMotionEnabled();
  const visible = useInView(wrapper, { amount: 0.1 });
  useEffect(() => {
    if (!enabled) return;
    gsap.registerPlugin(ScrollTrigger);
    const context = gsap.context(() => {
      gsap.fromTo(
        "[data-footer-wordmark]",
        { y: 80, scale: 0.9 },
        {
          y: 0,
          scale: 1,
          ease: "none",
          scrollTrigger: {
            trigger: wrapper.current,
            start: "top bottom",
            end: "bottom bottom",
            scrub: 1,
          },
        },
      );
      gsap.from("[data-footer-copy]", {
        y: 35,
        ease: "none",
        scrollTrigger: {
          trigger: wrapper.current,
          start: "top 70%",
          end: "bottom bottom",
          scrub: 1,
        },
      });
    }, wrapper);
    return () => context.revert();
  }, [enabled]);
  return (
    <div
      ref={wrapper}
      id="contact"
      className="relative z-10 h-svh min-h-[680px] w-full [clip-path:polygon(0%_0,100%_0,100%_100%,0_100%)]"
    >
      <footer className="fixed inset-x-0 bottom-0 flex h-svh min-h-[680px] flex-col justify-between overflow-hidden bg-background text-foreground">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#f4f3e805_1px,transparent_1px),linear-gradient(to_bottom,#f4f3e805_1px,transparent_1px)] bg-size-[64px_64px] mask-[radial-gradient(ellipse_at_center,black,transparent_75%)]"
        />
        <div
          data-footer-wordmark
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-[3vw] left-1/2 -translate-x-1/2 bg-linear-to-b from-foreground/10 to-transparent bg-clip-text text-[22vw] leading-none font-semibold tracking-[-.07em] whitespace-nowrap text-transparent select-none [-webkit-text-stroke:1px_#f4f3e809]"
        >
          TERRALENS
        </div>
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-20 -rotate-2 scale-105 overflow-hidden border-y border-border/70 bg-card/60 py-4"
        >
          <motion.div
            className="flex w-max gap-10 font-mono text-xs tracking-[.12em] text-muted-foreground"
            animate={enabled && visible ? { x: [0, "-50%"] } : { x: 0 }}
            transition={{ duration: 38, ease: "linear", repeat: Infinity }}
          >
            {[0, 1].map((copy) => (
              <div
                key={copy}
                className="flex shrink-0 items-center gap-10 pr-10"
              >
                {[
                  "Территории",
                  "Наблюдения",
                  "Динамика",
                  "Контекст",
                  "Открытые данные",
                ].map((word) => (
                  <span key={word} className="flex items-center gap-10">
                    {word}
                    <IconLeaf size={17} className="text-primary/70" />
                  </span>
                ))}
              </div>
            ))}
          </motion.div>
        </div>
        <div
          data-footer-copy
          className="relative z-10 mx-auto flex w-full max-w-5xl flex-1 flex-col items-center justify-center px-5 pt-36 pb-10 text-center"
        >
          <h2 className="max-w-4xl text-[clamp(2.5rem,6.5vw,6rem)] leading-[1.02] tracking-[-.055em]">
            Ваше поле.
            <br />
            Новый взгляд.
          </h2>
          <div className="mt-10 flex flex-wrap justify-center gap-4">
            <MagneticLink href="/app" primary>
              Исследовать поле
            </MagneticLink>
            <MagneticLink href="/app/polygons">Мои исследования</MagneticLink>
          </div>
          <nav
            aria-label="Ссылки в подвале"
            className="mt-8 flex flex-wrap justify-center gap-x-7 gap-y-3 text-sm text-muted-foreground"
          >
            <Link href="/app/models" className="py-2 hover:text-foreground">
              Модели
            </Link>
            <Link
              href="/app/data-quality"
              className="py-2 hover:text-foreground"
            >
              Источники данных
            </Link>
            <a
              href="https://github.com/ArtycoBW/Terralens"
              target="_blank"
              rel="noreferrer"
              className="py-2 hover:text-foreground"
            >
              GitHub ↗
            </a>
          </nav>
        </div>
        <div className="relative z-10 flex items-center justify-between gap-5 px-6 pb-6 text-xs text-muted-foreground sm:px-12">
          <span>© 2026 TerraLens</span>
          <a
            href="#top"
            aria-label="Вернуться наверх"
            className="grid size-12 place-items-center rounded-full border border-border bg-card/70 text-foreground transition-colors hover:bg-secondary"
          >
            <IconArrowUp size={19} />
          </a>
        </div>
      </footer>
    </div>
  );
}
