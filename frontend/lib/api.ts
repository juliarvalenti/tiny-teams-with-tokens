export type ProjectSummary = {
  id: string;
  name: string;
  locked: boolean;
  created_at: string;
  phase: string | null;
  cadence: string | null;
  repo_count: number;
  webex_room_count: number;
  confluence_space_count: number;
  latest_version: number | null;
  latest_ingested_at: string | null;
};

export type RepoOut = {
  id: string;
  project_id: string;
  slug: string;
  url: string;
  default_branch: string;
};

export type WebexRoomOut = {
  id: string;
  project_id: string;
  slug: string;
  name: string;
  webex_id: string | null;
};

export type ConfluenceSpaceOut = {
  id: string;
  project_id: string;
  slug: string;
  name: string;
  space_key: string;
  base_url: string;
};

export type ProjectDetail = ProjectSummary & {
  charter: string;
  ingest_config: Record<string, unknown>;
  repos: RepoOut[];
  webex_rooms: WebexRoomOut[];
  confluence_spaces: ConfluenceSpaceOut[];
  latest_run_id: string | null;
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

export type PageKind = "stable" | "dynamic" | "hidden" | "report";
// `folder` is a sidebar-only marker for synthesized non-clickable headers
// (when nested children exist without a real `<dir>.md` parent page).
export type NodeKind = PageKind | "folder";

export type PageNode = {
  path: string;
  title: string;
  kind: NodeKind;
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
    phase?: string | null;
    cadence?: string | null;
    repos?: string[];
  }) => req<ProjectSummary>("/api/projects", { method: "POST", body: JSON.stringify(body) }),

  updateProject: (
    id: string,
    body: {
      charter?: string;
      phase?: string | null;
      cadence?: string | null;
    },
  ) =>
    req<ProjectSummary>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  addRepo: (projectId: string, body: { url: string; slug?: string; default_branch?: string }) =>
    req<RepoOut>(`/api/projects/${projectId}/repos`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

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
    body: {
      path: string;
      title: string;
      parent_path?: string;
      kind?: "stable" | "dynamic" | "hidden";
    },
  ) =>
    req<{ path: string; title: string; kind: string }>(
      `/api/projects/${projectId}/reports/${version}/pages`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  patchFrontmatter: (
    projectId: string,
    version: number,
    pagePath: string,
    body: { kind?: PageKind; title?: string; order?: number },
  ) =>
    req<{ path: string; frontmatter: Record<string, unknown> }>(
      `/api/projects/${projectId}/reports/${version}/pages/${pagePath}/frontmatter`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  deletePage: (projectId: string, version: number, pagePath: string) =>
    req<{ deleted: boolean; path: string }>(
      `/api/projects/${projectId}/reports/${version}/pages/${pagePath}`,
      { method: "DELETE" },
    ),

  cancelIngest: (projectId: string) =>
    req<{ status: string }>(`/api/projects/${projectId}/ingest/cancel`, { method: "POST" }),

  deleteProject: (projectId: string) =>
    req<void>(`/api/projects/${projectId}`, { method: "DELETE" }),

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

export type IngestRunSummary = {
  id: string;
  status: "pending" | "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  error: string | null;
  log_lines: number;
};

export type IngestRunDetail = {
  id: string;
  status: "pending" | "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  error: string | null;
  log: string;
};

