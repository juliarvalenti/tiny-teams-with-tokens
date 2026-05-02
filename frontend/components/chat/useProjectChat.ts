"use client";

import { useCallback, useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, swrFetcher } from "@/lib/api";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_TTT_API_URL || "http://localhost:8765";

export type ToolCall = {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  preview?: string;
  truncated?: boolean;
  status: "running" | "done";
};

export type Turn = {
  role: "user" | "assistant";
  text: string;
  toolCalls: ToolCall[];
  done?: boolean;
  error?: string;
};

export type ChatEventPayload =
  | { type: "token"; payload: { text: string } }
  | { type: "tool_call"; payload: { id: string; tool: string; input: Record<string, unknown> } }
  | { type: "tool_result"; payload: { id: string; preview: string; truncated?: boolean } }
  | { type: "session"; payload: { session_id: string } }
  | { type: "done"; payload: { result?: string; cost_usd?: number; num_turns?: number } }
  | { type: "error"; payload: { message: string } };

/**
 * Owns chat state + SSE streaming for a project. Returns turns, streaming
 * flag, and senders. Used by both the collapsed dock and the expanded view.
 */
type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  error: string | null;
  tool_calls: ToolCall[];
  created_at: string;
};

export function useProjectChat(projectId: string) {
  const { mutate } = useSWRConfig();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const messagesKey = `/api/projects/${projectId}/chat/messages`;
  const { data: stored } = useSWR<StoredMessage[]>(messagesKey, swrFetcher);

  // Hydrate the in-memory turns from the persisted transcript exactly once
  // per project. After hydration, in-memory state is the source of truth
  // for the rest of the session; we ignore SWR refreshes to avoid clobbering
  // an in-flight stream.
  useEffect(() => {
    if (hydrated || !stored) return;
    setTurns(
      stored.map((m) => ({
        role: m.role,
        text: m.text,
        toolCalls: m.tool_calls ?? [],
        done: true,
        error: m.error ?? undefined,
      })),
    );
    setHydrated(true);
  }, [hydrated, stored]);

  const reset = useCallback(async () => {
    await api.resetChat(projectId);
    setTurns([]);
    mutate(messagesKey);
  }, [projectId, mutate, messagesKey]);

  const sendTurn = useCallback(
    async (message: string) => {
      setTurns((prev) => [
        ...prev,
        { role: "user", text: message, toolCalls: [] },
        { role: "assistant", text: "", toolCalls: [] },
      ]);
      setStreaming(true);

      try {
        const url = `${BACKEND_URL}/api/projects/${projectId}/chat`;
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ message }),
        });
        if (!resp.ok) {
          setTurns((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === "assistant") {
              last.error = `${resp.status} ${resp.statusText}`;
              last.done = true;
            }
            return copy;
          });
          return;
        }
        if (!resp.body) throw new Error("response has no readable body");

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let touchedFiles = false;

        const flush = (chunk: string) => {
          buffer += chunk;
          while (true) {
            const m = buffer.match(/\r?\n\r?\n/);
            if (!m || m.index === undefined) break;
            const frame = buffer.slice(0, m.index);
            buffer = buffer.slice(m.index + m[0].length);
            if (!frame.trim()) continue;
            const event = parseSseFrame(frame);
            if (!event) continue;
            setTurns((prev) => applyEvent(prev, event));
            if (event.type === "tool_call") {
              const p = event.payload as {
                tool?: string;
                input?: { file_path?: string; path?: string };
              };
              if (p.tool === "Edit" || p.tool === "Write") touchedFiles = true;
            }
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          flush(decoder.decode(value, { stream: true }));
        }
        flush(decoder.decode());
        if (buffer.trim()) {
          const event = parseSseFrame(buffer);
          if (event) setTurns((prev) => applyEvent(prev, event));
        }

        if (touchedFiles) {
          // Invalidate any open page editor for this project.
          mutate((key) =>
            typeof key === "string" && key.startsWith(`/api/projects/${projectId}/`),
          );
        }
        // Sync the persisted transcript so a refresh sees the same turns.
        mutate(messagesKey);
      } catch (err) {
        setTurns((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === "assistant") {
            last.error = (err as Error).message;
            last.done = true;
          }
          return copy;
        });
      } finally {
        setStreaming(false);
      }
    },
    [projectId, mutate],
  );

  return { turns, streaming, sendTurn, reset };
}

/* ---------- SSE frame parsing + reducer (same shape as the old ChatPanel) ---------- */

function parseSseFrame(frame: string): ChatEventPayload | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const raw of frame.split(/\r?\n/)) {
    const line = raw.replace(/\r$/, "");
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;
  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  return { type: event as ChatEventPayload["type"], payload } as ChatEventPayload;
}

function applyEvent(prev: Turn[], event: ChatEventPayload): Turn[] {
  const last = prev[prev.length - 1];
  if (!last || last.role !== "assistant") return prev;

  let next: Turn;
  switch (event.type) {
    case "token":
      next = { ...last, text: last.text + event.payload.text };
      break;
    case "tool_call":
      next = {
        ...last,
        toolCalls: [
          ...last.toolCalls,
          {
            id: event.payload.id,
            tool: event.payload.tool,
            input: event.payload.input,
            status: "running",
          },
        ],
      };
      break;
    case "tool_result":
      next = {
        ...last,
        toolCalls: last.toolCalls.map((tc) =>
          tc.id === event.payload.id
            ? {
                ...tc,
                preview: event.payload.preview,
                truncated: event.payload.truncated,
                status: "done",
              }
            : tc,
        ),
      };
      break;
    case "done":
      next = {
        ...last,
        done: true,
        text:
          event.payload.result && !last.text.trim()
            ? event.payload.result
            : last.text,
      };
      break;
    case "error":
      next = { ...last, error: event.payload.message, done: true };
      break;
    default:
      return prev;
  }
  return [...prev.slice(0, -1), next];
}
