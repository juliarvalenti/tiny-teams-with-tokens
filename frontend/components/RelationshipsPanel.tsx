"use client";

import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  api,
  swrFetcher,
  type ProjectSummary,
  type RelationshipKind,
  type WorkspaceDoc,
  type WorkspaceGroup,
  type WorkspaceRelationship,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

const KIND_OPTIONS: { value: RelationshipKind; label: string }[] = [
  { value: "depends_on", label: "depends on" },
  { value: "blocks", label: "blocks" },
  { value: "shares_team", label: "shares team" },
  { value: "supersedes", label: "supersedes" },
];

function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 40);
}

export function RelationshipsPanel({ onClose }: { onClose: () => void }) {
  const { mutate } = useSWRConfig();
  const { data: doc } = useSWR<WorkspaceDoc>(
    "/api/workspace/relationships",
    swrFetcher,
  );
  const { data: projects } = useSWR<ProjectSummary[]>("/api/projects", swrFetcher);

  const [groups, setGroups] = useState<WorkspaceGroup[]>([]);
  const [rels, setRels] = useState<WorkspaceRelationship[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hydrate local state once the doc loads.
  useEffect(() => {
    if (!doc) return;
    setGroups(doc.groups);
    setRels(doc.relationships);
  }, [doc]);

  const projectName = (id: string) =>
    projects?.find((p) => p.id === id)?.name ?? id.slice(0, 8);

  async function onSave() {
    setSaving(true);
    setError(null);
    try {
      await api.putRelationships({ groups, relationships: rels });
      mutate("/api/workspace/relationships");
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        style={{ width: "95vw", maxWidth: "min(1000px, 95vw)" }}
        className="flex flex-col gap-0 p-0"
      >
        <SheetHeader className="border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
          <SheetTitle>Relationships</SheetTitle>
          <SheetDescription>
            Group projects and declare dependencies. Stored in
            <span className="font-mono"> data/relationships.yaml</span>; agents
            can read and propose updates.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-8 overflow-y-auto px-5 py-4">
          <section>
            <header className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-neutral-500">
                Groups
              </h3>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setGroups((gs) => [
                    ...gs,
                    { id: `group-${gs.length + 1}`, name: "", description: "", projects: [] },
                  ])
                }
              >
                <Plus className="h-3 w-3" /> Add group
              </Button>
            </header>
            {groups.length === 0 && (
              <p className="text-sm italic text-neutral-500">
                No groups yet. Groups bucket projects on the home page.
              </p>
            )}
            <div className="grid gap-3">
              {groups.map((g, i) => (
                <GroupRow
                  key={i}
                  group={g}
                  projects={projects ?? []}
                  projectName={projectName}
                  onChange={(next) =>
                    setGroups((gs) => gs.map((x, j) => (j === i ? next : x)))
                  }
                  onDelete={() =>
                    setGroups((gs) => gs.filter((_, j) => j !== i))
                  }
                />
              ))}
            </div>
          </section>

          <section>
            <header className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-neutral-500">
                Relationships
              </h3>
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  setRels((rs) => [
                    ...rs,
                    { from: projects?.[0]?.id ?? "", to: projects?.[1]?.id ?? "", kind: "depends_on", note: "" },
                  ])
                }
              >
                <Plus className="h-3 w-3" /> Add relationship
              </Button>
            </header>
            {rels.length === 0 && (
              <p className="text-sm italic text-neutral-500">
                No relationships yet. Use these to declare cross-project dependencies.
              </p>
            )}
            <div className="grid gap-2">
              {rels.map((r, i) => (
                <RelRow
                  key={i}
                  rel={r}
                  projects={projects ?? []}
                  onChange={(next) =>
                    setRels((rs) => rs.map((x, j) => (j === i ? next : x)))
                  }
                  onDelete={() => setRels((rs) => rs.filter((_, j) => j !== i))}
                />
              ))}
            </div>
          </section>
        </div>

        {error && (
          <div className="border-t border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-neutral-200 p-3 dark:border-neutral-800">
          <Button variant="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function GroupRow({
  group,
  projects,
  projectName,
  onChange,
  onDelete,
}: {
  group: WorkspaceGroup;
  projects: ProjectSummary[];
  projectName: (id: string) => string;
  onChange: (next: WorkspaceGroup) => void;
  onDelete: () => void;
}) {
  const inputClass =
    "w-full rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900";
  return (
    <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
      <div className="mb-2 grid grid-cols-[1fr_auto] gap-2">
        <input
          value={group.name}
          onChange={(e) => {
            const name = e.target.value;
            const wantId = !group.id || group.id.startsWith("group-");
            onChange({ ...group, name, id: wantId ? slugify(name) || group.id : group.id });
          }}
          placeholder="Group name (e.g. Payments Platform)"
          className={inputClass}
        />
        <button
          onClick={onDelete}
          aria-label="Delete group"
          className="rounded p-1.5 text-neutral-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <input
        value={group.description}
        onChange={(e) => onChange({ ...group, description: e.target.value })}
        placeholder="Description (optional)"
        className={`mb-2 ${inputClass}`}
      />
      <div className="mb-1 text-xs text-neutral-500">Projects in this group:</div>
      <div className="flex flex-wrap gap-1.5">
        {projects.map((p) => {
          const inGroup = group.projects.includes(p.id);
          return (
            <button
              key={p.id}
              type="button"
              onClick={() =>
                onChange({
                  ...group,
                  projects: inGroup
                    ? group.projects.filter((x) => x !== p.id)
                    : [...group.projects, p.id],
                })
              }
              className={`rounded border px-2 py-1 text-xs transition ${
                inGroup
                  ? "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-900/60 dark:bg-violet-900/30 dark:text-violet-300"
                  : "border-neutral-300 bg-white text-neutral-600 hover:border-neutral-400 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-400"
              }`}
            >
              {p.name}
            </button>
          );
        })}
      </div>
      {group.projects.some((id) => !projects.find((p) => p.id === id)) && (
        <p className="mt-1.5 text-[11px] text-amber-600 dark:text-amber-400">
          Some project IDs in this group don&apos;t resolve:{" "}
          {group.projects
            .filter((id) => !projects.find((p) => p.id === id))
            .map((id) => projectName(id))
            .join(", ")}
        </p>
      )}
    </div>
  );
}

function RelRow({
  rel,
  projects,
  onChange,
  onDelete,
}: {
  rel: WorkspaceRelationship;
  projects: ProjectSummary[];
  onChange: (next: WorkspaceRelationship) => void;
  onDelete: () => void;
}) {
  const selectClass =
    "rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900";
  return (
    <div className="grid grid-cols-[1fr_auto_1fr_2fr_auto] items-center gap-2 rounded border border-neutral-200 p-2 dark:border-neutral-800">
      <select
        value={rel.from}
        onChange={(e) => onChange({ ...rel, from: e.target.value })}
        className={selectClass}
      >
        <option value="">— from —</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <select
        value={rel.kind}
        onChange={(e) => onChange({ ...rel, kind: e.target.value as RelationshipKind })}
        className={selectClass}
      >
        {KIND_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <select
        value={rel.to}
        onChange={(e) => onChange({ ...rel, to: e.target.value })}
        className={selectClass}
      >
        <option value="">— to —</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <input
        value={rel.note}
        onChange={(e) => onChange({ ...rel, note: e.target.value })}
        placeholder="Note (optional)"
        className="rounded border border-neutral-300 bg-white px-2 py-1.5 text-sm dark:border-neutral-700 dark:bg-neutral-900"
      />
      <button
        onClick={onDelete}
        aria-label="Delete relationship"
        className="rounded p-1.5 text-neutral-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
