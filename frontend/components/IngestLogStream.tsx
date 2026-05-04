"use client";

import { useEffect, useMemo, useRef } from "react";
import useSWR from "swr";
import { swrFetcher } from "@/lib/api";

type IngestRun = {
  id: string;
  status: "pending" | "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  error: string | null;
  log: string;
};

/**
 * Docker-log-style live tail of the agent ingest. Polls the run record while
 * the run is active, auto-scrolls to bottom, color-codes line prefixes.
 */
export function IngestLogStream({ runId }: { runId: string | null }) {
  const key = runId ? `/api/ingest/${runId}` : null;
  const { data } = useSWR<IngestRun>(key, swrFetcher, {
    refreshInterval: (latest) =>
      !latest || latest.status === "running" || latest.status === "pending" ? 800 : 0,
  });

  const lines = useMemo(() => (data?.log || "").split("\n").filter((l) => l.length > 0), [data?.log]);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines.length]);

  if (!runId || !data) {
    return (
      <Shell status="pending">
        <Line>[--:--:--] · waiting for ingest to start…</Line>
      </Shell>
    );
  }

  return (
    <Shell status={data.status}>
      <div
        ref={scrollRef}
        className="h-[60vh] overflow-y-auto px-3 py-2 font-mono text-[12px] leading-relaxed"
        style={{ overflowWrap: "anywhere", wordBreak: "break-word" }}
      >
        {lines.length === 0 ? (
          <Line dim>[--:--:--] · agent starting up…</Line>
        ) : (
          lines.map((raw, i) => <FormattedLine key={i} raw={raw} />)
        )}
        {data.error && (
          <Line className="text-red-300">
            [error] {data.error}
          </Line>
        )}
      </div>
    </Shell>
  );
}

function Shell({
  status,
  children,
}: {
  status: IngestRun["status"];
  children: React.ReactNode;
}) {
  const dot =
    status === "running" || status === "pending"
      ? "bg-emerald-400 animate-pulse"
      : status === "success"
        ? "bg-emerald-500"
        : "bg-red-500";
  return (
    <div className="overflow-hidden rounded-lg border border-neutral-800 bg-neutral-950 text-neutral-100 shadow-lg">
      <div className="flex items-center justify-between border-b border-neutral-800 bg-neutral-900 px-3 py-1.5">
        <div className="flex items-center gap-2">
          <span className={`inline-block h-2 w-2 rounded-full ${dot}`} />
          <span className="text-xs font-medium uppercase tracking-wider text-neutral-400">
            ingest · {status}
          </span>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-neutral-500">live</span>
      </div>
      {children}
    </div>
  );
}

function Line({
  children,
  className = "",
  dim = false,
}: {
  children: React.ReactNode;
  className?: string;
  dim?: boolean;
}) {
  return (
    <div className={`whitespace-pre-wrap break-words ${dim ? "text-neutral-600" : ""} ${className}`}>
      {children}
    </div>
  );
}

/**
 * Color a line based on its prefix marker, which the backend writer uses:
 *   ▶  start            (emerald, bold)
 *   ✓  finish           (emerald)
 *   ✗  tool error       (red)
 *   →  tool call        (sky)
 *   ←  tool result      (neutral)
 *   ▒  agent text       (amber)
 *   ✎  page write       (violet)
 *   ·  status / info    (neutral dim)
 */
function FormattedLine({ raw }: { raw: string }) {
  const m = raw.match(/^(\[[^\]]+\])\s+(.)\s?(.*)$/);
  if (!m) return <Line>{raw}</Line>;
  const [, ts, marker, rest] = m;
  const palette: Record<string, string> = {
    "▶": "text-emerald-400 font-semibold",
    "✓": "text-emerald-400",
    "✗": "text-red-400",
    "→": "text-sky-400",
    "←": "text-neutral-300",
    "~": "text-amber-300",
    "✎": "text-violet-400",
    "·": "text-neutral-500",
  };
  const color = palette[marker] || "text-neutral-400";
  return (
    <div className="whitespace-pre-wrap break-words">
      <span className="text-neutral-600">{ts} </span>
      <span className={color}>
        {marker} {rest}
      </span>
    </div>
  );
}
