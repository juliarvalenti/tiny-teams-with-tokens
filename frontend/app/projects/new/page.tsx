"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  api,
  swrFetcher,
  type ProjectSummary,
  type RelationshipKind,
  type WorkspaceDoc,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  ProjectFormFields,
  emptyProjectFormValues,
  projectFormValuesToArrays,
  type ProjectFormValues,
} from "@/components/ProjectFormFields";

const KIND_OPTIONS: { value: RelationshipKind; label: string }[] = [
  { value: "depends_on", label: "depends on" },
  { value: "blocks", label: "blocks" },
  { value: "shares_team", label: "shares team" },
  { value: "supersedes", label: "supersedes" },
];

type DraftRel = { to: string; kind: RelationshipKind; note: string };

export default function NewProjectPage() {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState("");
  const [values, setValues] = useState<ProjectFormValues>(emptyProjectFormValues());
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<DraftRel[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: workspace } = useSWR<WorkspaceDoc>(
    "/api/workspace/relationships",
    swrFetcher,
  );
  const { data: existingProjects } = useSWR<ProjectSummary[]>(
    "/api/projects",
    swrFetcher,
  );

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createProject({
        name: name.trim(),
        ...projectFormValuesToArrays(values),
      });

      // Stitch relationships into the workspace doc if anything was picked.
      if (groupIds.length > 0 || drafts.length > 0) {
        const current = workspace ?? { groups: [], relationships: [] };
        const nextGroups = current.groups.map((g) =>
          groupIds.includes(g.id)
            ? { ...g, projects: [...g.projects, created.id] }
            : g,
        );
        const nextRels = [
          ...current.relationships,
          ...drafts
            .filter((d) => d.to)
            .map((d) => ({ from: created.id, to: d.to, kind: d.kind, note: d.note })),
        ];
        try {
          await api.putRelationships({ groups: nextGroups, relationships: nextRels });
        } catch (relErr) {
          // The project IS created; just surface the relationship-save failure.
          // User can re-attach via the Relationships sheet on the home page.
          console.warn("relationship save failed", relErr);
        }
      }

      mutate("/api/projects");
      mutate("/api/workspace/relationships");
      router.push(`/projects/${created.id}`);
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  const groups = workspace?.groups ?? [];
  const projects = existingProjects ?? [];

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

        {(groups.length > 0 || projects.length > 0) && (
          <div className="rounded border border-neutral-200 p-4 dark:border-neutral-800">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.15em] text-neutral-500">
              Relationships
            </h2>

            {groups.length > 0 && (
              <div className="mb-4">
                <div className="mb-1.5 text-sm font-medium">Add to groups</div>
                <p className="mb-2 text-xs text-neutral-500">
                  Buckets the project lives under on the home page.
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {groups.map((g) => {
                    const on = groupIds.includes(g.id);
                    return (
                      <button
                        key={g.id}
                        type="button"
                        onClick={() =>
                          setGroupIds((ids) =>
                            on ? ids.filter((x) => x !== g.id) : [...ids, g.id],
                          )
                        }
                        className={`rounded border px-2 py-1 text-xs transition ${
                          on
                            ? "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-900/60 dark:bg-violet-900/30 dark:text-violet-300"
                            : "border-neutral-300 bg-white text-neutral-600 hover:border-neutral-400 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400"
                        }`}
                      >
                        {g.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {projects.length > 0 && (
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <div className="text-sm font-medium">Cross-project links</div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setDrafts((rs) => [
                        ...rs,
                        { to: projects[0]?.id ?? "", kind: "depends_on", note: "" },
                      ])
                    }
                  >
                    <Plus className="h-3 w-3" /> Add link
                  </Button>
                </div>
                <p className="mb-2 text-xs text-neutral-500">
                  This project relates to existing projects how?
                </p>
                <div className="grid gap-2">
                  {drafts.map((d, i) => (
                    <div
                      key={i}
                      className="grid grid-cols-[auto_1fr_2fr_auto] items-center gap-2"
                    >
                      <select
                        value={d.kind}
                        onChange={(e) =>
                          setDrafts((rs) =>
                            rs.map((x, j) =>
                              j === i ? { ...x, kind: e.target.value as RelationshipKind } : x,
                            ),
                          )
                        }
                        className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                      >
                        {KIND_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                      <select
                        value={d.to}
                        onChange={(e) =>
                          setDrafts((rs) =>
                            rs.map((x, j) => (j === i ? { ...x, to: e.target.value } : x)),
                          )
                        }
                        className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                      >
                        <option value="">— project —</option>
                        {projects.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name}
                          </option>
                        ))}
                      </select>
                      <input
                        value={d.note}
                        onChange={(e) =>
                          setDrafts((rs) =>
                            rs.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)),
                          )
                        }
                        placeholder="Note (optional)"
                        className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
                      />
                      <button
                        type="button"
                        onClick={() => setDrafts((rs) => rs.filter((_, j) => j !== i))}
                        aria-label="Delete link"
                        className="rounded p-1.5 text-neutral-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

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
