"use client";

import { useState } from "react";
import type { PageNode } from "@/lib/api";
import { KindBadge } from "./KindBadge";

export type ReportLink = {
  path: string;
  title: string;
};

export function WikiSidebar({
  reports,
  tree,
  activePath,
  onSelect,
  onCreatePage,
  disabled,
}: {
  reports: ReportLink[];
  tree: PageNode[];
  activePath: string | null;
  onSelect: (path: string) => void;
  onCreatePage: (parentPath: string | null) => void;
  disabled?: boolean;
}) {
  return (
    <nav className="text-sm">
      {reports.length > 0 && (
        <>
          <div className="mb-2">
            <span className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              Reports
            </span>
          </div>
          <ul className="mb-5 space-y-0.5">
            {reports.map((r) => {
              const isActive = r.path === activePath;
              return (
                <li key={r.path}>
                  <button
                    onClick={() => onSelect(r.path)}
                    className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left ${
                      isActive
                        ? "bg-neutral-200 dark:bg-neutral-800"
                        : "hover:bg-neutral-100 dark:hover:bg-neutral-900"
                    }`}
                  >
                    <span className="truncate">{r.title}</span>
                    <KindBadge kind="report" size="xs" />
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}

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
          <KindBadge kind={node.kind} size="xs" />
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

