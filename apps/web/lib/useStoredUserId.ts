"use client";

import { useSyncExternalStore } from "react";
import { getStoredUserId } from "./apiClient";

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener("storage", onStoreChange);
  return () => window.removeEventListener("storage", onStoreChange);
}

/**
 * SSR-safe access to the locally stored user id. localStorage must not be read
 * during the first client render (it would diverge from the server-rendered HTML
 * and fail hydration), so the server snapshot is a distinct "not read yet" value.
 *
 * `undefined` — server render / hydration, `null` — no profile stored.
 */
export function useStoredUserId(): string | null | undefined {
  return useSyncExternalStore(subscribe, getStoredUserId, () => undefined);
}
