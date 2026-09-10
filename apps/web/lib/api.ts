import { API_URL } from "./config";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./tokens";
import type {
  ApiErrorBody,
  AskAnswer,
  HybridSearchResult,
  Project,
  ProjectDocument,
  ProjectMember,
  SearchResult,
  TokenPair,
  User,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  // Coalesce concurrent 401s into a single refresh call.
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (response) => {
        if (!response.ok) return false;
        const tokens: TokenPair = await response.json();
        setTokens(tokens.access_token, tokens.refresh_token);
        return true;
      })
      .catch(() => false)
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  isForm?: boolean;
  skipAuth?: boolean;
  /** Internal: prevents infinite refresh loops. */
  _retried?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (options.isForm) {
    body = options.body as FormData;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  if (!options.skipAuth) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body,
  });

  if (response.status === 401 && !options.skipAuth && !options._retried) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, { ...options, _retried: true });
    }
    clearTokens();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "unauthorized", "Session expired.");
  }

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = await response.json();
    } catch {
      // non-JSON error body; fall through to generic message
    }
    throw new ApiError(
      response.status,
      body?.error?.code ?? "unknown_error",
      body?.error?.message ?? `Request failed with status ${response.status}.`
    );
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  // --- auth ---
  loginUrl: (provider: "google" | "mock", email?: string) => {
    const params = email ? `?email=${encodeURIComponent(email)}` : "";
    return request<{ authorize_url: string; state: string }>(
      `/auth/${provider}/login${params}`,
      { skipAuth: true }
    );
  },
  exchangeCode: (provider: "google" | "mock", code: string) =>
    request<TokenPair>(`/auth/${provider}/callback?code=${encodeURIComponent(code)}`, {
      skipAuth: true,
    }),
  me: () => request<User>("/auth/me"),

  // --- projects ---
  listProjects: () => request<Project[]>("/projects"),
  createProject: (data: { name: string; description?: string }) =>
    request<Project>("/projects", { method: "POST", body: data }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  updateProject: (id: string, data: { name?: string; description?: string }) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", body: data }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),
  listMembers: (projectId: string) =>
    request<ProjectMember[]>(`/projects/${projectId}/members`),
  inviteMember: (projectId: string, data: { email: string; role: string }) =>
    request<ProjectMember>(`/projects/${projectId}/members`, { method: "POST", body: data }),
  removeMember: (projectId: string, userId: string) =>
    request<void>(`/projects/${projectId}/members/${userId}`, { method: "DELETE" }),

  // --- documents ---
  listDocuments: (projectId: string) =>
    request<ProjectDocument[]>(`/projects/${projectId}/documents`),
  uploadDocument: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ProjectDocument>(`/projects/${projectId}/documents`, {
      method: "POST",
      body: form,
      isForm: true,
    });
  },
  documentDownloadUrl: (projectId: string, documentId: string) =>
    `${API_URL}/projects/${projectId}/documents/${documentId}/download`,

  // --- search ---
  semanticSearch: (projectId: string, query: string, limit = 10) =>
    request<SearchResult[]>(`/projects/${projectId}/search`, {
      method: "POST",
      body: { query, limit },
    }),
  keywordSearch: (projectId: string, query: string, limit = 10) =>
    request<SearchResult[]>(`/projects/${projectId}/search/keyword`, {
      method: "POST",
      body: { query, limit },
    }),
  hybridSearch: (projectId: string, query: string, limit = 10) =>
    request<HybridSearchResult[]>(`/projects/${projectId}/search/hybrid`, {
      method: "POST",
      body: { query, limit },
    }),
  rerankSearch: (projectId: string, query: string, limit = 6) =>
    request<SearchResult[]>(`/projects/${projectId}/search/rerank`, {
      method: "POST",
      body: { query, limit },
    }),

  // --- rag ---
  ask: (projectId: string, question: string, topK = 6) =>
    request<AskAnswer>(`/projects/${projectId}/ask`, {
      method: "POST",
      body: { question, top_k: topK },
    }),
};

export { API_URL };
