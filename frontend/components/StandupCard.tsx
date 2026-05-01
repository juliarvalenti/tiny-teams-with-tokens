"use client";

import { useMemo, useRef, useState } from "react";
import useSWR from "swr";
import {
  api,
  swrFetcher,
  type PageResponse,
} from "@/lib/api";
import { CrepeEditor, type CrepeEditorHandle } from "./CrepeEditor";
import { KindBadge } from "./KindBadge";
import { Button } from "@/components/ui/button";

type Section = {
  title: string;
  body: string;
};

const STANDUP_SECTIONS = [
  { key: "what", title: "What is this", layout: "half" as const },
  { key: "headline", title: "Headline", layout: "half" as const },
  { key: "asks", title: "Asks / Blockers", layout: "full" as const },
  { key: "next", title: "Up next", layout: "full" as const },
] as const;

export function StandupCard({
  projectId,
  version,
  locked,
}: {
  projectId: string;
  version: number;
  locked: boolean;
}) {
  const pageKey = `/api/projects/${projectId}/reports/${version}/pages/standup.md`;
  const { data, error, isLoading, mutate } = useSWR<PageResponse>(
    pageKey,
    swrFetcher,
    { shouldRetryOnError: false },
  );

  const sections = useMemo(
    () => parseSections(data?.body ?? ""),
    [data?.body],
  );

  const notGenerated =
    error && (error as Error).message.startsWith("404");

  if (isLoading) {
    return <Shell>Loading standup…</Shell>;
  }
  if (notGenerated) {
    return (
      <Shell>
        <p className="text-sm text-neutral-500">
          No standup yet — run a reingest to generate one.
        </p>
      </Shell>
    );
  }
  if (error) {
    return (
      <Shell>
        <p className="text-sm text-red-700 dark:text-red-300">
          {(error as Error).message}
        </p>
      </Shell>
    );
  }
  if (!data) return null;

  return (
    <Shell>
      <div className="grid gap-3 md:grid-cols-2">
        {STANDUP_SECTIONS.map(({ key, title, layout }) => {
          const section = sections.find((s) => normalize(s.title) === normalize(title));
          return (
            <div key={key} className={layout === "full" ? "md:col-span-2" : ""}>
              <StandupSection
                title={title}
                body={section?.body ?? ""}
                revisionId={data.revision_id ?? "none"}
                locked={locked}
                onSave={async (newBody) => {
                  const next = STANDUP_SECTIONS.map((spec) => {
                    if (spec.title === title) return { title, body: newBody };
                    const existing = sections.find(
                      (s) => normalize(s.title) === normalize(spec.title),
                    );
                    return { title: spec.title, body: existing?.body ?? "" };
                  });
                  const nextMd = serializeSections(next);
                  await api.putPage(projectId, version, "standup.md", nextMd);
                  await mutate();
                }}
              />
            </div>
          );
        })}
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <section aria-label="Project standup">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">The Standup</h2>
          <KindBadge kind="report" />
        </div>
      </div>
      {children}
    </section>
  );
}

function StandupSection({
  title,
  body,
  revisionId,
  locked,
  onSave,
}: {
  title: string;
  body: string;
  revisionId: string;
  locked: boolean;
  onSave: (newBody: string) => Promise<void>;
}) {
  const editorRef = useRef<CrepeEditorHandle>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [editorEpoch, setEditorEpoch] = useState(0);

  return (
    <div
      className={`group rounded-lg border bg-white transition-shadow dark:bg-neutral-900 ${
        editing
          ? "border-amber-300 ring-2 ring-amber-200 dark:border-amber-700 dark:ring-amber-900/40"
          : "border-neutral-200 hover:shadow dark:border-neutral-800"
      }`}
    >
      <div className="flex items-baseline justify-between px-3 pb-1 pt-2.5">
        <h3 className="font-serif text-sm font-semibold tracking-tight">
          {title}
        </h3>
        {!editing && !locked && (
          <button
            onClick={() => setEditing(true)}
            className="text-[10px] uppercase tracking-wide text-neutral-400 opacity-0 hover:text-neutral-700 group-hover:opacity-100 dark:text-neutral-500 dark:hover:text-neutral-200"
          >
            edit
          </button>
        )}
      </div>

      <div className="standup-section-body px-1 pb-1">
        <CrepeEditor
          ref={editorRef}
          key={`${title}-${revisionId}-${editorEpoch}`}
          initialMarkdown={body || "_(empty)_"}
          readonly={!editing}
        />
      </div>

      {err && (
        <p className="px-3 pb-2 text-xs text-red-600 dark:text-red-400">{err}</p>
      )}

      {editing && (
        <div className="flex justify-end gap-2 border-t border-amber-200 bg-amber-50/60 px-3 py-2 dark:border-amber-900/40 dark:bg-amber-950/30">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setEditing(false);
              setEditorEpoch((n) => n + 1);
              setErr(null);
            }}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              if (!editorRef.current) return;
              const md = editorRef.current.getMarkdown();
              setSaving(true);
              setErr(null);
              try {
                await onSave(md);
                setEditing(false);
                setEditorEpoch((n) => n + 1);
              } catch (e) {
                setErr((e as Error).message);
              } finally {
                setSaving(false);
              }
            }}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      )}
    </div>
  );
}

/* ---------- markdown <-> sections ---------- */

function parseSections(body: string): Section[] {
  const lines = body.split("\n");
  const out: Section[] = [];
  let current: Section | null = null;
  for (const raw of lines) {
    const m = raw.match(/^##\s+(.+)$/);
    if (m) {
      if (current) {
        current.body = current.body.trim();
        out.push(current);
      }
      current = { title: m[1].trim(), body: "" };
      continue;
    }
    if (current) current.body += raw + "\n";
  }
  if (current) {
    current.body = current.body.trim();
    out.push(current);
  }
  return out;
}

function serializeSections(sections: Section[]): string {
  return (
    sections
      .map(({ title, body }) => `## ${title}\n\n${body.trim() || "_(empty)_"}\n`)
      .join("\n") + "\n"
  );
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}
