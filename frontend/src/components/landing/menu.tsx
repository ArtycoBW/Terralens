"use client";
import Link from "next/link";
import { IconMenu2 } from "@tabler/icons-react";
import { useHydrated } from "./motion-preference";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
  SheetClose,
} from "@/components/ui/sheet";
export function LandingMenu() {
  // Серверная кнопка неактивна до подключения обработчиков событий.
  const hydrated = useHydrated();
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Открыть меню"
          disabled={!hydrated}
          className="rounded-full lg:hidden"
        >
          <IconMenu2 size={22} />
        </Button>
      </SheetTrigger>
      <SheetContent className="bg-background">
        <SheetHeader>
          <SheetTitle>TerraLens</SheetTitle>
          <SheetDescription>Спутниковая история полей</SheetDescription>
        </SheetHeader>
        <nav aria-label="Меню проекта" className="grid gap-2 px-6">
          {[
            ["#features", "Возможности"],
            ["#workflow", "Как это работает"],
            ["#method", "Методология"],
            ["/app", "Исследовать поле"],
          ].map(([href, label]) => (
            <SheetClose asChild key={href}>
              <Link
                href={href}
                className="rounded-md py-4 text-lg hover:text-primary"
              >
                {label}
              </Link>
            </SheetClose>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
