"use client";

import { ArrowUp, Maximize2, MessageSquare, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { swrFetcher, type ProjectDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { resolveCitations } from "@/lib/citations";
import { CrepeEditor } from "../CrepeEditor";
import { useProjectChat, type ToolCall, type Turn } from "./useProjectChat";

/**
 * DeepWiki-style chat. Two states:
 *   - collapsed: a fixed bottom-center input bar.
 *   - expanded: a fullscreen overlay with the thread on the left and a
 *     "context" panel on the right showing tool calls + read previews.
 *
 * Reusable: when projectId is omitted (e.g. on the home page) the dock is
 * disabled with a "coming soon" hint — meta-chat across projects is its own
 * follow-up.
 */
export function ChatDock({
  projectId,
  projectName,
}: {
  projectId?: string;
  projectName?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const enabled = !!projectId;

  // useProjectChat assumes a projectId; for the disabled (home) variant we
  // skip the hook entirely.
  if (!enabled) {
    return (
      <Bar>
        <input
          disabled
          placeholder="Cross-project chat is coming soon — open a project to chat there."
          className="flex-1 bg-transparent text-sm text-neutral-500 placeholder:text-neutral-400 focus:outline-none"
        />
        <Button size="sm" disabled>
          <ArrowUp className="h-3 w-3" />
        </Button>
      </Bar>
    );
  }

  return (
    <ProjectScopedDock
      projectId={projectId!}
      projectName={projectName}
      expanded={expanded}
      setExpanded={setExpanded}
      draft={draft}
      setDraft={setDraft}
    />
  );
}

function ProjectScopedDock({
  projectId,
  projectName,
  expanded,
  setExpanded,
  draft,
  setDraft,
}: {
  projectId: string;
  projectName?: string;
  expanded: boolean;
  setExpanded: (v: boolean) => void;
  draft: string;
  setDraft: (v: string) => void;
}) {
  const { turns, streaming, sendTurn, reset } = useProjectChat(projectId);
  const { data: project } = useSWR<ProjectDetail>(
    `/api/projects/${projectId}`,
    swrFetcher,
  );
  const repos = (project?.repos ?? []).map((r) => r.url);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function send() {
    const text = draft.trim();
    if (!text || streaming) return;
    setDraft("");
    setExpanded(true);
    void sendTurn(text);
  }

  // Keep focus in the input across send / re-render.
  useEffect(() => {
    if (expanded) inputRef.current?.focus();
  }, [expanded]);

  // Auto-collapse on Escape.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !streaming) setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded, streaming, setExpanded]);

  const inputBar = (
    <Bar>
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100"
        title={expanded ? "Collapse" : "Expand"}
        aria-label={expanded ? "Collapse chat" : "Expand chat"}
      >
        {expanded ? <X className="h-4 w-4" /> : <MessageSquare className="h-4 w-4" />}
      </button>
      <textarea
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
          }
        }}
        placeholder={
          turns.length === 0
            ? `Ask anything about ${projectName ?? "this project"}…`
            : "Ask a follow-up question…"
        }
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm placeholder:text-neutral-400 focus:outline-none"
      />
      {turns.length > 0 && (
        <button
          onClick={reset}
          disabled={streaming}
          title="Reset thread"
          className="text-neutral-500 hover:text-neutral-800 disabled:opacity-40 dark:text-neutral-400 dark:hover:text-neutral-100"
          aria-label="Reset chat thread"
        >
          <RotateCcw className="h-4 w-4" />
        </button>
      )}
      <Button size="sm" onClick={send} disabled={streaming || !draft.trim()}>
        <ArrowUp className="h-3 w-3" />
      </Button>
    </Bar>
  );

  if (!expanded) return inputBar;

  return (
    <ExpandedShell
      onClose={() => setExpanded(false)}
      projectName={projectName}
      turns={turns}
      streaming={streaming}
      repos={repos}
      footer={inputBar}
    />
  );
}

/* ---------- collapsed bar ---------- */

function Bar({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-x-0 bottom-8 z-30 flex justify-center px-4">
      <div className="flex w-full max-w-2xl items-center gap-2 rounded-full border border-neutral-200 bg-white px-4 py-2 shadow-lg dark:border-neutral-800 dark:bg-neutral-900">
        {children}
      </div>
    </div>
  );
}

/* ---------- expanded overlay ---------- */

