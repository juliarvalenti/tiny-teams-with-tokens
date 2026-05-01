"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { ProjectCard } from "@/components/ProjectCard";
import { RelationshipsPanel } from "@/components/RelationshipsPanel";
import { Button } from "@/components/ui/button";
import {
  swrFetcher,
  type ProjectSummary,
  type WorkspaceDoc,
} from "@/lib/api";

export default function Home() {
  const projects = useSWR<ProjectSummary[]>("/api/projects", swrFetcher, {
    refreshInterval: 5000,
  });
  const workspace = useSWR<WorkspaceDoc>(
    "/api/workspace/relationships",
    swrFetcher,
  );
  const [editing, setEditing] = useState(false);

  const error = projects.error;
  const isLoading = projects.isLoading;
  const projs = projects.data;
  const doc = workspace.data;

  return (
    <main>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => setEditing(true)}
            title="Group projects, declare cross-project relationships"
          >
            Relationships
          </Button>
          <Link
            href="/projects/new"
            className="inline-flex items-center justify-center rounded bg-neutral-900 px-3 py-1.5 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900"
          >
            New project
          </Link>
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          Backend unreachable: {(error as Error).message}
        </div>
      )}

      {!error && isLoading && (
        <p className="text-sm text-neutral-500">Loading…</p>
      )}

      {!error && !isLoading && projs && (
        projs.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No projects yet. Click <span className="font-mono">New project</span> to start.
          </p>
        ) : (
          <GroupedProjects projects={projs} doc={doc} />
        )
      )}

      {editing && <RelationshipsPanel onClose={() => setEditing(false)} />}
    </main>
  );
}

function GroupedProjects({
  projects,
  doc,
}: {
  projects: ProjectSummary[];
  doc: WorkspaceDoc | undefined;
}) {
  const groups = doc?.groups ?? [];
  const rels = doc?.relationships ?? [];

  // For each project, build the immediate-neighbor labels (e.g. "→ payments-api").
  const neighborLabels = (id: string): string[] => {
    const out: string[] = [];
    for (const r of rels) {
      if (r.from === id) {
        const target = projects.find((p) => p.id === r.to);
        if (target) out.push(`${arrow(r.kind)} ${target.name}`);
      } else if (r.to === id) {
        const target = projects.find((p) => p.id === r.from);
        if (target) out.push(`${arrowBack(r.kind)} ${target.name}`);
      }
    }
    return out;
  };

  // Bucket projects: each group, then "Other" for ungrouped. A project can
  // appear in multiple groups (membership isn't exclusive).
  const grouped: { group: { id: string; name: string; description: string }; projects: ProjectSummary[] }[] = [];
  const seen = new Set<string>();
  for (const g of groups) {
    const items = projects.filter((p) => g.projects.includes(p.id));
    items.forEach((p) => seen.add(p.id));
    grouped.push({ group: g, projects: items });
  }
  const ungrouped = projects.filter((p) => !seen.has(p.id));
  if (ungrouped.length > 0) {
    grouped.push({
      group: { id: "_ungrouped", name: groups.length > 0 ? "Other" : "All projects", description: "" },
      projects: ungrouped,
    });
  }

  return (
    <div className="space-y-8">
      {grouped.map(({ group, projects: gp }) =>
        gp.length === 0 ? null : (
          <section key={group.id}>
            <header className="mb-2">
              <h2 className="text-xs font-semibold uppercase tracking-[0.15em] text-neutral-500">
                {group.name}
              </h2>
              {group.description && (
                <p className="mt-0.5 text-xs text-neutral-500">{group.description}</p>
              )}
            </header>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {gp.map((p) => (
                <ProjectCard key={p.id} p={p} relations={neighborLabels(p.id)} />
              ))}
            </div>
          </section>
        ),
      )}
    </div>
  );
}

function arrow(kind: string): string {
  switch (kind) {
    case "depends_on":
      return "→ depends on";
    case "blocks":
      return "⛔ blocks";
    case "shares_team":
      return "↔ shares team";
    case "supersedes":
      return "↦ supersedes";
    default:
      return "→";
  }
}

function arrowBack(kind: string): string {
  switch (kind) {
    case "depends_on":
      return "← used by";
    case "blocks":
      return "⛔ blocked by";
    case "shares_team":
      return "↔ shares team";
    case "supersedes":
      return "↤ superseded by";
    default:
      return "←";
  }
}
