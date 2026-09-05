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
  const { open, setHover } = useSidebar();
  const reduce = useReducedMotion();
  return (
    <motion.aside
      data-sidebar
      data-open={open}
      className="group/sidebar sticky top-0 hidden h-dvh shrink-0 flex-col overflow-hidden border-r border-border/60 bg-card/45 px-3 py-5 md:flex"
      animate={{ width: open ? 248 : 76 }}
      initial={false}
      transition={{ duration: reduce ? 0 : 0.25, ease: [0.22, 1, 0.36, 1] }}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") setHover(true);
      }}
      onPointerLeave={(event) => {
        if (!event.currentTarget.contains(document.activeElement))
          setHover(false);
      }}
      onFocusCapture={() => setHover(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setHover(false);
      }}
    >
      {children}
    </motion.aside>
  );
}
export function SidebarToggle() {
  const { pinned, setPinned } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-11 rounded-xl text-muted-foreground"
      aria-label={pinned ? "Свернуть навигацию" : "Закрепить навигацию"}
      aria-pressed={pinned}
      onClick={() => setPinned(!pinned)}
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
  const { open, setMobile } = useSidebar();
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
      <span
        className={cn(
          "whitespace-nowrap transition-opacity duration-150",
          open || mobile ? "opacity-100" : "sr-only",
        )}
      >
        {label}
      </span>
    </Link>
  );
}
