"use client";

import { useEffect, useState } from "react";

/** The (non-standard, Chromium-only) install prompt event. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISS_KEY = "taxiai.installDismissed";

function isIosSafari(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  const isIos = /iphone|ipad|ipod/i.test(ua);
  // Chrome/Firefox/Edge on iOS all carry their own token; exclude them.
  const isSafari = /safari/i.test(ua) && !/crios|fxios|edgios/i.test(ua);
  return isIos && isSafari;
}

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    // iOS Safari exposes standalone off navigator, not the media query.
    (window.navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

/**
 * Registers public/sw.js (production only — a dev SW would serve stale assets
 * across HMR) and surfaces a dismissible "Установить приложение" banner:
 * Chromium via beforeinstallprompt, iOS Safari via a manual Share-sheet hint.
 */
export function ServiceWorkerRegister() {
  const [promptEvent, setPromptEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIosHint, setShowIosHint] = useState(false);
  const [dismissed, setDismissed] = useState(true);

  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/", updateViaCache: "none" })
        .catch(() => {
          // Registration failure (e.g. plain http) just means no offline mode.
        });
    }

    if (localStorage.getItem(DISMISS_KEY) === "1") return;
    if (isStandalone()) return; // already installed
    setDismissed(false);

    const onBeforeInstall = (e: Event) => {
      e.preventDefault(); // stop Chrome's own mini-infobar; we show our banner
      setPromptEvent(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // iOS never fires beforeinstallprompt — offer the Share-sheet hint instead.
    if (isIosSafari()) setShowIosHint(true);

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }

  async function install() {
    if (!promptEvent) return;
    await promptEvent.prompt();
    await promptEvent.userChoice.catch(() => undefined);
    setPromptEvent(null);
    dismiss();
  }

  if (dismissed || (!promptEvent && !showIosHint)) return null;

  return (
    <div
      className="fixed inset-x-3 z-50 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] md:inset-x-auto md:right-4 md:bottom-4 md:max-w-sm rounded-2xl border border-white/10 backdrop-blur px-4 py-3 shadow-lg"
      style={{ background: "var(--overlay)" }}
      role="dialog"
      aria-label="Установить приложение"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-[var(--text-primary)]">Установить приложение</p>
          {promptEvent ? (
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              Быстрый доступ с домашнего экрана и работа без сети.
            </p>
          ) : (
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              Нажмите «Поделиться» → «На экран „Домой“», чтобы установить.
            </p>
          )}
        </div>
        <button
          onClick={dismiss}
          className="text-[var(--text-muted)] shrink-0 -mt-1 -mr-1 p-1"
          aria-label="Скрыть"
        >
          ✕
        </button>
      </div>
      {promptEvent && (
        <button onClick={install} className="btn-cta w-full mt-2.5">
          Установить
        </button>
      )}
    </div>
  );
}
