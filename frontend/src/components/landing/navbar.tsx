import Link from "next/link";
import { IconLeaf, IconArrowUpRight } from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { LandingMenu } from "./menu";

export function LandingNavbar() {
  return (
    <header className="fixed inset-x-4 top-4 z-40 mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 rounded-full border border-foreground/15 bg-background/85 py-2 pr-2 pl-5 text-foreground backdrop-blur-xl sm:inset-x-8 sm:pl-6">
      <Link
        href="/"
        className="flex shrink-0 items-center gap-2 text-lg font-medium tracking-tight"
        aria-label="TerraLens — главная"
      >
        <IconLeaf size={25} stroke={1.6} className="text-primary" />
        TerraLens
      </Link>
      <nav
        aria-label="Навигация по проекту"
        className="hidden items-center gap-6 text-sm lg:flex"
      >
        <a
          href="#features"
          className="py-3 transition-colors hover:text-primary"
        >
          Возможности
        </a>
        <a
          href="#workflow"
          className="py-3 transition-colors hover:text-primary"
        >
          Как это работает
        </a>
        <a href="#method" className="py-3 transition-colors hover:text-primary">
          Исследовать рельеф
        </a>
      </nav>
      <div className="flex items-center gap-2">
        <Button
          asChild
          className="hidden h-11 rounded-full px-5 text-xs sm:inline-flex"
        >
          <Link href="/app">
            Исследовать поле <IconArrowUpRight size={16} />
          </Link>
        </Button>
        <LandingMenu />
      </div>
    </header>
  );
}
