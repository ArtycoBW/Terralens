"use client";

import { useId, useState } from "react";
import { format, isValid, parseISO } from "date-fns";
import { ru } from "date-fns/locale";
import { isIsoDate } from "@/lib/dates";
import { IconCalendar } from "@tabler/icons-react";
import { Button } from "./button";
import { Input } from "./input";
import { Label } from "./label";
import { Calendar } from "./calendar";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

export function DateField({
  label,
  value,
  onValueChange,
  min,
  max,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  min?: string;
  max?: string;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const parsed = value ? parseISO(value) : undefined;
  const selected = parsed && isValid(parsed) ? parsed : undefined;
  const lower = min && isIsoDate(min) ? parseISO(min) : undefined;
  const upper = max && isIsoDate(max) ? parseISO(max) : undefined;
  const invalid =
    !!value &&
    (!isIsoDate(value) ||
      !selected ||
      (!!lower && value < min!) ||
      (!!upper && value > max!));
  return (
    <div className="grid min-w-0 gap-2">
      <Label htmlFor={id} className="text-sm font-normal text-muted-foreground">
        {label}
      </Label>
      <div className="relative">
        <Input
          id={id}
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          placeholder="ГГГГ-ММ-ДД"
          maxLength={10}
          aria-invalid={invalid || undefined}
          aria-describedby={invalid ? `${id}-error` : undefined}
          className="pr-12 font-mono text-sm"
        />
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-0 right-0 size-11"
              aria-label={`Календарь: ${label}`}
              disabled={!!(lower && upper && lower > upper)}
            >
              <IconCalendar size={17} />
            </Button>
          </PopoverTrigger>
          <PopoverContent
            className="w-auto p-0"
            align="start"
            collisionPadding={12}
          >
            <Calendar
              mode="single"
              locale={ru}
              selected={selected}
              defaultMonth={selected}
              startMonth={lower}
              endMonth={upper}
              disabled={[
                ...(lower ? [{ before: lower }] : []),
                ...(upper ? [{ after: upper }] : []),
              ]}
              onSelect={(day) => {
                if (day) {
                  onValueChange(format(day, "yyyy-MM-dd"));
                  setOpen(false);
                }
              }}
              autoFocus
            />
          </PopoverContent>
        </Popover>
      </div>
      {invalid && (
        <p id={`${id}-error`} className="text-xs text-destructive">
          Введите допустимую дату в формате ГГГГ-ММ-ДД.
        </p>
      )}
    </div>
  );
}
