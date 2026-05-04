"use client";

import { ChevronDown } from "lucide-react";
import { useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, swrFetcher, type PageKind, type PageResponse } from "@/lib/api";
import { CrepeEditor, type CrepeEditorHandle } from "./CrepeEditor";
import { HistoryPanel } from "./HistoryPanel";
import { KindBadge } from "./KindBadge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

export function ReportEditor({
  projectId,
  version,
  pagePath,
  pageTitle,
  pageKind,
  locked,
}: {
  projectId: string;
  version: number;
  pagePath: string;
  pageTitle: string;
  pageKind: PageKind;
  locked: boolean;
}) {
  const reportKey = `/api/projects/${projectId}/reports/${version}/pages/${pagePath}`;
  const { data, error, isLoading, mutate } = useSWR<PageResponse>(reportKey, swrFetcher);

  const editorRef = useRef<CrepeEditorHandle>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [showHistory, setShowHistory] = useState(false);

  if (error) {
    return (
      <div className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
        {(error as Error).message}
      </div>
    );
  }
  if (isLoading || !data) {
    return <p className="text-sm text-neutral-500">Loading page…</p>;
  }

  async function onSave() {
    if (!editorRef.current || !data) return;
    const md = editorRef.current.getMarkdown();
    setSaving(true);
    setSaveError(null);
    try {
      await api.putPage(projectId, version, pagePath, md);
      setIsEditing(false);
      setEditorEpoch((n) => n + 1);
      await mutate();
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function onCancel() {
    setIsEditing(false);
    setEditorEpoch((n) => n + 1);
    setSaveError(null);
  }

  const dynamicWarning =
    pageKind === "dynamic" && isEditing
      ? "Heads up: the agent rewrites this page on every reingest. Your edits go in as context for the next rewrite, but they may not survive."
      : null;

  // Editor frame swaps to an amber outline while editing so the user can see
  // they're in a mutating context — prevents accidental "I thought I was just
  // reading" edits.
  const editorFrame = isEditing
    ? "ring-2 ring-amber-400 ring-offset-2 ring-offset-neutral-50 dark:ring-offset-neutral-950 border-amber-300 dark:border-amber-700"
    : "border-neutral-200 dark:border-neutral-800";

  return (
    <div className="relative">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">{pageTitle}</h2>
          <KindBadge kind={pageKind} />
        </div>
        <div className="flex gap-2">
          <KindToggleButton
            projectId={projectId}
            version={version}
            pagePath={pagePath}
            currentKind={pageKind}
            disabled={locked}
            onChanged={() => mutate()}
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowHistory(true)}
            title="View revision history"
          >
            History
          </Button>
          {!isEditing && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setIsEditing(true)}
              disabled={locked}
              title={locked ? "locked while ingest is running" : "Edit page"}
            >
              Edit
            </Button>
          )}
        </div>
      </div>

      {dynamicWarning && (
        <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300">
          {dynamicWarning}
        </div>
      )}
      {saveError && (
        <div className="mb-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          {saveError}
        </div>
      )}

      <div
        className={`rounded border bg-white mb-16 transition-shadow dark:bg-neutral-900 ${editorFrame}`}
      >
        <CrepeEditor
          ref={editorRef}
          key={`${pagePath}-${data.revision_id ?? "none"}-${editorEpoch}`}
          initialMarkdown={data.body}
          readonly={!isEditing}
        />
      </div>

      {isEditing && (
        <div className="sticky bottom-6 -mx-2 mt-4 flex items-center justify-between gap-4 rounded-lg border border-amber-300 bg-amber-50/95 px-5 py-3 shadow-lg backdrop-blur dark:border-amber-900/60 dark:bg-amber-950/85">
          <span className="text-sm text-amber-900 dark:text-amber-200">
            Editing <span className="font-mono">{pagePath}</span> · changes are not saved until you click Save.
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCancel} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={saving || locked}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}

      {showHistory && (
        <HistoryPanel
          projectId={projectId}
          pagePath={pagePath}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );
}

function KindToggleButton({
  projectId,
  version,
  pagePath,
  currentKind,
  disabled,
  onChanged,
}: {
  projectId: string;
  version: number;
  pagePath: string;
  currentKind: PageKind;
  disabled: boolean;
  onChanged: () => void;
}) {
  const { mutate: globalMutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // "report" is system-managed via path; only stable/dynamic/hidden are
  // user-flippable kinds.
  const opts: { key: PageKind; label: string }[] = [
    { key: "stable", label: "Stable" },
    { key: "dynamic", label: "Dynamic" },
    { key: "hidden", label: "Hidden" },
  ];

  async function set(kind: PageKind) {
    if (kind === currentKind) {
      setOpen(false);
      return;
    }
    setBusy(true);
    try {
      await api.patchFrontmatter(projectId, version, pagePath, { kind });
      onChanged();
      // Invalidate the page tree so the sidebar badge updates immediately.
      globalMutate(`/api/projects/${projectId}/reports/${version}`);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  if (disabled) return null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          size="sm"
          variant="outline"
          title="Change page kind"
          className="capitalize"
        >
          {currentKind}
          <ChevronDown
            className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`}
          />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-2">
        <p className="mb-2 px-1 text-[11px] uppercase tracking-wider text-neutral-500">
          Change kind
        </p>
        <div className="grid gap-1">
          {opts.map((o) => (
            <button
              key={o.key}
              onClick={() => set(o.key)}
              disabled={busy}
              className={`flex items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-neutral-100 disabled:opacity-50 dark:hover:bg-neutral-800 ${
                o.key === currentKind ? "bg-neutral-100 dark:bg-neutral-800" : ""
              }`}
            >
              <span className="flex items-center gap-2">
                <KindBadge kind={o.key} iconOnly />
                <span>{o.label}</span>
              </span>
              {o.key === currentKind && (
                <span className="text-[10px] uppercase tracking-wider text-neutral-500">
                  current
                </span>
              )}
            </button>
          ))}
        </div>
        {currentKind === "report" && (
          <p className="mt-2 border-t border-neutral-200 px-1 pt-2 text-[11px] text-neutral-500 dark:border-neutral-800">
            Report pages are system-managed surfaces. Switching kind here will
            move it into the wiki tree.
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
