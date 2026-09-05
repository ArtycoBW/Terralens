"use client";
import { useSyncExternalStore } from "react";
const subscribeHydration = () => () => {};
export function useHydrated() {
  return useSyncExternalStore(
    subscribeHydration,
    () => true,
    () => false,
  );
}
function subscribe(callback: () => void) {
  const media = matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change", callback);
  document.addEventListener("visibilitychange", callback);
  return () => {
    media.removeEventListener("change", callback);
    document.removeEventListener("visibilitychange", callback);
  };
}
export function useMotionEnabled() {
  return useSyncExternalStore(
    subscribe,
    () =>
      !matchMedia("(prefers-reduced-motion: reduce)").matches &&
      !document.hidden,
    () => false,
  );
}

export function usePrefersReducedMotion() {
  return useSyncExternalStore(
    subscribe,
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => true,
  );
}
