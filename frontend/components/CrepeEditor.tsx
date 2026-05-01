"use client";

import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

export type CrepeEditorHandle = {
  getMarkdown: () => string;
};

type Props = {
  initialMarkdown: string;
  readonly?: boolean;
};

/**
 * Thin wrapper around Crepe. Mounts on the host div, exposes a ref handle
 * the parent can call to read the current markdown out (for save).
 *
 * IMPORTANT: this component does not re-create the editor when
 * `initialMarkdown` changes — that would clobber unsaved edits. Parents
 * should remount (via `key` prop) if they want a hard reset.
 */
export const CrepeEditor = forwardRef<CrepeEditorHandle, Props>(function CrepeEditor(
  { initialMarkdown, readonly = false },
  ref,
) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const crepeRef = useRef<Crepe | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    const crepe = new Crepe({
      root: hostRef.current,
      defaultValue: initialMarkdown,
    });
    crepeRef.current = crepe;
    let cancelled = false;
    crepe.create().then(() => {
      if (cancelled) return;
      crepe.setReadonly(readonly);
    });
    return () => {
      cancelled = true;
      crepe.destroy();
      crepeRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    crepeRef.current?.setReadonly(readonly);
  }, [readonly]);

  useImperativeHandle(
    ref,
    () => ({
      getMarkdown: () =>
        normalizeMarkdown(crepeRef.current?.getMarkdown() ?? initialMarkdown),
    }),
    [initialMarkdown],
  );

  return <div ref={hostRef} className="milkdown-host" />;
});

/**
 * Undo two over-eager round-trip artifacts from Milkdown's remark serializer:
 *
 *  1. **Setext → ATX heading conversion.** `## Heading` round-trips to
 *     `Heading\n--------`. We walk back to the previous blank line so
 *     multi-line setext headings split into ATX heading + paragraph body
 *     (ATX can't span lines).
 *  2. **Bracket escaping.** `[#213]` and `[commit abc]` round-trip to
 *     `\[#213]` and `\[commit abc\]` because remark sees `[…]` as
 *     potentially-link syntax. Our citations always use literal brackets,
 *     so unescape them.
 */
function normalizeMarkdown(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1] ?? "";
    const isSetextH1 = /^={3,}\s*$/.test(next);
    const isSetextH2 = /^-{3,}\s*$/.test(next);

    if ((isSetextH1 || isSetextH2) && line.trim()) {
      // Multi-line setext: pull all preceding non-blank lines off `out` to
      // assemble the full heading body, then split into ATX heading + paragraph.
      const headingLines: string[] = [line];
      while (out.length > 0 && out[out.length - 1].trim() !== "") {
        headingLines.unshift(out.pop() as string);
      }
      const prefix = isSetextH1 ? "# " : "## ";
      const headText = headingLines[0].replace(/\\$/, "").trim();
      out.push(prefix + headText);
      if (headingLines.length > 1) {
        out.push("");
        for (const l of headingLines.slice(1)) {
          out.push(l.replace(/\\$/, ""));
        }
      }
      i += 2;
      continue;
    }
    out.push(line);
    i += 1;
  }

  let result = out.join("\n");
  result = result.replace(/\\([\[\]])/g, "$1");
  return result;
}
