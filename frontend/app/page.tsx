"use client";

import Link from "next/link";
import useSWR from "swr";
import { ChatDock } from "@/components/chat/ChatDock";
import { ProjectCard } from "@/components/ProjectCard";
import { Button } from "@/components/ui/button";
import { api, swrFetcher, type ProjectSummary } from "@/lib/api";

export default function Home() {
  const projects = useSWR<ProjectSummary[]>("/api/projects", swrFetcher, {
    refreshInterval: 5000,
  });

  async function handleDelete(id: string) {
    await api.deleteProject(id);
    projects.mutate();
  }

  const error = projects.error;
  const isLoading = projects.isLoading;
  const projs = projects.data;

  return (
    <main className="pb-24">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Button size="sm" asChild>
          <Link href="/projects/new">New project</Link>
        </Button>
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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {projs.map((p) => (
              <ProjectCard key={p.id} p={p} relations={[]} onDelete={handleDelete} />
            ))}
          </div>
        )
      )}

      <ChatDock />
    </main>
  );
}
