"use client";

export type ProjectFormValues = {
  charter: string;
  phase: string;
  cadence: string;
  repos: string;
};

export function emptyProjectFormValues(): ProjectFormValues {
  return { charter: "", phase: "", cadence: "", repos: "" };
}

export type ProjectFormSubmit = {
  charter: string;
  phase: string | null;
  cadence: string | null;
  repos: string[];
};

export function projectFormValuesToSubmit(v: ProjectFormValues): ProjectFormSubmit {
  const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  return {
    charter: v.charter.trim(),
    phase: v.phase.trim() || null,
    cadence: v.cadence.trim() || null,
    repos: split(v.repos),
  };
}

export function projectFormValuesFromProject(p: {
  charter: string;
  phase: string | null;
  cadence: string | null;
  repos: { url: string }[];
}): ProjectFormValues {
  return {
    charter: p.charter || "",
    phase: p.phase || "",
    cadence: p.cadence || "",
    repos: (p.repos || []).map((r) => r.url).join(", "),
  };
}

const PHASE_OPTIONS = ["", "prototype", "venture", "active", "sunset"];
const CADENCE_OPTIONS = ["", "weekly", "monthly", "quiet"];

/**
 * Source-of-truth fields for project create + edit. The parent owns the name
 * (only create exposes it) and the submit button. Webex rooms / Confluence
 * spaces aren't editable here yet — add them via the MCP tools or the future
 * sources panel.
 */
export function ProjectFormFields({
  values,
  onChange,
  compact = false,
  showRepos = true,
}: {
  values: ProjectFormValues;
  onChange: (next: ProjectFormValues) => void;
  compact?: boolean;
  showRepos?: boolean;
}) {
  const set = <K extends keyof ProjectFormValues>(key: K, v: string) =>
    onChange({ ...values, [key]: v });

  const inputClass = `w-full rounded border border-neutral-300 bg-white px-3 py-2 ${
    compact ? "text-sm" : ""
  } dark:border-neutral-700 dark:bg-neutral-900`;

  return (
    <div className="grid gap-4">
      <Field
        label="Charter"
        hint="Persistent seed context — what this strategic effort is and why it exists."
      >
        <textarea
          value={values.charter}
          onChange={(e) => set("charter", e.target.value)}
          rows={4}
          className={inputClass}
        />
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Phase" hint="Lifecycle stage of the effort.">
          <select
            value={values.phase}
            onChange={(e) => set("phase", e.target.value)}
            className={inputClass}
          >
            {PHASE_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p || "(unset)"}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Cadence" hint="How often we expect material change.">
          <select
            value={values.cadence}
            onChange={(e) => set("cadence", e.target.value)}
            className={inputClass}
          >
            {CADENCE_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c || "(unset)"}
              </option>
            ))}
          </select>
        </Field>
      </div>
      {showRepos && (
        <Field label="GitHub repos" hint="Comma-separated. e.g. org/repo1, org/repo2">
          <input
            value={values.repos}
            onChange={(e) => set("repos", e.target.value)}
            className={inputClass}
          />
        </Field>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium">{label}</div>
      {hint && <div className="mb-1.5 text-xs text-neutral-500">{hint}</div>}
      {children}
    </label>
  );
}
