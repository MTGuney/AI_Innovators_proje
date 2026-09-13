/**
 * Types mirroring the backend's DTOs (backend/FinAi.Api/DTOs).
 * ASP.NET Core serialises camelCase, so these match field-for-field.
 */

export interface ReportDto {
  id: string;
  title: string;
  companyName: string;
  ticker: string | null;
  year: number | null;
  reportType: string;
  fileName: string;
  documentId: string | null;
  indexStatus: 'Pending' | 'Indexed' | 'Duplicate' | 'Failed';
  pageCount: number;
  chunkCount: number;
  fileSizeBytes: number;
  uploadedAt: string;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface SourceCitation {
  document: string;
  documentId: string;
  page: number | null;
  relevance: number;
  company: string | null;
  year: number | null;
  reportType: string | null;
  section: string | null;
  chunkId: string;
  excerpt: string;
}

export interface RetrievedChunk {
  chunkId: string;
  documentId: string;
  sourceFile: string;
  company: string | null;
  year: number | null;
  reportType: string | null;
  title: string | null;
  section: string | null;
  pageNumber: number | null;
  chunkIndex: number | null;
  relevance: number;
  text: string;
}

export type Confidence = 'high' | 'medium' | 'low';

export interface ChatResponse {
  conversationId: string;
  messageId: string;
  answer: string;
  keyPoints: string[];
  sources: SourceCitation[];
  retrievedChunks: RetrievedChunk[];
  confidence: Confidence;
  grounded: boolean;
  /** Figures the AI service could not find in the retrieved passages. */
  unsupportedFigures: string[];
  model: string;
  elapsedMs: number;
  createdAt: string;
}

export interface MessageDto {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  keyPoints: string[];
  sources: SourceCitation[];
  confidence: Confidence | null;
  grounded: boolean;
  unsupportedFigures: string[];
  elapsedMs: number | null;
  model: string | null;
  createdAt: string;
}

export interface ConversationSummaryDto {
  id: string;
  title: string;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationDetailDto {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: MessageDto[];
}

export interface SearchResponse {
  question: string;
  topK: number;
  similarityThreshold: number;
  totalCandidates: number;
  chunks: RetrievedChunk[];
}

export type FactKind = 'retrieved_fact' | 'ai_summary' | 'calculated_comparison';

export interface CompanyFindings {
  company: string;
  kind: FactKind;
  findings: string[];
  sources: SourceCitation[];
  hasData: boolean;
}

export interface ComparisonResponse {
  metric: string;
  companies: string[];
  years: number[];
  perCompany: CompanyFindings[];
  summary: string;
  summaryKind: FactKind;
  confidence: Confidence;
  unsupportedFigures: string[];
  model: string;
  elapsedMs: number;
}

export interface ChatRequestBody {
  question: string;
  conversationId?: string | null;
  companies?: string[];
  years?: number[];
  reportTypes?: string[];
  documentIds?: string[];
  topK?: number;
}

export interface ReportFilters {
  search?: string;
  company?: string;
  year?: number;
  reportType?: string;
  page?: number;
  pageSize?: number;
}
