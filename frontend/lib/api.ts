export type ProjectSummary = {
  id: string;
  name: string;
  locked: boolean;
  created_at: string;
  latest_version: number | null;
  latest_ingested_at: string | null;
};

export type ProjectDetail = ProjectSummary & {
  charter: string;
  repos: string[];
  confluence_roots: string[];
  webex_channels: string[];
  ingest_config: Record<string, unknown>;
};

const BASE = ""; // proxied via next.config.js rewrites

export async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// SWR fetcher — pass URL as the SWR key.
export const swrFetcher = <T>(path: string) => req<T>(path);

export type PageKind = "stable" | "dynamic";

export type PageNode = {
  path: string;
  title: string;
  kind: PageKind;
  order: number;
  children: PageNode[];
};

export type ReportTreeResponse = {
  id: string;
  project_id: string;
  version: number;
  ingested_at: string;
  summary: string;
  is_greenfield: boolean;
  page_tree: PageNode[];
};

export type PageResponse = {
  path: string;
  markdown: string;
  frontmatter: Record<string, unknown>;
  body: string;
  revision_id: string | null;
  updated_at: string | null;
  author: string | null;
};

export const api = {
  createProject: (body: {
    name: string;
    charter?: string;
    repos?: string[];
    confluence_roots?: string[];
    webex_channels?: string[];
  }) => req<ProjectSummary>("/api/projects", { method: "POST", body: JSON.stringify(body) }),

  reingest: (projectId: string) =>
    req<{ run_id: string; status: string }>(
      `/api/projects/${projectId}/reingest`,
      { method: "POST" },
    ),

  putPage: (projectId: string, version: number, pagePath: string, markdown: string) =>
    req<{ path: string }>(
      `/api/projects/${projectId}/reports/${version}/pages/${pagePath}`,
      { method: "PUT", body: JSON.stringify({ markdown }) },
    ),

  createPage: (
    projectId: string,
    version: number,
    body: { path: string; title: string; parent_path?: string },
  ) =>
    req<{ path: string; title: string }>(
      `/api/projects/${projectId}/reports/${version}/pages`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  resetChat: (projectId: string) =>
    req<{ ok: boolean }>(`/api/projects/${projectId}/chat/reset`, { method: "POST" }),

  pageHistory: (projectId: string, pagePath: string) =>
    req<RevisionSummary[]>(
      `/api/projects/${projectId}/pages/${pagePath}/history`,
    ),

  getRevision: (projectId: string, revisionId: string) =>
    req<RevisionDetail>(`/api/projects/${projectId}/revisions/${revisionId}`),
};

export type RevisionSummary = {
  id: string;
  created_at: string;
  author: string;
  message: string;
  report_id: string | null;
};

export type RevisionDetail = RevisionSummary & {
  path: string;
  markdown: string;
  body: string;
  frontmatter: Record<string, unknown>;
};
