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

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  document_filename: string;
  page_number: number;
  text: string;
  score: number;
}

export interface HybridSearchResult {
  chunk_id: string;
  document_id: string;
  document_filename: string;
  page_number: number;
  text: string;
  fused_score: number;
  vector_rank: number | null;
  vector_score: number | null;
  keyword_rank: number | null;
  keyword_score: number | null;
}

export interface Citation {
  source_number: number;
  document_id: string;
  document_chunk_id: string;
  document_filename: string;
  page_number: number;
  quote: string;
}

export interface AskAnswer {
  answer: string;
  citations: Citation[];
  sources_considered: number;
  model: string;
  insufficient_evidence: boolean;
}

export interface Conversation {
  id: string;
  project_id: string;
  title: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationCitation {
  id: string;
  source_number: number;
  document_id: string;
  document_chunk_id: string;
  document_filename: string;
  page_number: number;
  quote: string;
}

export type MessageRole = "user" | "assistant";

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  citations: ConversationCitation[];
}

export interface ConversationDetail extends Conversation {
  messages: ConversationMessage[];
}

export interface PostMessageResponse {
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
  insufficient_evidence: boolean;
  sources_considered: number;
  model: string;
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
