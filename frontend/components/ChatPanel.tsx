"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";

// Bypass Next dev's rewrite proxy for SSE — it buffers and closes the
// stream. Talk to the backend directly. CORS allows localhost:3001.
const BACKEND_URL =
  process.env.NEXT_PUBLIC_TTT_API_URL || "http://localhost:8765";

type ToolCall = {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  preview?: string;
  truncated?: boolean;
  status: "running" | "done";
};

type Turn = {
  role: "user" | "assistant";
  text: string;
  toolCalls: ToolCall[];
  done?: boolean;
  error?: string;
};

export function ChatPanel({
  projectId,
  reportKey,
  version,
}: {
  projectId: string;
  reportKey: string | null;
  version: number | null;
}) {
  const { mutate } = useSWRConfig();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  const sendTurn = useCallback(
    async (message: string) => {
      // Optimistically render the user turn + a placeholder assistant turn
      setTurns((prev) => [
        ...prev,
        { role: "user", text: message, toolCalls: [] },
        { role: "assistant", text: "", toolCalls: [] },
      ]);
      setStreaming(true);

      console.log("[chat] sendTurn entered", { message });
      try {
        const url = `${BACKEND_URL}/api/projects/${projectId}/chat`;
        console.log("[chat] fetch ->", url);
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ message }),
        });
        console.log("[chat] fetch returned", resp.status, resp.statusText);

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

        // True SSE streaming: read chunks as they arrive and dispatch each
        // complete frame (events separated by a blank line) immediately.
        // Buffer carries any partial trailing frame across chunk boundaries.
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

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          flush(decoder.decode(value, { stream: true }));
        }
        // Drain any final partial frame.
        flush(decoder.decode());
        if (buffer.trim()) {
          const event = parseSseFrame(buffer);
          if (event) setTurns((prev) => applyEvent(prev, event));
        }
        if (touchedFiles) {
          if (reportKey) mutate(reportKey);
          if (version != null) {
            // Invalidate every page-content SWR key for this version so any
            // open editor reloads the post-edit markdown.
            const pagePrefix = `/api/projects/${projectId}/reports/${version}/pages/`;
            mutate((key) => typeof key === "string" && key.startsWith(pagePrefix));
          }
        }
      } catch (err) {
        console.error("[chat] sendTurn error", err);
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
    [projectId, reportKey, mutate],
  );

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    console.log("[chat] onSubmit", { text, streaming });
    if (!text || streaming) return;
    setInput("");
    await sendTurn(text);
  }

  async function onReset() {
    await api.resetChat(projectId);
    setTurns([]);
  }

  return (
    <div className="flex h-[640px] flex-col rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
      <div className="flex items-center justify-between border-b border-neutral-200 px-3 py-2 dark:border-neutral-800">
        <div className="text-sm font-medium">Chat</div>
        <button
          onClick={onReset}
          disabled={streaming || turns.length === 0}
          className="text-xs text-neutral-500 hover:text-neutral-900 disabled:opacity-40 dark:hover:text-neutral-100"
        >
          reset thread
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {turns.length === 0 && (
          <p className="text-xs text-neutral-500">
            Ask anything about this project. The assistant can read the wiki, edit pages, and pull live context from the web.
          </p>
        )}
        {turns.map((turn, i) => (
          <TurnBubble key={i} turn={turn} />
        ))}
      </div>

      <form onSubmit={onSubmit} className="border-t border-neutral-200 p-2 dark:border-neutral-800">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e as unknown as React.FormEvent);
              }
            }}
            placeholder={streaming ? "Working…" : "Ask something…"}
            disabled={streaming}
            rows={2}
            className="flex-1 resize-none rounded border border-neutral-300 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-neutral-400 disabled:opacity-60 dark:border-neutral-700 dark:bg-neutral-900"
          />
          <button
            type="submit"
            disabled={streaming || !input.trim()}
            className="self-end rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {streaming ? "…" : "Send"}
          </button>
        </div>
        <div className="mt-1 text-[10px] text-neutral-500">
          Enter to send, Shift+Enter for newline
        </div>
      </form>
    </div>
  );
}

