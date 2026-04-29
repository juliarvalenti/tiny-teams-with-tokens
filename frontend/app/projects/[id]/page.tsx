"use client";

import { use, useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ReingestButton } from "@/components/ReingestButton";
import { ReportEditor } from "@/components/ReportEditor";
import { WikiSidebar } from "@/components/WikiSidebar";
import {
  api,
  swrFetcher,
  type PageNode,
  type ProjectDetail,
  type ReportTreeResponse,
} from "@/lib/api";

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { mutate } = useSWRConfig();

  const project = useSWR<ProjectDetail>(`/api/projects/${id}`, swrFetcher, {
    refreshInterval: (latest) => (latest?.locked ? 1500 : 5000),
  });

  const version = project.data?.latest_version ?? null;
  const reportKey = version != null ? `/api/projects/${id}/reports/${version}` : null;
  const report = useSWR<ReportTreeResponse>(reportKey, swrFetcher);

  const [activePath, setActivePath] = useState<string | null>(null);
  const [createUnder, setCreateUnder] = useState<string | null | undefined>(undefined);

  // Default to overview.md when the tree first loads.
  useEffect(() => {
    if (activePath || !report.data) return;
    const flat = flattenTree(report.data.page_tree);
    const overview = flat.find((n) => n.path === "overview.md") ?? flat[0];
    if (overview) setActivePath(overview.path);
  }, [report.data, activePath]);

  const flatNodes = useMemo(
    () => (report.data ? flattenTree(report.data.page_tree) : []),
    [report.data],
  );
  const activeNode = flatNodes.find((n) => n.path === activePath) ?? null;

  if (project.error) {
    return (
      <div className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
        {(project.error as Error).message}
      </div>
    );
  }
  if (project.isLoading || !project.data) {
    return <p className="text-sm text-neutral-500">Loading…</p>;
  }

  const data = project.data;

  return (
    <main>
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">{data.name}</h1>
        <div className="flex items-center gap-3">
          {data.locked ? (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              ingest in progress…
            </span>
          ) : (
            <span className="text-xs text-neutral-500">v{data.latest_version ?? "—"}</span>
          )}
          <ReingestButton projectId={id} disabled={data.locked} />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <aside className="lg:sticky lg:top-6 self-start">
          {report.data ? (
            <WikiSidebar
              tree={report.data.page_tree}
              activePath={activePath}
              onSelect={setActivePath}
              onCreatePage={(parent) => setCreateUnder(parent)}
              disabled={data.locked}
            />
          ) : (
            <p className="text-sm text-neutral-500">
              {data.locked ? "Generating…" : "No report yet."}
            </p>
          )}
        </aside>

        <section>
          {version != null && activeNode ? (
            <ReportEditor
              projectId={id}
              version={version}
              pagePath={activeNode.path}
              pageTitle={activeNode.title}
              pageKind={activeNode.kind}
              locked={data.locked}
            />
          ) : version == null ? (
            <p className="text-sm text-neutral-500">
              {data.locked
                ? "Generating first wiki…"
                : "No report yet — click Reingest to generate one."}
            </p>
          ) : (
            <p className="text-sm text-neutral-500">Pick a page from the sidebar.</p>
          )}
        </section>
      </div>

      {createUnder !== undefined && version != null && (
        <NewPageModal
          projectId={id}
          version={version}
          parentPath={createUnder}
          onClose={() => setCreateUnder(undefined)}
          onCreated={(path) => {
            setCreateUnder(undefined);
            setActivePath(path);
            if (reportKey) mutate(reportKey);
          }}
        />
      )}
    </main>
  );
}

function flattenTree(tree: PageNode[]): PageNode[] {
  const out: PageNode[] = [];
  const visit = (n: PageNode) => {
    out.push(n);
    n.children.forEach(visit);
  };
  tree.forEach(visit);
  return out;
}

function NewPageModal({
  projectId,
  version,
  parentPath,
  onClose,
  onCreated,
}: {
  projectId: string;
  version: number;
  parentPath: string | null;
  onClose: () => void;
  onCreated: (path: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const slug = title
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
      if (!slug) throw new Error("title can't be empty");
      const result = await api.createPage(projectId, version, {
        path: `${slug}.md`,
        title: title.trim(),
        parent_path: parentPath ?? undefined,
      });
      onCreated(result.path);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-5 shadow-lg dark:border-neutral-800 dark:bg-neutral-900"
      >
        <h2 className="mb-2 text-lg font-semibold">New page</h2>
        <p className="mb-3 text-xs text-neutral-500">
          {parentPath ? (
            <>
              Will be created as a sub-page under <span className="font-mono">{parentPath}</span>.
            </>
          ) : (
            <>Will be created at the top level.</>
          )}{" "}
          New pages are <span className="font-medium">stable</span> — they're yours; ingest won't rewrite them.
        </p>
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Page title (e.g. Roadmap)"
          className="mb-3 w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          required
        />
        {error && (
          <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded px-3 py-1.5 text-sm text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !title.trim()}
            className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
