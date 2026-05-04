"use client";

import Link from "next/link";
import { useState } from "react";
import type { ProjectSummary } from "@/lib/api";

function age(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const days = Math.floor(ms / 86_400_000);
  if (days >= 1) return `${days}d ago`;
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 1) return `${hours}h ago`;
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "just now";
  return `${min}m ago`;
}

export function ProjectCard({
  p,
  relations,
  onDelete,
}: {
  p: ProjectSummary;
  relations?: string[];
  onDelete?: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);

  function handleDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirming) {
      setConfirming(true);
      return;
    }
    onDelete?.(p.id);
  }

  function handleCancelDelete(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setConfirming(false);
  }

  return (
    <Link
      href={`/projects/${p.id}`}
      className="group relative block rounded-lg border border-neutral-200 bg-white p-4 transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-600"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">{p.name}</h2>
        <div className="flex items-center gap-1">
          {p.locked && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              ingesting
            </span>
          )}
          {onDelete && !p.locked && (
            confirming ? (
              <span className="flex items-center gap-1">
                <button
                  onClick={handleDelete}
                  className="rounded px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                >
                  Delete
                </button>
                <button
                  onClick={handleCancelDelete}
                  className="rounded px-1.5 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                onClick={handleDelete}
                className="invisible rounded p-0.5 text-neutral-400 hover:text-red-500 group-hover:visible dark:text-neutral-600 dark:hover:text-red-400"
                title="Delete project"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </button>
            )
          )}
        </div>
      </div>
      <div className="mt-2 flex gap-4 text-xs text-neutral-500">
        <span>v{p.latest_version ?? "—"}</span>
        <span>updated {age(p.latest_ingested_at)}</span>
      </div>
      {relations && relations.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {relations.map((r, i) => (
            <span
              key={i}
              className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600 dark:bg-neutral-800 dark:text-neutral-400"
            >
              {r}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
