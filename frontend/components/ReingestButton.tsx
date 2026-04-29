"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";

export function ReingestButton({
  projectId,
  disabled,
}: {
  projectId: string;
  disabled?: boolean;
}) {
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    setBusy(true);
    setError(null);
    try {
      await api.reingest(projectId);
      // Force SWR to refetch project + reports list.
      mutate(`/api/projects/${projectId}`);
      mutate(`/api/projects/${projectId}/reports`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        onClick={onClick}
        disabled={busy || disabled}
        title={disabled ? "ingest already in progress" : "Re-run the ingest pipeline"}
        className="rounded border border-neutral-300 px-3 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
      >
        {busy ? "Starting…" : "Reingest"}
      </button>
      {error && (
        <div className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</div>
      )}
    </div>
  );
}
