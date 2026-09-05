"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import {
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconMenu2,
} from "@tabler/icons-react";
import { Button } from "./button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "./sheet";
import { cn } from "@/lib/utils";

type SidebarState = {
  open: boolean;
  setHover: (value: boolean) => void;
  pinned: boolean;
  setPinned: (value: boolean) => void;
  mobile: boolean;
  setMobile: (value: boolean) => void;
};
const Context = createContext<SidebarState | null>(null);
export function useSidebar() {
  const context = useContext(Context);
  if (!context) throw new Error("Sidebar components need SidebarProvider");
  return context;
}
/** Adapted from the supplied 21st/Aceternity sidebar; Sheet supplies mobile focus management. */
export function SidebarProvider({ children }: { children: ReactNode }) {
  const [hover, setHover] = useState(false),
    [pinned, setPinned] = useState(false),
    [mobile, setMobile] = useState(false);
  return (
    <Context.Provider
      value={{
        open: hover || pinned,
        setHover,
        pinned,
        setPinned,
        mobile,
        setMobile,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function DesktopSidebar({ children }: { children: ReactNode }) {
  const { open, pinned, setHover, setPinned } = useSidebar();
  const reduce = useReducedMotion();
  return (
    // Keep the workspace width constant: resizing WebGL/canvas on each animation
    // frame clears their backing buffers and makes charts and the map flash.
    <div
      data-pinned={pinned}
      className="sticky top-0 z-30 hidden h-dvh w-[76px] shrink-0 self-start data-[pinned=true]:w-[248px] md:block"
    >
      <motion.aside
        data-sidebar
        data-open={open}
        className="group/sidebar absolute inset-y-0 left-0 overflow-hidden border-r border-border/60 bg-background transition-shadow duration-600 data-[open=true]:shadow-[12px_0_32px_-12px_rgba(0,0,0,0.35)]"
        animate={{ width: open ? 248 : 76 }}
        initial={false}
        transition={{ duration: reduce ? 0 : 0.6, ease: [0.4, 0, 0.2, 1] }}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") setHover(true);
        }}
        onPointerLeave={(event) => {
          if (!event.currentTarget.contains(document.activeElement))
            setHover(false);
        }}
        onFocusCapture={() => setHover(true)}
        onBlurCapture={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget))
            setHover(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape" && !event.defaultPrevented) {
            setPinned(false);
            setHover(false);
          }
        }}
      >
        <div className="flex h-full w-full flex-col px-3 py-5">{children}</div>
      </motion.aside>
    </div>
  );
}
export function SidebarInset({ children }: { children: ReactNode }) {
  const { pinned } = useSidebar();
  const reduce = useReducedMotion();
  return (
    <motion.div
      // Reserve space once when pinned. FLIP animates only the position, so
      // canvases resize once instead of being cleared throughout the transition.
      layout="position"
      layoutDependency={pinned}
      transition={{
        layout: { duration: reduce ? 0 : 0.6, ease: [0.4, 0, 0.2, 1] },
      }}
      className="min-w-0 flex-1"
    >
      {children}
    </motion.div>
  );
}
export function SidebarLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const { open } = useSidebar();
  return (
    <span
      aria-hidden={!open}
      className={cn(
        "whitespace-nowrap transition-[opacity,transform] duration-300 motion-reduce:transition-none",
        open ? "translate-x-0 opacity-100" : "-translate-x-1 opacity-0",
        className,
      )}
    >
      {children}
    </span>
  );
}
export function SidebarToggle() {
  const { open, pinned, setPinned, setHover } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-11 rounded-xl text-muted-foreground"
      aria-label={pinned ? "Свернуть навигацию" : "Закрепить навигацию"}
      aria-pressed={pinned}
      aria-expanded={open}
      onClick={() => {
        setPinned(!pinned);
        if (pinned) setHover(false);
      }}
    >
      {pinned ? (
        <IconLayoutSidebarLeftCollapse size={20} />
      ) : (
        <IconLayoutSidebarLeftExpand size={20} />
      )}
    </Button>
  );
}
export function MobileSidebar({ children }: { children: ReactNode }) {
  const { mobile, setMobile } = useSidebar();
  return (
    <Sheet open={mobile} onOpenChange={setMobile}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Открыть навигацию">
          <IconMenu2 size={22} />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="left"
        className="w-80 max-w-[90vw] rounded-r-2xl bg-background"
      >
        <SheetHeader>
          <SheetTitle>TerraLens</SheetTitle>
          <SheetDescription>Рабочее пространство</SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col px-4 pb-5">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
export function SidebarLink({
  href,
  label,
  icon,
  active,
  mobile = false,
}: {
  href: string;
  label: string;
  icon: ReactNode;
  active?: boolean;
  mobile?: boolean;
}) {
  const { setMobile } = useSidebar();
  return (
    <Link
      href={href}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      onClick={() => setMobile(false)}
      className={cn(
        "group flex min-h-12 items-center gap-3 overflow-hidden rounded-xl px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
        active &&
          "bg-primary/10 text-primary ring-1 ring-inset ring-primary/10",
      )}
    >
      <span className="grid size-5 shrink-0 place-items-center">{icon}</span>
      {mobile ? <span>{label}</span> : <SidebarLabel>{label}</SidebarLabel>}
    </Link>
  );
}
