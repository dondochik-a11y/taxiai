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

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="text-xl font-semibold mb-3">AI-ассистент</h1>
      <div className="flex-1 overflow-y-auto flex flex-col gap-2 pr-1">
        {messages.length === 0 && (
          <p className="text-sm text-[var(--text-muted)]">
            Спросите, например: «где сейчас лучше работать?» или «почему сегодня доход ниже?»
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
              m.role === "user" ? "self-end bg-[var(--series-1)] text-white" : "self-start bg-[var(--surface-1)] border border-white/10"
            }`}
          >
            {m.content}
          </div>
        ))}
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
          className="px-4 py-2 rounded-md bg-[var(--series-1)] text-white font-medium disabled:opacity-50"
        >
          Отправить
        </button>
      </div>
    </div>
  );
}
