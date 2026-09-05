"use client";
import { ApiError, label } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { useState, type ReactNode } from "react";
export function ErrorNotice({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <div
      className="grid gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
      role="alert"
    >
      <p>{error.message}</p>
      {error instanceof ApiError && error.requestId && (
        <small className="break-all">Код обращения: {error.requestId}</small>
      )}
      {retry && (
        <Button variant="outline" size="sm" className="w-fit" onClick={retry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
export function Status({ value }: { value: string }) {
  return (
    <Badge
      variant="outline"
      data-state={value}
      className="w-fit shrink-0 border-border bg-secondary text-xs font-normal text-secondary-foreground data-[state=critical]:border-destructive/30 data-[state=critical]:bg-destructive/10 data-[state=critical]:text-destructive data-[state=failed]:border-destructive/30 data-[state=failed]:text-destructive data-[state=stress]:text-warning data-[state=partial]:text-warning data-[state=completed]:text-primary data-[state=succeeded]:text-primary"
    >
      {label[value] || value}
    </Badge>
  );
}
export function Disclosure({
  title,
  children,
  autoOpen = false,
}: {
  title: string;
  children: ReactNode;
  autoOpen?: boolean;
}) {
  const [override, setOverride] = useState<{
    seed: boolean;
    open: boolean;
  } | null>(null);
  const expanded = override?.seed === autoOpen ? override.open : autoOpen;
  return (
    <Accordion
      type="single"
      collapsible
      value={expanded ? "content" : ""}
      onValueChange={(value) =>
        setOverride({ seed: autoOpen, open: value === "content" })
      }
    >
      <AccordionItem value="content" className="border-border/60">
        <AccordionTrigger className="text-left text-sm font-normal text-muted-foreground hover:text-foreground hover:no-underline">
          {title}
        </AccordionTrigger>
        <AccordionContent>{children}</AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
export function JsonDetails({
  value,
  title = "Подробности",
}: {
  value: unknown;
  title?: string;
}) {
  return (
    <Disclosure title={title}>
      <pre className="max-h-96 overflow-auto rounded-md bg-background p-4 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">
        {JSON.stringify(value, null, 2)}
      </pre>
    </Disclosure>
  );
}
