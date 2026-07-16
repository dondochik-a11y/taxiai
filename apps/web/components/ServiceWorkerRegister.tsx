"use client";

import { useEffect } from "react";

/**
 * Registers public/sw.js. Production only — a service worker in dev would
 * serve stale assets across HMR reloads and mask code changes.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .catch(() => {
        // Registration failure (e.g. plain http) just means no offline mode.
      });
  }, []);
  return null;
}
