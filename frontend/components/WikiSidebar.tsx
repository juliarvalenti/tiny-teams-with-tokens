"use client";

import { useState } from "react";
import type { PageNode } from "@/lib/api";

export function WikiSidebar({
  tree,
  activePath,
  onSelect,
  onCreatePage,
  disabled,
}: {
  tree: PageNode[];
  activePath: string | null;
  onSelect: (path: string) => void;
  onCreatePage: (parentPath: string | null) => void;
  disabled?: boolean;
}) {
  return (
    <nav className="text-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
          Pages
        </span>
        <button
          onClick={() => onCreatePage(null)}
          disabled={disabled}
          title={disabled ? "locked while ingest is running" : "Add a top-level page"}
          className="rounded px-1.5 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 disabled:opacity-40 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
        >
          + new
        </button>
      </div>
      <ul className="space-y-0.5">
        {tree.map((node) => (
          <Branch
            key={node.path}
            node={node}
            depth={0}
            activePath={activePath}
            onSelect={onSelect}
            onCreatePage={onCreatePage}
            disabled={disabled}
          />
        ))}
      </ul>

      <KindLegend />
    </nav>
  );
}

function Branch({
  node,
  depth,
  activePath,
  onSelect,
  onCreatePage,
  disabled,
}: {
  node: PageNode;
  depth: number;
  activePath: string | null;
  onSelect: (path: string) => void;
  onCreatePage: (parentPath: string | null) => void;
  disabled?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const isActive = node.path === activePath;
  return (
    <li>
      <div
        className={`group flex items-center justify-between rounded px-2 py-1 ${
          isActive
            ? "bg-neutral-200 dark:bg-neutral-800"
            : "hover:bg-neutral-100 dark:hover:bg-neutral-900"
        }`}
        style={{ paddingLeft: `${0.5 + depth * 0.75}rem` }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <button
          onClick={() => onSelect(node.path)}
          className="flex flex-1 items-center gap-1.5 text-left"
        >
          <span className="truncate">{node.title}</span>
          <KindBadge kind={node.kind} />
        </button>
        <button
          onClick={() => onCreatePage(node.path)}
          disabled={disabled}
          title="Add a sub-page"
          className={`rounded px-1 text-xs text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900 disabled:opacity-40 dark:hover:bg-neutral-700 dark:hover:text-neutral-100 ${
            hovered ? "opacity-100" : "opacity-0 group-hover:opacity-100"
          }`}
        >
          +
        </button>
      </div>
      {node.children.length > 0 && (
        <ul className="mt-0.5 space-y-0.5">
          {node.children.map((child) => (
            <Branch
              key={child.path}
              node={child}
              depth={depth + 1}
              activePath={activePath}
              onSelect={onSelect}
              onCreatePage={onCreatePage}
              disabled={disabled}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function KindBadge({ kind }: { kind: PageNode["kind"] }) {
  if (kind === "stable") {
    return (
      <span
        title="Stable: human-curated. Reingest preserves your edits."
        className="rounded bg-emerald-100 px-1 text-[10px] font-medium uppercase tracking-wide text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
      >
        stable
      </span>
    );
  }
  return (
    <span
      title="Dynamic: agent-rewritten on each reingest. Hand edits will be overwritten next ingest."
      className="rounded bg-sky-100 px-1 text-[10px] font-medium uppercase tracking-wide text-sky-800 dark:bg-sky-900/40 dark:text-sky-300"
    >
      dynamic
    </span>
  );
}

function KindLegend() {
  return (
    <div className="mt-6 space-y-1 border-t border-neutral-200 pt-3 text-[11px] text-neutral-500 dark:border-neutral-800">
      <div className="flex items-center gap-1.5">
        <KindBadge kind="stable" />
        <span>human-owned, preserved across ingests</span>
      </div>
      <div className="flex items-center gap-1.5">
        <KindBadge kind="dynamic" />
        <span>agent-rewritten each reingest</span>
      </div>
    </div>
  );
}
