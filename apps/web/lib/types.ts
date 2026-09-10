// Mirrors apps/api/app/schemas/*.py. Kept as plain interfaces (no codegen)
// since the backend is the single source of truth for validation — these
// exist purely for editor/type-checking convenience on the client.

export type ProjectRole = "owner" | "editor" | "viewer";

export interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url: string | null;
  created_at: string;
}

export interface Project {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  role: ProjectRole;
  created_at: string;
}

export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

export interface ProjectDocument {
  id: string;
  project_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  status: DocumentStatus;
  uploaded_by: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id: string | null;
  };
}
