"use client";

import { useState } from "react";
import useSWR from "swr";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import {
  api,
  swrFetcher,
  type RevisionDetail,
  type RevisionSummary,
} from "@/lib/api";

export function HistoryPanel({
  projectId,
  pagePath,
  currentBody,
  onClose,
}: {
  projectId: string;
  pagePath: string;
  currentBody: string;
  onClose: () => void;
}) {
  const historyKey = `/api/projects/${projectId}/pages/${pagePath}/history`;
  const { data: history, isLoading } = useSWR<RevisionSummary[]>(
    historyKey,
    swrFetcher,
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const revKey = selectedId
    ? `/api/projects/${projectId}/revisions/${selectedId}`
    : null;
  const { data: revision } = useSWR<RevisionDetail>(revKey, swrFetcher);

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="flex h-full w-full max-w-[min(1200px,90vw)] flex-col border-l border-neutral-200 bg-white shadow-xl dark:border-neutral-800 dark:bg-neutral-950">
        <div className="flex items-center justify-between border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
          <div>
            <h2 className="text-base font-semibold">History</h2>
            <p className="text-xs text-neutral-500 font-mono">{pagePath}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-sm text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            aria-label="Close history"
          >
            ✕
          </button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          <aside className="w-72 shrink-0 overflow-y-auto border-r border-neutral-200 dark:border-neutral-800">
            {isLoading && (
              <p className="p-4 text-sm text-neutral-500">Loading…</p>
            )}
            {history && history.length === 0 && (
              <p className="p-4 text-sm text-neutral-500">No revisions yet.</p>
            )}
            <ul>
              {history?.map((r, i) => {
                const ts = new Date(r.created_at);
                const isLatest = i === 0;
                const isSelected = selectedId === r.id;
                return (
                  <li key={r.id}>
                    <button
                      onClick={() => setSelectedId(r.id)}
                      className={`block w-full border-b border-neutral-100 px-4 py-3 text-left text-sm hover:bg-neutral-50 dark:border-neutral-900 dark:hover:bg-neutral-900 ${
                        isSelected
                          ? "bg-neutral-100 dark:bg-neutral-900"
                          : ""
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{r.author}</span>
                        {isLatest && (
                          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                            current
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-neutral-500">
                        {ts.toLocaleString()}
                      </div>
                      {r.message && (
                        <div className="mt-1 truncate text-xs text-neutral-600 dark:text-neutral-400">
                          {r.message}
                        </div>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          <section className="flex-1 overflow-auto bg-neutral-50 dark:bg-neutral-900">
            {!selectedId && (
              <div className="p-6 text-sm text-neutral-500">
                Pick a revision on the left to see its diff against the current page.
              </div>
            )}
            {selectedId && !revision && (
              <div className="p-6 text-sm text-neutral-500">Loading diff…</div>
            )}
            {revision && (
              <div className="text-sm">
                <ReactDiffViewer
                  oldValue={revision.body}
                  newValue={currentBody}
                  splitView={true}
                  compareMethod={DiffMethod.WORDS}
                  leftTitle={`${revision.author} · ${new Date(revision.created_at).toLocaleString()}`}
                  rightTitle="current"
                  useDarkTheme={
                    typeof window !== "undefined" &&
                    window.matchMedia("(prefers-color-scheme: dark)").matches
                  }
                />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

// Suppress unused export warning
void api;
