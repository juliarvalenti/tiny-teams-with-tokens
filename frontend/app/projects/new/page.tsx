"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  ProjectFormFields,
  emptyProjectFormValues,
  projectFormValuesToSubmit,
  type ProjectFormValues,
} from "@/components/ProjectFormFields";

export default function NewProjectPage() {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState("");
  const [values, setValues] = useState<ProjectFormValues>(emptyProjectFormValues());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createProject({
        name: name.trim(),
        ...projectFormValuesToSubmit(values),
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
        <label className="block">
          <div className="mb-1 text-sm font-medium">
            Name<span className="ml-0.5 text-red-600">*</span>
          </div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 dark:border-neutral-700 dark:bg-neutral-900"
          />
        </label>

        <ProjectFormFields values={values} onChange={setValues} />

        {error && (
          <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <Button type="submit" disabled={submitting || !name.trim()}>
            {submitting ? "Creating…" : "Create"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </form>
    </main>
  );
}
