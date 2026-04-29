"use client";

import Link from "next/link";
import useSWR from "swr";
import { ProjectCard } from "@/components/ProjectCard";
import { swrFetcher, type ProjectSummary } from "@/lib/api";

export default function Home() {
  const { data: projects, error, isLoading } = useSWR<ProjectSummary[]>(
    "/api/projects",
    swrFetcher,
    { refreshInterval: 5000 },
  );

  return (
    <main>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <Link
          href="/projects/new"
          className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900"
        >
          New project
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          Backend unreachable: {(error as Error).message}
        </div>
      )}

      {!error && isLoading && (
        <p className="text-sm text-neutral-500">Loading…</p>
      )}

      {!error && !isLoading && projects && (
        projects.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No projects yet. Click <span className="font-mono">New project</span> to start.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <ProjectCard key={p.id} p={p} />
            ))}
          </div>
        )
      )}
    </main>
  );
}
