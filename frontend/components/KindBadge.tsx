"use client";

import { Anchor, Eye, FileText, RefreshCw } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type Kind = "stable" | "dynamic" | "hidden" | "report";

type Spec = {
  label: string;
  Icon: ComponentType<{ className?: string }>;
  badgeClass: string;   // Background + border tint
  iconClass: string;    // Stroke color
  blurb: ReactNode;     // Tooltip content
};

const SPECS: Record<Kind, Spec> = {
  stable: {
    label: "stable",
    Icon: Anchor,
    badgeClass:
      "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-900/30 dark:text-emerald-300",
    iconClass: "text-emerald-700 dark:text-emerald-400",
    blurb: (
      <>
        <strong>Stable.</strong> Human-curated. Written once on greenfield ingest, then
        preserved across every reingest. Edit freely — your changes stick.
      </>
    ),
  },
  dynamic: {
    label: "dynamic",
    Icon: RefreshCw,
    badgeClass:
      "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-900/60 dark:bg-sky-900/30 dark:text-sky-300",
    iconClass: "text-sky-700 dark:text-sky-400",
    blurb: (
      <>
        <strong>Dynamic.</strong> Agent rewrites this page on every reingest. Your
        edits feed in as prior context — they may or may not survive verbatim.
      </>
    ),
  },
  hidden: {
    label: "hidden",
    Icon: Eye,
    badgeClass:
      "border-neutral-300 bg-neutral-100 text-neutral-700 dark:border-neutral-700 dark:bg-neutral-800/60 dark:text-neutral-300",
    iconClass: "text-neutral-600 dark:text-neutral-400",
    blurb: (
      <>
        <strong>Hidden.</strong> Agent-only memory. Read by the synthesizers and chat,
        not surfaced in the wiki. Useful for project-specific instructions or notes
        you want the agent to keep in mind.
      </>
    ),
  },
  report: {
    label: "report",
    Icon: FileText,
    badgeClass:
      "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-900/60 dark:bg-violet-900/30 dark:text-violet-300",
    iconClass: "text-violet-700 dark:text-violet-400",
    blurb: (
      <>
        <strong>Report.</strong> A focused, structured surface — not a wiki page. Lives
        above the wiki and renders as its own UI element. Editable, but the agent
        rewrites it on each ingest like dynamic pages.
      </>
    ),
  },
};

export function KindBadge({
  kind,
  size = "sm",
}: {
  kind: Kind;
  size?: "xs" | "sm";
}) {
  const spec = SPECS[kind];
  const { Icon } = spec;
  const sizing =
    size === "xs"
      ? "text-[9px] px-1 py-0 gap-0.5 h-auto"
      : "text-[10px] px-1.5 py-0.5 gap-1 h-auto";
  const iconSize = size === "xs" ? "h-2.5 w-2.5" : "h-3 w-3";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          className={`cursor-help font-medium uppercase tracking-wide ${sizing} ${spec.badgeClass}`}
        >
          <Icon className={`${iconSize} ${spec.iconClass}`} />
          <span>{spec.label}</span>
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="w-64 text-[11px] font-normal normal-case leading-relaxed">
        {spec.blurb}
      </TooltipContent>
    </Tooltip>
  );
}
