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

export type ReportType =
  | "executive_summary"
  | "evidence_report"
  | "risk_analysis"
  | "chronology"
  | "contradiction_report"
  | "research_memo";

export type ReportStatus = "queued" | "processing" | "ready" | "failed";

export interface Report {
  id: string;
  project_id: string;
  report_type: ReportType;
  title: string;
  status: ReportStatus;
  error: string | null;
  created_by: string;
  created_at: string;
}

export interface ReportCitation {
  id: string;
  source_number: number;
  document_id: string;
  document_chunk_id: string;
  document_filename: string;
  page_number: number;
  quote: string;
}

export interface ReportSection {
  id: string;
  heading: string;
  content: string;
  position: number;
  citations: ReportCitation[];
}

export interface ReportDetail extends Report {
  sections: ReportSection[];
}

export type EvaluationRunStatus = "queued" | "running" | "succeeded" | "failed";

export interface EvaluationRun {
  id: string;
  project_id: string;
  dataset_name: string;
  dataset_version: number;
  prompt_version_id: string | null;
  model: string;
  retriever_version: string;
  status: EvaluationRunStatus;
  error: string | null;
  created_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface EvaluationGraderDetail {
  grader: string;
  score: number;
  reason: string;
  failures: string[];
  judge_model: string;
  prompt_version: string;
  temperature: number;
}

export interface EvaluationResult {
  id: string;
  example_id: string;
  question: string;
  generated_answer: string;
  expected_answer: string | null;
  faithfulness_score: number | null;
  relevance_score: number | null;
  completeness_score: number | null;
  citation_support_score: number | null;
  citation_correct: boolean;
  judge_reason: string | null;
  recall_at_k: number | null;
  precision_at_k: number | null;
  mrr: number | null;
  ndcg_at_k: number | null;
  latency_ms: number;
  cost_usd: number;
  model_run_id: string | null;
  grader_details: {
    faithfulness: EvaluationGraderDetail;
    relevance: EvaluationGraderDetail;
    completeness: EvaluationGraderDetail | null;
    citation_support: EvaluationGraderDetail;
    deterministic_failures: string[];
  };
}

export interface EvaluationRunDetail extends EvaluationRun {
  results: EvaluationResult[];
}

export interface CostDay {
  day: string;
  model: string;
  user_id: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  run_count: number;
}

export interface CostSummary {
  project_id: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_runs: number;
  by_day: CostDay[];
  by_model: Record<string, number>;
  by_user: Record<string, number>;
}

export type HumanReviewStatus = "needs_review" | "approved" | "rejected" | "corrected";

export interface HumanReview {
  id: string;
  project_id: string;
  message_id: string;
  status: HumanReviewStatus;
  flagged_by: string;
  reviewer_id: string | null;
  reviewed_at: string | null;
  original_answer: string;
  corrected_answer: string | null;
  reason: string | null;
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
