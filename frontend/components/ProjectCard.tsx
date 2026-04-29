import Link from "next/link";
import type { ProjectSummary } from "@/lib/api";

function age(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const days = Math.floor(ms / 86_400_000);
  if (days >= 1) return `${days}d ago`;
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 1) return `${hours}h ago`;
  const min = Math.max(1, Math.floor(ms / 60_000));
  return `${min}m ago`;
}

export function ProjectCard({ p }: { p: ProjectSummary }) {
  return (
    <Link
      href={`/projects/${p.id}`}
      className="block rounded-lg border border-neutral-200 bg-white p-4 transition hover:border-neutral-400 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-600"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">{p.name}</h2>
        {p.locked && (
          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
            ingesting
          </span>
        )}
      </div>
      <div className="mt-2 flex gap-4 text-xs text-neutral-500">
        <span>v{p.latest_version ?? "—"}</span>
        <span>updated {age(p.latest_ingested_at)}</span>
      </div>
    </Link>
  );
}
