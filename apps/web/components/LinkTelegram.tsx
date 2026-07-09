"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, storeUserId } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { User } from "@/lib/types";

const BOT_USERNAME = "taxiai1bot";

export function LinkTelegram() {
  const router = useRouter();
  const userId = useStoredUserId();
  const [code, setCode] = useState<string | null>(null);
  const [genLoading, setGenLoading] = useState(false);
  const [enterCode, setEnterCode] = useState("");
  const [enterLoading, setEnterLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adopted, setAdopted] = useState(false);

  async function generate() {
    if (!userId) return;
    setGenLoading(true);
    setError(null);
    try {
      const res = await api.post<{ code: string }>("/v1/link/code", { user_id: userId });
      setCode(res.code);
    } catch {
      setError("Не удалось получить код. Попробуйте ещё раз.");
    } finally {
      setGenLoading(false);
    }
  }

  async function adopt(e: React.FormEvent) {
    e.preventDefault();
    const c = enterCode.trim().toUpperCase();
    if (!c) return;
    setEnterLoading(true);
    setError(null);
    try {
      const user = await api.post<User>("/v1/link/redeem-web", { code: c });
      storeUserId(user.id);
      setAdopted(true);
      router.push("/");
      router.refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      setError(msg.includes("404") ? "Код не найден или уже использован." : msg.includes("410") ? "Код истёк — возьмите новый в боте." : "Не удалось войти по коду.");
    } finally {
      setEnterLoading(false);
    }
  }

  return (
    <div className="card p-4 flex flex-col gap-4">
      <h2 className="text-sm font-semibold text-[var(--text-secondary)]">✈️ Telegram-бот</h2>

      {userId && (
        <div className="flex flex-col gap-2">
          <p className="text-sm text-[var(--text-secondary)]">
            Привязать бота к этому аккаунту — уведомления о спросе, план на день и итоги смены в Telegram.
          </p>
          {code ? (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <span className="text-2xl font-semibold tracking-widest tabular">{code}</span>
                <button
                  className="chip"
                  onClick={() => navigator.clipboard?.writeText(code).catch(() => {})}
                >
                  копировать
                </button>
              </div>
              <p className="text-xs text-[var(--text-muted)]">
                Отправьте боту{" "}
                <a
                  href={`https://t.me/${BOT_USERNAME}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[var(--series-1)]"
                >
                  @{BOT_USERNAME}
                </a>{" "}
                команду <code className="text-[var(--text-secondary)]">/link {code}</code>. Код действует 15 минут.
              </p>
            </div>
          ) : (
            <button className="btn-primary self-start" onClick={generate} disabled={genLoading}>
              {genLoading ? "Готовлю код..." : "Подключить Telegram"}
            </button>
          )}
        </div>
      )}

      <div className="flex flex-col gap-2 border-t border-white/10 pt-4">
        <p className="text-sm text-[var(--text-secondary)]">
          Уже настроили профиль в Telegram-боте? Отправьте боту команду <code className="text-[var(--text-muted)]">/link</code>,
          получите код и введите его здесь:
        </p>
        <form onSubmit={adopt} className="flex gap-2">
          <input
            className="input flex-1 uppercase tracking-widest"
            placeholder="КОД"
            value={enterCode}
            maxLength={8}
            onChange={(e) => setEnterCode(e.target.value)}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={enterLoading}>
            {enterLoading ? "..." : "Войти"}
          </button>
        </form>
        {adopted && <p className="text-sm" style={{ color: "var(--status-good)" }}>Аккаунт подключён!</p>}
      </div>

      {error && <p className="text-sm" style={{ color: "var(--status-critical)" }}>{error}</p>}
    </div>
  );
}