function TurnBubble({ turn }: { turn: Turn }) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded bg-neutral-900 px-3 py-2 text-sm text-white dark:bg-neutral-200 dark:text-neutral-900">
          {turn.text}
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {turn.toolCalls.map((tc) => (
        <ToolCallCard key={tc.id} call={tc} />
      ))}
      {turn.text && (
        <div className="whitespace-pre-wrap text-sm leading-relaxed">{turn.text}</div>
      )}
      {turn.error && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-xs text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          {turn.error}
        </div>
      )}
    </div>
  );
}

function ToolCallCard({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const summary = summariseToolInput(call.tool, call.input);
  return (
    <div className="rounded border border-neutral-200 bg-neutral-50 text-xs dark:border-neutral-800 dark:bg-neutral-950">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2 py-1 text-left"
      >
        <span className="font-mono text-neutral-500">{open ? "▾" : "▸"}</span>
        <span className="font-medium">{call.tool}</span>
        <span className="truncate text-neutral-500">{summary}</span>
        <span className="ml-auto text-[10px] uppercase tracking-wide text-neutral-500">
          {call.status}
        </span>
      </button>
      {open && (
        <div className="space-y-1 border-t border-neutral-200 px-2 py-1 dark:border-neutral-800">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-neutral-500">input</div>
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[11px]">
              {JSON.stringify(call.input, null, 2)}
            </pre>
          </div>
          {call.preview && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-neutral-500">
                result preview {call.truncated ? "(truncated)" : ""}
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-[11px]">
                {call.preview}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function summariseToolInput(tool: string, input: Record<string, unknown>): string {
  if (tool === "Read" || tool === "Edit" || tool === "Write") {
    return String(input.file_path ?? input.path ?? "");
  }
  if (tool === "Glob") return String(input.pattern ?? "");
  if (tool === "Grep") return String(input.pattern ?? "");
  if (tool === "WebFetch") return String(input.url ?? "");
  if (tool === "WebSearch") return String(input.query ?? "");
  return "";
}

type ParsedEvent = { type: string; payload: unknown };

function parseSseFrame(frame: string): ParsedEvent | null {
  let event: string | null = null;
  const dataLines: string[] = [];
  // Tolerate CRLF or LF line endings.
  for (const raw of frame.split(/\r?\n/)) {
    const line = raw.replace(/\r$/, "");
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!event || dataLines.length === 0) return null;
  try {
    return { type: event, payload: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

function applyEvent(turns: Turn[], event: ParsedEvent): Turn[] {
  if (turns.length === 0) return turns;
  const copy = [...turns];
  const last = { ...copy[copy.length - 1] };
  last.toolCalls = [...last.toolCalls];
  copy[copy.length - 1] = last;

  if (event.type === "token") {
    const text = (event.payload as { text?: string }).text ?? "";
    last.text = (last.text ?? "") + text;
    return copy;
  }
  if (event.type === "tool_call") {
    const p = event.payload as { id: string; tool: string; input: Record<string, unknown> };
    last.toolCalls.push({
      id: p.id,
      tool: p.tool,
      input: p.input ?? {},
      status: "running",
    });
    return copy;
  }
  if (event.type === "tool_result") {
    const p = event.payload as { id: string; preview?: string; truncated?: boolean };
    last.toolCalls = last.toolCalls.map((tc) =>
      tc.id === p.id
        ? { ...tc, status: "done", preview: p.preview, truncated: p.truncated }
        : tc,
    );
    return copy;
  }
  if (event.type === "done") {
    const p = event.payload as { result?: string; subtype?: string };
    if (p.subtype !== "success" && !last.text) {
      last.text = `_(stopped: ${p.subtype ?? "unknown"})_`;
    } else if (!last.text && p.result) {
      // Fallback: if streaming didn't yield tokens, render the final result.
      last.text = p.result;
    }
    last.done = true;
    return copy;
  }
  if (event.type === "error") {
    const p = event.payload as { message?: string };
    last.error = p.message ?? "unknown error";
    last.done = true;
    return copy;
  }
  return copy;
}
