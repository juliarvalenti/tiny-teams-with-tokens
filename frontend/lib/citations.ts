/**
 * Defensive renderer-side resolver for bare citations the agent didn't link.
 *
 * The agent's system prompt asks it to emit `[commit abc](URL)` etc. with the
 * proper URL filled in. When it forgets and emits plain `[commit abc]`,
 * `[issue #142]`, `[PR #99]`, this function rewrites them to clickable
 * markdown links using the project's first repo as the default.
 *
 * Idempotent: already-linked citations (those with a `(http…)` suffix) are
 * left alone.
 */

const COMMIT_RE = /(?<![\(\\])\[(commit|sha)\s+`?([0-9a-f]{7,40})`?\](?!\()/gi;
const ISSUE_RE = /(?<![\(\\])\[issue\s+#?(\d+)\](?!\()/gi;
const PR_RE = /(?<![\(\\])\[PR\s+#?(\d+)\](?!\()/gi;
const HASH_RE = /(?<![\(\\])\[#(\d+)\](?!\()/g;
// GitHub mentions: `@handle`. Don't match inside markdown links, emails, or
// already-linked text. GitHub handle = alnum + hyphen, not starting with `-`,
// up to 39 chars.
const MENTION_RE = /(?<![\w@\(\\\/])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?!\w)/g;

function normalizeRepo(repo: string): string | null {
  let s = repo.trim().replace(/\/$/, "");
  for (const prefix of ["https://github.com/", "github.com/"]) {
    if (s.startsWith(prefix)) s = s.slice(prefix.length);
  }
  if (s.endsWith(".git")) s = s.slice(0, -4);
  const parts = s.split("/");
  if (parts.length < 2 || !parts[0] || !parts[1]) return null;
  return `${parts[0]}/${parts[1]}`;
}

export type CitationKind = "issue" | "pr" | "commit" | "release" | "mention";

export type CitationInfo = {
  kind: CitationKind;
  label: string;       // e.g. "#142", "abc1234", "@alice"
  repo?: string;       // owner/name (for repo-scoped kinds)
  handle?: string;     // GitHub handle (for mentions)
};

/**
 * Classify a URL as a citation if it points at a GitHub issue / PR / commit /
 * release / user. Returns `null` for non-citation URLs. Used by the Crepe
 * `linkAttr` hook to inject chip classes on rendered <a> tags.
 */
export function classifyCitationHref(href: string): CitationInfo | null {
  const repoMatch = href.match(
    /^https?:\/\/github\.com\/([^/]+\/[^/]+)\/(issues|pull|commit|releases\/tag)\/([^?#/]+)/i,
  );
  if (repoMatch) {
    const [, repo, kindRaw, ref] = repoMatch;
    if (kindRaw === "issues") return { kind: "issue", label: `#${ref}`, repo };
    if (kindRaw === "pull") return { kind: "pr", label: `#${ref}`, repo };
    if (kindRaw === "commit") return { kind: "commit", label: ref.slice(0, 7), repo };
    if (kindRaw === "releases/tag") return { kind: "release", label: ref, repo };
  }
  // GitHub user profile: github.com/<handle> with no further path. Handles
  // are alnum+hyphen, ≤39 chars. Excludes anything followed by `/`.
  const userMatch = href.match(
    /^https?:\/\/github\.com\/([A-Za-z0-9][A-Za-z0-9-]{0,38})\/?(?:[?#]|$)/,
  );
  if (userMatch) {
    const handle = userMatch[1];
    return { kind: "mention", label: `@${handle}`, handle };
  }
  return null;
}

export function resolveCitations(markdown: string, repos: string[]): string {
  const primary = repos.map(normalizeRepo).find((r): r is string => !!r);

  let out = markdown;
  // Repo-scoped patterns only run when a repo exists. Mentions always run.
  if (primary) {
    out = out.replace(COMMIT_RE, (_m, _kind, sha) => {
      const short = sha.slice(0, 7);
      return `[commit \`${short}\`](https://github.com/${primary}/commit/${sha})`;
    });
    out = out.replace(ISSUE_RE, (_m, n) =>
      `[issue #${n}](https://github.com/${primary}/issues/${n})`,
    );
    out = out.replace(PR_RE, (_m, n) =>
      `[PR #${n}](https://github.com/${primary}/pull/${n})`,
    );
    out = out.replace(HASH_RE, (_m, n) =>
      `[#${n}](https://github.com/${primary}/issues/${n})`,
    );
  }
  out = out.replace(MENTION_RE, (_m, handle) =>
    `[@${handle}](https://github.com/${handle})`,
  );
  return out;
}
