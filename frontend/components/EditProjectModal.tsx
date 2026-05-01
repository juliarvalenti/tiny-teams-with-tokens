"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { api, type ProjectDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  ProjectFormFields,
  projectFormValuesFromArrays,
  projectFormValuesToArrays,
  type ProjectFormValues,
} from "./ProjectFormFields";

export function EditProjectModal({
  project,
  onClose,
}: {
  project: ProjectDetail;
  onClose: () => void;
}) {
  const { mutate } = useSWRConfig();
  const [values, setValues] = useState<ProjectFormValues>(() =>
    projectFormValuesFromArrays(project),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.updateProject(project.id, projectFormValuesToArrays(values));
      mutate(`/api/projects/${project.id}`);
      mutate("/api/projects");
      onClose();
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Edit project</DialogTitle>
            <DialogDescription>
              Updates take effect on the next ingest. Project name can&apos;t be changed.
            </DialogDescription>
          </DialogHeader>

          <div className="my-5">
            <ProjectFormFields values={values} onChange={setValues} compact />
          </div>

          {project.locked && (
            <div className="mb-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300">
              Project is locked while ingest is running — saves will be rejected.
            </div>
          )}
          {error && (
            <div className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
              {error}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || project.locked}>
              {submitting ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
