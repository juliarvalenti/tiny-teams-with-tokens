"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import ReactDiffViewer, { DiffMethod } from "react-diff-viewer-continued";
import {
  swrFetcher,
  type RevisionDetail,
  type RevisionSummary,
} from "@/lib/api";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";

export function HistoryPanel({
  projectId,
  pagePath,
  onClose,
}: {
  projectId: string;
  pagePath: string;
  onClose: () => void;
}) {
  const historyKey = `/api/projects/${projectId}/pages/${pagePath}/history`;
  const { data: history, isLoading } = useSWR<RevisionSummary[]>(
    historyKey,
    swrFetcher,
  );

  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  // Default to the most recent revision so the panel isn't blank on open.
  useEffect(() => {
    if (selectedIndex == null && history && history.length > 0) {
      setSelectedIndex(0);
    }
  }, [history, selectedIndex]);

  const selected = selectedIndex != null ? history?.[selectedIndex] : null;
  // The "previous" revision in the timeline is the *next* item in the list,
  // since the list is ordered newest-first.
  const previous =
    selectedIndex != null && history ? history[selectedIndex + 1] : null;

  const newKey = selected
    ? `/api/projects/${projectId}/revisions/${selected.id}`
    : null;
  const oldKey = previous
    ? `/api/projects/${projectId}/revisions/${previous.id}`
    : null;

  const { data: newRev } = useSWR<RevisionDetail>(newKey, swrFetcher);
  const { data: oldRev } = useSWR<RevisionDetail>(oldKey, swrFetcher);

  const oldBody = previous ? oldRev?.body ?? "" : "";
  const newBody = newRev?.body ?? "";
  const diffReady = !!newRev && (!previous || !!oldRev);

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="flex w-full max-w-[min(1600px,95vw)] flex-col gap-0 p-0 sm:max-w-[min(1600px,95vw)]"
      >
        <SheetHeader className="border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
          <SheetTitle>History</SheetTitle>
          <SheetDescription className="font-mono text-xs">
            {pagePath}
          </SheetDescription>
        </SheetHeader>

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
                const isSelected = selectedIndex === i;
                return (
                  <li key={r.id}>
                    <button
                      onClick={() => setSelectedIndex(i)}
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
            {!selected && (
              <div className="p-6 text-sm text-neutral-500">
                Pick a revision on the left.
              </div>
            )}
            {selected && !diffReady && (
              <div className="p-6 text-sm text-neutral-500">Loading diff…</div>
            )}
            {selected && diffReady && (
              <div className="diff-host">
                <div className="border-b border-neutral-200 px-5 py-2 text-xs text-neutral-600 dark:border-neutral-800 dark:text-neutral-400">
                  {previous ? (
                    <>
                      Showing what changed in this revision (
                      <span className="font-medium">{previous.author}</span>{" "}
                      → <span className="font-medium">{selected.author}</span>)
                    </>
                  ) : (
                    <>
                      First revision — comparing against an empty page.
                    </>
                  )}
                </div>
                <ReactDiffViewer
                  oldValue={oldBody}
                  newValue={newBody}
                  splitView={true}
                  compareMethod={DiffMethod.WORDS}
                  leftTitle={
                    previous
                      ? `${previous.author} · ${new Date(previous.created_at).toLocaleString()}`
                      : "(empty)"
                  }
                  rightTitle={`${selected.author} · ${new Date(selected.created_at).toLocaleString()}`}
                  useDarkTheme={
                    typeof window !== "undefined" &&
                    window.matchMedia("(prefers-color-scheme: dark)").matches
                  }
                />
              </div>
            )}
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
