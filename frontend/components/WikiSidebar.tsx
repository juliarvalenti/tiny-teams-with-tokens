"use client";

import { Eye, EyeOff, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
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
  onDeletePage,
  disabled,
}: {
  reports: ReportLink[];
  tree: PageNode[];
  activePath: string | null;
  onSelect: (path: string) => void;
  onCreatePage: (parentPath: string | null) => void;
  onDeletePage?: (path: string) => void;
  disabled?: boolean;
}) {
  const [showHidden, setShowHidden] = useState(false);

  // Count hidden nodes anywhere in the tree (for the toggle label) and
  // produce a hierarchy-preserving copy with hidden nodes pruned out (used
  // when the toggle is off). When the toggle is on, the original tree is
  // rendered as-is so hidden items appear in their natural position.
  const { renderedTree, hiddenCount } = useMemo(() => {
    let count = 0;
    const countHidden = (nodes: PageNode[]) => {
      for (const n of nodes) {
        if (n.kind === "hidden") count += 1;
        countHidden(n.children);
      }
    };
    countHidden(tree);

    const pruneHidden = (nodes: PageNode[]): PageNode[] => {
      const out: PageNode[] = [];
      for (const n of nodes) {
        if (n.kind === "hidden") continue;
        out.push({ ...n, children: pruneHidden(n.children) });
      }
      return out;
    };

    return {
      renderedTree: showHidden ? tree : pruneHidden(tree),
      hiddenCount: count,
    };
  }, [tree, showHidden]);

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
                    className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left ${
                      isActive
                        ? "bg-neutral-200 dark:bg-neutral-800"
                        : "hover:bg-neutral-100 dark:hover:bg-neutral-900"
                    }`}
                  >
                    <KindBadge kind="report" iconOnly />
                    <span className="truncate">{r.title}</span>
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
        {renderedTree.map((node) => (
          <Branch
            key={node.path}
            node={node}
            depth={0}
            activePath={activePath}
            onSelect={onSelect}
            onCreatePage={onCreatePage}
            onDeletePage={onDeletePage}
            disabled={disabled}
          />
        ))}
      </ul>

      <div className="mt-3 border-t border-neutral-200 pt-3 dark:border-neutral-800">
        <button
          onClick={() => setShowHidden((v) => !v)}
          className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-200"
          title={showHidden ? "Hide hidden pages" : "Show hidden pages"}
        >
          {showHidden ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
          <span className="uppercase tracking-wide">
            {showHidden ? "Hide" : "Show"} hidden ({hiddenCount})
          </span>
        </button>
      </div>
    </nav>
  );
}

function Branch({
  node,
  depth,
  activePath,
  onSelect,
  onCreatePage,
  onDeletePage,
  disabled,
}: {
  node: PageNode;
  depth: number;
  activePath: string | null;
  onSelect: (path: string) => void;
  onCreatePage: (parentPath: string | null) => void;
  onDeletePage?: (path: string) => void;
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
          className="flex flex-1 items-center gap-2 text-left"
        >
          <KindBadge kind={node.kind} iconOnly />
          <span className="truncate">{node.title}</span>
        </button>
        <div
          className={`flex items-center gap-0.5 ${
            hovered ? "opacity-100" : "opacity-0 group-hover:opacity-100"
          }`}
        >
          <button
            onClick={() => onCreatePage(node.path)}
            disabled={disabled}
            title="Add a sub-page"
            className="rounded px-1 text-xs text-neutral-500 hover:bg-neutral-200 hover:text-neutral-900 disabled:opacity-40 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
          >
            +
          </button>
          {onDeletePage && (
            <button
              onClick={() => {
                if (confirm(`Delete ${node.path}? History stays in the audit log.`)) {
                  onDeletePage(node.path);
                }
              }}
              disabled={disabled}
              title="Delete page (soft)"
              className="rounded p-0.5 text-neutral-500 hover:bg-red-100 hover:text-red-600 disabled:opacity-40 dark:hover:bg-red-900/40 dark:hover:text-red-400"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
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
              onDeletePage={onDeletePage}
              disabled={disabled}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

