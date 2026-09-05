"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconMap,
  IconLayersIntersect,
  IconChartLine,
  IconShieldCheck,
  IconBrain,
  IconFlask,
  IconArrowUpRight,
  IconLeaf,
  IconLogout,
} from "@tabler/icons-react";
import { Button } from "@/components/ui/button";
import { ConfirmAction } from "@/components/ui/confirm-action";
import {
  SidebarProvider,
  DesktopSidebar,
  MobileSidebar,
  SidebarLink,
  SidebarToggle,
  useSidebar,
} from "@/components/ui/sidebar";
import { useWorkspace } from "./provider";
const nav = [
  ["/app", "Карта", IconMap],
  ["/app/polygons", "Мои поля", IconLayersIntersect],
  ["/app/compare", "Сравнение", IconChartLine],
  ["/app/data-quality", "Качество данных", IconShieldCheck],
  ["/app/models", "Модели", IconBrain],
  ["/app/benchmark", "Бенчмарк", IconFlask],
] as const;
function ExitButton({ compact = false }: { compact?: boolean }) {
  const { reset } = useWorkspace();
  const { open } = useSidebar();
  return (
    <ConfirmAction
      title="Завершить сессию?"
      description="Доступ к сохранённым полям этого пространства будет потерян. После завершения откроется новое гостевое пространство."
      action="Завершить сессию"
      onConfirm={reset}
    >
      <Button
        variant="ghost"
        aria-label="Завершить сессию"
        className="h-12 justify-start gap-3 overflow-hidden rounded-xl px-3 text-muted-foreground"
      >
        <IconLogout className="size-5! shrink-0" />
        <span
          className={compact || !open ? "sr-only" : "whitespace-nowrap text-xs"}
        >
          Завершить сессию
        </span>
      </Button>
    </ConfirmAction>
  );
}
function Navigation({ mobile = false }: { mobile?: boolean }) {
  const path = usePathname();
  return (
    <nav aria-label="Основная навигация" className="grid gap-1.5">
      {nav.map(([href, title, Icon]) => (
        <SidebarLink
          key={href}
          href={href}
          label={title}
          icon={<Icon size={21} stroke={1.6} />}
          active={
            href === "/app"
              ? path === href
              : path.startsWith(href) ||
                (href === "/app/polygons" && path.startsWith("/app/analyses/"))
          }
          mobile={mobile}
        />
      ))}
    </nav>
  );
}
function WorkspaceChrome({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { open } = useSidebar();
  const { session } = useWorkspace();
  const current =
    (path.startsWith("/app/analyses/")
      ? "Анализ"
      : nav.find(([href]) => href !== "/app" && path.startsWith(href))?.[1]) ||
    "Карта";
  const brand = (
    <Link
      href="/"
      aria-label="TerraLens"
      className="flex h-12 items-center gap-3 px-3 text-lg font-medium tracking-tight"
    >
      <IconLeaf size={25} className="shrink-0 text-primary" />
      <span className={open ? "whitespace-nowrap" : "sr-only"}>TerraLens</span>
    </Link>
  );
  return (
    <div className="min-h-dvh md:flex">
      <DesktopSidebar>
        {brand}
        <div className="mt-8">
          <Navigation />
        </div>
        <div className="mt-auto grid gap-2 pt-8">
          {open && (
            <p className="px-3 pb-3 text-xs leading-relaxed text-muted-foreground">
              Гостевая сессия
              <br />
              <span className="text-foreground/80">
                до {new Date(session.expires_at).toLocaleDateString("ru-RU")}
              </span>
            </p>
          )}
          <ExitButton />
          <div className="mt-2 border-t border-border/60 pt-2">
            <SidebarToggle />
          </div>
        </div>
      </DesktopSidebar>
      <div className="min-w-0 flex-1">
        <header className="flex h-16 items-center gap-3 border-b border-border/50 px-4 text-xs text-muted-foreground sm:px-7 lg:px-8">
          <div className="-ml-2 md:hidden">
            <MobileSidebar>
              <Navigation mobile />
              <div className="mt-auto border-t border-border pt-4">
                <Link href="/" className="flex items-center gap-2 p-3 text-sm">
                  <IconLeaf size={20} />
                  TerraLens <IconArrowUpRight size={15} />
                </Link>
              </div>
            </MobileSidebar>
          </div>
          <span className="hidden sm:inline">TerraLens</span>
          <span aria-hidden="true" className="hidden text-border sm:inline">
            /
          </span>
          <span className="text-sm text-foreground">{current}</span>
          <Link
            href="/app/data-quality"
            className="ml-auto hidden items-center gap-2 sm:flex"
          >
            Источники данных <IconArrowUpRight size={14} />
          </Link>
          <div className="ml-auto md:hidden">
            <ExitButton compact />
          </div>
        </header>
        <main id="main">{children}</main>
      </div>
    </div>
  );
}
export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <WorkspaceChrome>{children}</WorkspaceChrome>
    </SidebarProvider>
  );
}
