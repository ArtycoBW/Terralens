"use client";

import type { ComponentProps, ReactNode } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

// Radix reserves the empty value for placeholders; filters need an explicit “all” option.
const ALL = "__terralens_all__";
export function SelectControl({
  value,
  onValueChange,
  children,
  ...props
}: Omit<ComponentProps<typeof SelectTrigger>, "value" | "onChange"> & {
  value: string | number;
  onValueChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <Select
      value={String(value) || ALL}
      onValueChange={(next) => onValueChange(next === ALL ? "" : next)}
      disabled={props.disabled}
    >
      <SelectTrigger {...props}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent
        position="popper"
        align="start"
        sideOffset={5}
        collisionPadding={12}
      >
        {children}
      </SelectContent>
    </Select>
  );
}
export function SelectOption({
  value,
  ...props
}: Omit<ComponentProps<typeof SelectItem>, "value"> & {
  value: string | number;
}) {
  return <SelectItem {...props} value={String(value) || ALL} />;
}
