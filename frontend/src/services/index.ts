/** Typed wrappers around the backend endpoints, grouped by feature. */

import { api, toQuery } from './apiClient';
import type {
  ChatRequestBody,
  ChatResponse,
  ComparisonResponse,
  ConversationDetailDto,
  ConversationSummaryDto,
  PagedResult,
  ReportDto,
  ReportFilters,
  SearchResponse,
} from './types';

export const reportsApi = {
  list: (filters: ReportFilters = {}, signal?: AbortSignal) =>
    api.get<PagedResult<ReportDto>>(
      `/reports${toQuery({
        search: filters.search,
        company: filters.company,
        year: filters.year,
        reportType: filters.reportType,
        page: filters.page ?? 1,
        pageSize: filters.pageSize ?? 20,
      })}`,
      signal,
    ),

  get: (id: string, signal?: AbortSignal) => api.get<ReportDto>(`/reports/${id}`, signal),

  remove: (id: string) => api.delete<void>(`/reports/${id}`),

  /** Import documents that were indexed directly by the AI service's CLI. */
  sync: () => api.post<{ imported: number }>('/reports/sync'),

  upload: (
    file: File,
    meta: { company?: string; year?: number; reportType?: string; title?: string },
  ) => {
    const form = new FormData();
    form.append('file', file);
    if (meta.company) form.append('company', meta.company);
    if (meta.year) form.append('year', String(meta.year));
    if (meta.reportType) form.append('reportType', meta.reportType);
    if (meta.title) form.append('title', meta.title);
    return api.upload<{ report: ReportDto }>('/reports/upload', form);
  },
};

export const chatApi = {
  ask: (body: ChatRequestBody, signal?: AbortSignal) =>
    api.post<ChatResponse>('/chat', body, signal),

  conversations: (signal?: AbortSignal) =>
    api.get<ConversationSummaryDto[]>('/conversations', signal),

  conversation: (id: string, signal?: AbortSignal) =>
    api.get<ConversationDetailDto>(`/conversations/${id}`, signal),

  removeConversation: (id: string) => api.delete<void>(`/conversations/${id}`),
};

export const searchApi = {
  search: (
    query: string,
    options: { topK?: number; company?: string; year?: number; reportType?: string } = {},
    signal?: AbortSignal,
  ) =>
    api.get<SearchResponse>(
      `/search${toQuery({
        q: query,
        topK: options.topK,
        company: options.company,
        year: options.year,
        reportType: options.reportType,
      })}`,
      signal,
    ),
};

export const compareApi = {
  companies: (signal?: AbortSignal) => api.get<string[]>('/compare/companies', signal),

  compare: (
    companies: string[],
    metric: string,
    years: number[] = [],
    signal?: AbortSignal,
  ) => api.post<ComparisonResponse>('/compare', { companies, metric, years }, signal),
};

export * from './types';
export { ApiError } from './apiClient';
