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
      getMarkdown: () => crepeRef.current?.getMarkdown() ?? initialMarkdown,
    }),
    [initialMarkdown],
  );

  return <div ref={hostRef} className="milkdown-host" />;
});
