"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import {
  swrFetcher,
  type IngestRunDetail,
  type IngestRunSummary,
} from "@/lib/api";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export function IngestHistoryPanel({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const listKey = `/api/projects/${projectId}/ingests`;
  const { data: runs, isLoading } = useSWR<IngestRunSummary[]>(listKey, swrFetcher);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Default to the most recent run on open.
  useEffect(() => {
    if (selectedId == null && runs && runs.length > 0) {
      setSelectedId(runs[0].id);
    }
  }, [runs, selectedId]);

  const detailKey = selectedId ? `/api/ingest/${selectedId}` : null;
  const { data: detail } = useSWR<IngestRunDetail>(detailKey, swrFetcher, {
    refreshInterval: (latest) =>
      !latest || latest.status === "running" || latest.status === "pending" ? 800 : 0,
  });

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        style={{ width: "95vw", maxWidth: "min(1400px, 95vw)" }}
        className="flex flex-col gap-0 p-0"
      >
        <SheetHeader className="border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
          <SheetTitle>Ingest history</SheetTitle>
          <SheetDescription className="text-xs">
            Every ingest run for this project, with its full agent log.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 overflow-hidden">
          <aside className="w-72 shrink-0 overflow-y-auto border-r border-neutral-200 dark:border-neutral-800">
            {isLoading && <p className="p-4 text-sm text-neutral-500">Loading…</p>}
            {runs && runs.length === 0 && (
              <p className="p-4 text-sm text-neutral-500">No ingests yet.</p>
            )}
            <ul>
              {runs?.map((r) => {
                const ts = new Date(r.started_at);
                const dur =
                  r.finished_at && r.started_at
                    ? Math.round(
                        (new Date(r.finished_at).getTime() -
                          new Date(r.started_at).getTime()) /
                          1000,
                      )
                    : null;
                const isSelected = selectedId === r.id;
                return (
                  <li key={r.id}>
                    <button
                      onClick={() => setSelectedId(r.id)}
                      className={`block w-full border-b border-neutral-100 px-4 py-3 text-left text-sm hover:bg-neutral-50 dark:border-neutral-900 dark:hover:bg-neutral-900 ${
                        isSelected ? "bg-neutral-100 dark:bg-neutral-900" : ""
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <StatusPill status={r.status} />
                        <span className="text-xs text-neutral-500">
                          {dur != null ? `${dur}s` : ""}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-neutral-600 dark:text-neutral-400">
                        {ts.toLocaleString()}
                      </div>
                      <div className="mt-0.5 text-[11px] text-neutral-500">
                        {r.log_lines} log lines
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          <section className="flex-1 overflow-hidden bg-neutral-950">
            {!selectedId && (
              <p className="p-6 text-sm text-neutral-400">
                Pick an ingest on the left.
              </p>
            )}
            {selectedId && detail && <LogViewport log={detail.log} error={detail.error} status={detail.status} />}
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function StatusPill({ status }: { status: IngestRunSummary["status"] }) {
  const cls =
    status === "success"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
      : status === "failed"
        ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
        : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${cls}`}>
      {status}
    </span>
  );
}

function LogViewport({
  log,
  error,
  status,
}: {
  log: string;
  error: string | null;
  status: IngestRunDetail["status"];
}) {
  const lines = useMemo(() => log.split("\n").filter((l) => l.length > 0), [log]);
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!scrollRef.current) return;
    if (status === "running" || status === "pending") {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines.length, status]);

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed text-neutral-100">
      {lines.length === 0 ? (
        <div className="text-neutral-600">[--:--:--] · no log captured</div>
      ) : (
        lines.map((raw, i) => <FormattedLine key={i} raw={raw} />)
      )}
      {error && (
        <div className="mt-3 whitespace-pre-wrap break-words text-red-300">[error] {error}</div>
      )}
    </div>
  );
}

function FormattedLine({ raw }: { raw: string }) {
  const m = raw.match(/^(\[[^\]]+\])\s+(.)\s?(.*)$/);
  if (!m) return <div className="whitespace-pre-wrap break-words">{raw}</div>;
  const [, ts, marker, rest] = m;
  const palette: Record<string, string> = {
    "▶": "text-emerald-400 font-semibold",
    "✓": "text-emerald-400",
    "✗": "text-red-400",
    "→": "text-sky-400",
    "←": "text-neutral-300",
    "▒": "text-amber-300",
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
