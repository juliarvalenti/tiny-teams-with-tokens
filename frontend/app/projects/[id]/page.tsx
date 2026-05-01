"use client";

import { use, useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Pencil } from "lucide-react";
import { ChatPanel } from "@/components/ChatPanel";
import { EditProjectModal } from "@/components/EditProjectModal";
import { IngestHistoryPanel } from "@/components/IngestHistoryPanel";
import { IngestLogStream } from "@/components/IngestLogStream";
import { ReingestButton } from "@/components/ReingestButton";
import { ReportEditor } from "@/components/ReportEditor";
import { StandupCard } from "@/components/StandupCard";
import { WikiSidebar } from "@/components/WikiSidebar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  const [showIngestHistory, setShowIngestHistory] = useState(false);
  const [showEditProject, setShowEditProject] = useState(false);

  // Default to The Standup (first report) when the tree first loads — it's
  // the highest-signal surface for cross-functional readers.
  useEffect(() => {
    if (activePath || !report.data) return;
    setActivePath("standup.md");
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
      <div className="grid gap-6 lg:grid-cols-[200px_1fr_360px]">
        <aside className="lg:sticky lg:top-6 self-start">
          <div className="group/title mb-3 flex h-8 items-center gap-1.5">
            <h1
              className="truncate text-2xl font-semibold leading-none"
              title={data.name}
            >
              {data.name}
            </h1>
            <button
              onClick={() => setShowEditProject(true)}
              className="rounded p-1 text-neutral-400 opacity-0 hover:bg-neutral-100 hover:text-neutral-700 group-hover/title:opacity-100 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
              title="Edit project"
              aria-label="Edit project"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          </div>
          {report.data ? (
            <WikiSidebar
              reports={[{ path: "standup.md", title: "The Standup" }]}
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
          {data.locked ? (
            <IngestLogStream runId={data.latest_run_id} />
          ) : version != null && activePath === "standup.md" ? (
            <StandupCard projectId={id} version={version} locked={data.locked} />
          ) : version != null && activeNode ? (
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
              No report yet — click Reingest to generate one.
            </p>
          ) : (
            <p className="text-sm text-neutral-500">Pick a page from the sidebar.</p>
          )}
        </section>

        <aside className="lg:sticky lg:top-6 self-start">
          <div className="mb-3 flex h-8 items-center justify-end gap-3">
            {data.locked ? (
              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                ingest in progress…
              </span>
            ) : (
              <span className="text-xs text-neutral-500">v{data.latest_version ?? "—"}</span>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowIngestHistory(true)}
              title="View past ingest logs"
            >
              Logs
            </Button>
            <ReingestButton projectId={id} disabled={data.locked} />
          </div>
          <ChatPanel projectId={id} reportKey={reportKey} version={version} />
        </aside>
      </div>

      {showIngestHistory && (
        <IngestHistoryPanel
          projectId={id}
          onClose={() => setShowIngestHistory(false)}
        />
      )}

      {showEditProject && (
        <EditProjectModal
          project={data}
          onClose={() => setShowEditProject(false)}
        />
      )}

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
  const [kind, setKind] = useState<"stable" | "dynamic" | "hidden">("stable");
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
        kind,
      });
      onCreated(result.path);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>New page</DialogTitle>
            <DialogDescription>
              {parentPath ? (
                <>
                  Will be created as a sub-page under{" "}
                  <span className="font-mono">{parentPath}</span>.
                </>
              ) : (
                <>Will be created at the top level.</>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="my-4 grid gap-3">
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Page title (e.g. Roadmap)"
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
              required
            />
            <KindToggle value={kind} onChange={setKind} />
          </div>
          {error && (
            <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </div>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !title.trim()}>
              {submitting ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function KindToggle({
  value,
  onChange,
}: {
  value: "stable" | "dynamic" | "hidden";
  onChange: (v: "stable" | "dynamic" | "hidden") => void;
}) {
  const opts: { key: "stable" | "dynamic" | "hidden"; label: string; hint: string }[] = [
    { key: "stable", label: "Stable", hint: "human-curated, preserved across ingests" },
    { key: "dynamic", label: "Dynamic", hint: "agent rewrites it on every ingest" },
    { key: "hidden", label: "Hidden", hint: "agent-only memory, not shown in sidebar" },
  ];
  return (
    <div>
      <div className="mb-1.5 text-sm font-medium">Kind</div>
      <div className="grid grid-cols-3 gap-1 rounded-md border border-neutral-200 bg-neutral-50 p-1 dark:border-neutral-800 dark:bg-neutral-900">
        {opts.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key)}
            className={`rounded px-3 py-1.5 text-xs font-medium transition ${
              value === o.key
                ? "bg-white text-neutral-900 shadow-sm dark:bg-neutral-800 dark:text-neutral-100"
                : "text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-neutral-500">
        {opts.find((o) => o.key === value)?.hint}
      </p>
    </div>
  );
}
