"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState("");
  const [charter, setCharter] = useState("");
  const [repos, setRepos] = useState("");
  const [confluence, setConfluence] = useState("");
  const [webex, setWebex] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createProject({
        name: name.trim(),
        charter: charter.trim(),
        repos: repos.split(",").map((s) => s.trim()).filter(Boolean),
        confluence_roots: confluence.split(",").map((s) => s.trim()).filter(Boolean),
        webex_channels: webex.split(",").map((s) => s.trim()).filter(Boolean),
      });
      mutate("/api/projects");
      router.push(`/projects/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <main>
      <h1 className="mb-6 text-2xl font-semibold">New project</h1>
      <form onSubmit={onSubmit} className="grid gap-4">
        <Field label="Name" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </Field>
        <Field
          label="Charter"
          hint="Persistent seed context — team mission, glossary, what leadership cares about."
        >
          <textarea
            value={charter}
            onChange={(e) => setCharter(e.target.value)}
            rows={4}
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </Field>
        <Field label="GitHub repos" hint="Comma-separated. e.g. org/repo1, org/repo2">
          <input
            value={repos}
            onChange={(e) => setRepos(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </Field>
        <Field label="Confluence root pages" hint="Comma-separated page IDs or URLs.">
          <input
            value={confluence}
            onChange={(e) => setConfluence(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </Field>
        <Field label="Webex channels" hint="Comma-separated channel IDs.">
          <input
            value={webex}
            onChange={(e) => setWebex(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </Field>

        {error && (
          <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting || !name.trim()}
            className="rounded bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded px-4 py-2 text-sm text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
          >
            Cancel
          </button>
        </div>
      </form>
    </main>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium">
        {label}
        {required && <span className="ml-0.5 text-red-600">*</span>}
      </div>
      {hint && <div className="mb-1 text-xs text-neutral-500">{hint}</div>}
      {children}
    </label>
  );
}
