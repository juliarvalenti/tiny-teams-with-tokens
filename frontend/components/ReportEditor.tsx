"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { api, swrFetcher, type PageKind, type PageResponse } from "@/lib/api";
import { CrepeEditor, type CrepeEditorHandle } from "./CrepeEditor";

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
      ? "This page is auto-rewritten on each reingest — your edits will be overwritten next time."
      : null;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">{pageTitle}</h2>
          <span
            className={
              pageKind === "stable"
                ? "rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
                : "rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
            }
          >
            {pageKind}
          </span>
        </div>
        <div className="flex gap-2">
          {isEditing ? (
            <>
              <button
                onClick={onSave}
                disabled={saving || locked}
                className="rounded bg-neutral-900 px-3 py-1 text-xs text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                onClick={onCancel}
                disabled={saving}
                className="rounded px-3 py-1 text-xs text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              onClick={() => setIsEditing(true)}
              disabled={locked}
              title={locked ? "locked while ingest is running" : "Edit page"}
              className="rounded border border-neutral-300 px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            >
              Edit
            </button>
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

      <div className="rounded border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
        <CrepeEditor
          ref={editorRef}
          key={`${pagePath}-${data.git_commit}-${editorEpoch}`}
          initialMarkdown={data.body}
          readonly={!isEditing}
        />
      </div>
    </div>
  );
}
