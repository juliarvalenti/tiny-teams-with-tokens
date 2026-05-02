"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_TTT_API_URL || "http://localhost:8765";

export function ReingestButton({
  projectId,
  disabled,
}: {
  projectId: string;
  disabled?: boolean;
}) {
  const { mutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [seed, setSeed] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch(`${BACKEND_URL}/api/projects/${projectId}/reingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed: seed.trim() || null }),
      });
      if (!resp.ok) throw new Error(`${resp.status} ${await resp.text()}`);
      mutate(`/api/projects/${projectId}`);
      mutate(`/api/projects/${projectId}/reports`);
      mutate(`/api/projects/${projectId}/ingests`);
      setOpen(false);
      setSeed("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen(true)}
        disabled={disabled}
        title={disabled ? "ingest already in progress" : "Re-run the ingest pipeline"}
      >
        Reingest
      </Button>

      <Dialog open={open} onOpenChange={(o) => !o && !busy && setOpen(false)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Reingest project</DialogTitle>
            <DialogDescription>
              Run another ingest now. Optionally seed the agent with a one-shot
              instruction for this run — e.g. &ldquo;focus on the SSE leak&rdquo;
              or &ldquo;summarize the v1.0.7 cycle&rdquo;.
            </DialogDescription>
          </DialogHeader>

          <div className="my-4">
            <label className="block">
              <div className="mb-1 text-sm font-medium">Seed instruction</div>
              <div className="mb-1.5 text-xs text-neutral-500">
                Optional. Goes to the agent alongside the standard ingest prompt.
                Doesn&apos;t override page-kind preservation rules.
              </div>
              <textarea
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                placeholder="(blank = standard ingest)"
                rows={4}
                disabled={busy}
                className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-900"
              />
            </label>
          </div>

          {error && (
            <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button type="button" onClick={onSubmit} disabled={busy}>
              {busy ? "Starting…" : "Run ingest"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
