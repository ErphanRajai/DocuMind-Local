export type Source = {
  id: string;
  pdf_id: number;
  page: number;
  filename: string;
  excerpt: string;
};
export type Metrics = {
  awaiting_interpretation?: boolean;
  request_question?: string;
  sources?: Source[];
  source_notice?: string;
  citation_warning?: string;
  quote_checks?: { quote: string; verified: boolean; sources: string[] }[];
  warnings?: string[];
  contextual_retrieval?: boolean;
  pages_reviewed?: number;
  segments_reviewed?: number;
  cache_hits?: number;
  tok_per_sec?: number;
  ttft_ms?: number;
  context_notice?: string;
  done_reason?: string;
  [key: string]: unknown;
};
export type Document = {
  id: number;
  filename: string;
  status: string;
  page_count?: number;
  warning_message?: string;
  error_message?: string;
};
export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  metrics?: Metrics;
  state?: "complete" | "failed" | "cancelled" | "generating";
};
export type Workspace = {
  id: string;
  title: string;
  documents: Document[];
  messages: Message[];
  updated: number;
};
export type JobPayload = {
  kind: "chat" | "summary";
  payload: Record<string, unknown>;
};
export type StreamEvent = {
  type: string;
  content?: string;
  message?: string;
  phase?: string;
  metrics?: Metrics;
  sources?: Source[];
  completed?: number;
  total?: number;
  [key: string]: unknown;
};
