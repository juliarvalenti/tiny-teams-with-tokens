"use client";

export type ProjectFormValues = {
  charter: string;
  repos: string;
  confluence: string;
  webex: string;
};

export function emptyProjectFormValues(): ProjectFormValues {
  return { charter: "", repos: "", confluence: "", webex: "" };
}

export function projectFormValuesFromArrays(p: {
  charter: string;
  repos: string[];
  confluence_roots: string[];
  webex_channels: string[];
}): ProjectFormValues {
  return {
    charter: p.charter || "",
    repos: p.repos.join(", "),
    confluence: p.confluence_roots.join(", "),
    webex: p.webex_channels.join(", "),
  };
}

export function projectFormValuesToArrays(v: ProjectFormValues): {
  charter: string;
  repos: string[];
  confluence_roots: string[];
  webex_channels: string[];
} {
  const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
  return {
    charter: v.charter.trim(),
    repos: split(v.repos),
    confluence_roots: split(v.confluence),
    webex_channels: split(v.webex),
  };
}

/**
 * Source-of-truth fields for project create + edit. The parent owns the name
 * (only create exposes it) and the submit button.
 */
export function ProjectFormFields({
  values,
  onChange,
  compact = false,
}: {
  values: ProjectFormValues;
  onChange: (next: ProjectFormValues) => void;
  compact?: boolean;
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
        hint="Persistent seed context — team mission, glossary, what leadership cares about."
      >
        <textarea
          value={values.charter}
          onChange={(e) => set("charter", e.target.value)}
          rows={4}
          className={inputClass}
        />
      </Field>
      <Field label="GitHub repos" hint="Comma-separated. e.g. org/repo1, org/repo2">
        <input
          value={values.repos}
          onChange={(e) => set("repos", e.target.value)}
          className={inputClass}
        />
      </Field>
      <Field label="Confluence root pages" hint="Comma-separated page IDs or URLs.">
        <input
          value={values.confluence}
          onChange={(e) => set("confluence", e.target.value)}
          className={inputClass}
        />
      </Field>
      <Field label="Webex channels" hint="Comma-separated channel IDs.">
        <input
          value={values.webex}
          onChange={(e) => set("webex", e.target.value)}
          className={inputClass}
        />
      </Field>
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
