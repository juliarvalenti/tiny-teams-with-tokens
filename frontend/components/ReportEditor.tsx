"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { api, swrFetcher, type PageKind, type PageResponse } from "@/lib/api";
import { CrepeEditor, type CrepeEditorHandle } from "./CrepeEditor";
import { HistoryPanel } from "./HistoryPanel";
import { KindBadge } from "./KindBadge";
import { Button } from "@/components/ui/button";

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
        className={`rounded border bg-white pb-16 transition-shadow dark:bg-neutral-900 ${editorFrame}`}
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