function ExpandedShell({
  onClose,
  projectName,
  turns,
  streaming,
  repos,
  footer,
}: {
  onClose: () => void;
  projectName?: string;
  turns: Turn[];
  streaming: boolean;
  repos: string[];
  footer: React.ReactNode;
}) {
  const threadRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [turns]);

  // Show in the right panel: union of all toolCalls across all turns.
  const allCalls = useMemo(
    () => turns.flatMap((t) => t.toolCalls),
    [turns],
  );

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-neutral-50 dark:bg-neutral-950">
      <header className="flex items-center justify-between border-b border-neutral-200 px-5 py-3 dark:border-neutral-800">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="rounded p-1 text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
            aria-label="Collapse chat"
          >
            <X className="h-4 w-4" />
          </button>
          <h2 className="text-sm font-semibold">
            Chat · <span className="text-neutral-500">{projectName ?? "project"}</span>
          </h2>
          {streaming && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              streaming…
            </span>
          )}
        </div>
        <div className="text-[10px] uppercase tracking-wider text-neutral-400">
          esc to collapse
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <section
          ref={threadRef}
          className="flex-1 overflow-y-auto px-6 pt-5 pb-32"
        >
          <div className="mx-auto max-w-3xl space-y-4">
            {turns.length === 0 && (
              <p className="text-sm text-neutral-500">
                Ask anything about this project. The agent reads the wiki, calls
                live GitHub tools, and can edit pages.
              </p>
            )}
            {turns.map((t, i) => (
              <TurnBubble key={i} turn={t} repos={repos} />
            ))}
          </div>
        </section>

        <aside className="w-[400px] shrink-0 overflow-y-auto border-l border-neutral-200 bg-white px-4 pt-4 pb-32 dark:border-neutral-800 dark:bg-neutral-900">
          <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.15em] text-neutral-500">
            Sources
          </h3>
          {allCalls.length === 0 ? (
            <p className="text-xs italic text-neutral-400">
              Tool calls and page reads will appear here.
            </p>
          ) : (
            <div className="space-y-3">
              {allCalls.map((tc) => (
                <ContextItem key={tc.id} call={tc} />
              ))}
            </div>
          )}
        </aside>
      </div>

      {footer}
    </div>
  );
}

function TurnBubble({ turn, repos }: { turn: Turn; repos: string[] }) {
  if (turn.role === "user") {
    return (
      <div className="ml-8 rounded-lg bg-neutral-900 px-3 py-2 text-sm text-white dark:bg-neutral-100 dark:text-neutral-900">
        {turn.text}
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-4 py-3 text-sm dark:border-neutral-800 dark:bg-neutral-900">
      {turn.toolCalls.length > 0 && (
        <ul className="mb-2 space-y-1 text-xs text-neutral-500">
          {turn.toolCalls.map((tc) => (
            <li key={tc.id} className="flex items-center gap-1.5">
              <span className={tc.status === "done" ? "text-emerald-600" : "text-amber-600"}>
                {tc.status === "done" ? "✓" : "•"}
              </span>
              <span className="font-mono">{labelForCall(tc)}</span>
            </li>
          ))}
        </ul>
      )}
      <AssistantText turn={turn} repos={repos} />
      {turn.error && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">{turn.error}</p>
      )}
    </div>
  );
}

/**
 * Render assistant text via Crepe in `liveUpdate` mode — same renderer the
 * wiki uses, so chat ↔ wiki markdown rendering is bound by definition. The
 * editor mounts once per turn and replaces its content as tokens stream in.
 * Citation resolver runs on every update to wire up unlinked `[issue #N]`.
 */
function AssistantText({ turn, repos }: { turn: Turn; repos: string[] }) {
  if (!turn.text.trim()) {
    return (
      <p className="italic text-neutral-400">
        {turn.done ? "(no answer)" : "…"}
      </p>
    );
  }
  const resolved = resolveCitations(turn.text, repos);
  return (
    <div className="chat-md-body -mx-1">
      <CrepeEditor initialMarkdown={resolved} readonly liveUpdate />
    </div>
  );
}

function ContextItem({ call }: { call: ToolCall }) {
  const subject = labelForCall(call);
  return (
    <div className="rounded border border-neutral-200 p-2 text-xs dark:border-neutral-800">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[11px] text-neutral-700 dark:text-neutral-300">
          {subject}
        </span>
        <span
          className={
            call.status === "done"
              ? "text-[10px] uppercase tracking-wider text-emerald-600"
              : "text-[10px] uppercase tracking-wider text-amber-600"
          }
        >
          {call.status}
        </span>
      </div>
      {call.preview && (
        <pre
          className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-neutral-50 p-1.5 text-[11px] leading-snug text-neutral-700 dark:bg-neutral-950 dark:text-neutral-300"
          style={{ overflowWrap: "anywhere" }}
        >
          {call.preview}
          {call.truncated ? "…" : ""}
        </pre>
      )}
    </div>
  );
}

function labelForCall(tc: ToolCall): string {
  const tool = tc.tool.replace("mcp__github__", "gh.").replace("mcp__workspace__", "ws.");
  const inp = tc.input || {};
  const path = (inp as { file_path?: string; path?: string }).file_path || (inp as { path?: string }).path;
  if (path) return `${tool} ${path}`;
  const repo = (inp as { repo?: string }).repo;
  const number = (inp as { number?: number }).number;
  if (repo && number != null) return `${tool} ${repo}#${number}`;
  if (repo) return `${tool} ${repo}`;
  return tool;
}

/* expose Maximize2 as unused to suppress import warning */
void Maximize2;
