import Link from "next/link";
import { IconArrowUpRight } from "@tabler/icons-react";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { Colonnade } from "./colonnade";
import { DataFlow } from "./data-flow";
import { TerrainView } from "./terrain-view";
import { LandingMotion } from "./motion";
import { CinematicFooter } from "@/components/ui/motion-footer";
import { LandingNavbar } from "./navbar";
import { Outputs } from "./outputs";
import { HeroStory } from "./hero-story";

export function Landing() {
  return (
    <div
      className="relative isolate overflow-clip bg-background text-foreground"
      id="top"
      data-landing
    >
      <LandingMotion />
      <LandingNavbar />
      <main id="main">
        <HeroStory />

        <Colonnade />

        <section
          id="workflow"
          className="relative z-10 mx-auto flex min-h-svh flex-col justify-center bg-background px-5 py-24 sm:px-10 lg:px-[max(64px,calc((100vw-1312px)/2))]"
        >
          <div data-reveal className="max-w-3xl">
            <h2 className="text-[clamp(2.2rem,4.4vw,4rem)] leading-[1.06] tracking-[-.045em]">
              Несколько источников.
              <br />
              История одного поля.
            </h2>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              TerraLens собирает доступные наблюдения, дополняет пропуски и
              сохраняет происхождение каждого значения.
            </p>
          </div>
          <div className="mt-12 grid gap-12 lg:grid-cols-[1.25fr_1fr] lg:items-center lg:gap-20">
            <DataFlow />
            <ol className="space-y-8" aria-label="Как получить анализ">
              {[
                [
                  "Обозначьте территорию",
                  "Найдите регион, выберите готовый контур или нарисуйте поле на карте.",
                ],
                [
                  "Задайте период",
                  "Выберите даты и источники. Ход сбора сохранится, даже если вы закроете страницу.",
                ],
                [
                  "Изучите результат",
                  "Сопоставьте наблюдения, оценки и погоду. Выгрузите CSV, GeoJSON или полный JSON.",
                ],
              ].map(([title, text]) => (
                <li key={title} data-reveal className="grid gap-3">
                  <h3 className="text-xl font-normal tracking-tight">
                    {title}
                  </h3>
                  <p className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
                    {text}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section
          id="method"
          className="relative z-10 flex min-h-svh items-center border-y border-border/60 bg-background"
        >
          <div className="mx-auto grid w-full max-w-[1440px] items-center gap-8 px-5 py-20 sm:px-10 lg:grid-cols-[.85fr_1.15fr] lg:gap-12 lg:px-16 lg:py-24">
            <div data-reveal>
              <h2 className="text-[clamp(2.2rem,4vw,3.75rem)] leading-[1.06] tracking-[-.045em]">
                За каждым выводом
                <br />
                видны данные.
              </h2>
              <p className="mt-6 max-w-md text-base leading-relaxed text-muted-foreground">
                Понимать изменения можно, когда наблюдения, оценки модели и
                неопределённость различимы.
              </p>
              <Accordion
                type="single"
                collapsible
                defaultValue="observations"
                className="mt-8"
              >
                {[
                  [
                    "observations",
                    "Наблюдения и оценки",
                    "Точки на графике получены со спутника. Восстановленные значения показаны отдельно, а отсутствие данных остаётся видимым.",
                  ],
                  [
                    "signals",
                    "Сигнал требует контекста",
                    "Падение NDVI может совпасть с уборкой, погодой или облаками. Возможные причины остаются гипотезами и требуют проверки на месте.",
                  ],
                  [
                    "provenance",
                    "Результат можно проверить",
                    "Снимки источников, версия контура, модель и контрольные суммы сохраняются вместе с исследованием.",
                  ],
                ].map(([id, title, text]) => (
                  <AccordionItem
                    key={id}
                    value={id}
                    className="border-border/60"
                  >
                    <AccordionTrigger className="py-5 text-base font-normal hover:no-underline">
                      {title}
                    </AccordionTrigger>
                    <AccordionContent className="max-w-md text-sm leading-relaxed text-muted-foreground">
                      {text}
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
              <Link
                href="/app/models"
                className="mt-7 inline-flex items-center gap-3 py-2 text-sm text-primary"
              >
                Посмотреть валидацию
                <IconArrowUpRight size={16} />
              </Link>
            </div>
            <TerrainView />
          </div>
        </section>
        <Outputs />
      </main>
      <CinematicFooter />
    </div>
  );
}
