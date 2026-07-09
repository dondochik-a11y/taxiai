"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/apiClient";
import { useStoredUserId } from "@/lib/useStoredUserId";
import type { ChatMessage } from "@/lib/types";

export default function ChatPage() {
  const userId = useStoredUserId();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!userId) return;
    api.get<ChatMessage[]>(`/v1/chat/${userId}/history`).then(setMessages).catch(() => setMessages([]));
  }, [userId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || !userId) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text, created_at: new Date().toISOString() }]);
    setSending(true);
    try {
      const { reply } = await api.post<{ reply: string }>(`/v1/chat/${userId}`, { message: text });
      setMessages((prev) => [...prev, { role: "assistant", content: reply, created_at: new Date().toISOString() }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Не удалось получить ответ. Попробуйте ещё раз.", created_at: new Date().toISOString() },
      ]);
    } finally {
      setSending(false);
    }
  }

  if (userId === undefined) return null;

  if (userId === null) {
    return (
      <p className="text-sm text-[var(--text-secondary)]">
        Профиль ещё не создан —{" "}
        <Link href="/onboarding" className="text-[var(--series-1)] underline">
          заполните настройки
        </Link>
        .
      </p>
    );
  }

  const suggestions = [
    "Где сейчас лучше работать?",
    "Какой план на сегодня?",
    "Почему доход ниже обычного?",
  ];

  return (
    <div className="flex flex-col h-[calc(100dvh-11.5rem)] md:h-[calc(100dvh-8.5rem)]">
      <h1 className="text-lg md:text-xl font-semibold mb-3">AI-ассистент</h1>
      <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1">
        {messages.length === 0 && (
          <div className="flex flex-col items-start gap-2 mt-2">
            <p className="text-sm text-[var(--text-muted)] mb-1">
              Спросите о работе — например:
            </p>
            {suggestions.map((s) => (
              <button key={s} className="chip" onClick={() => setInput(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] md:max-w-[70%] px-3.5 py-2.5 text-sm leading-relaxed ${
              m.role === "user"
                ? "self-end bg-[var(--series-1)] text-white rounded-2xl rounded-br-md"
                : "self-start bg-[var(--surface-1)] border border-white/10 rounded-2xl rounded-bl-md"
            }`}
          >
            {m.content}
          </div>
        ))}
        {sending && (
          <div className="self-start px-3.5 py-2.5 text-sm text-[var(--text-muted)] bg-[var(--surface-1)] border border-white/10 rounded-2xl rounded-bl-md">
            печатает…
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="flex gap-2 mt-3">
        <input
          className="input flex-1"
          placeholder="Напишите сообщение..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button
          onClick={send}
          disabled={sending}
          aria-label="Отправить"
          className="btn-primary !px-4 shrink-0"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m5 12 14-7-4 14-3.5-5.5L5 12Z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
