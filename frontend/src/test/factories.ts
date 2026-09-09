import type { MessageDto, RetrievedChunk, SourceCitation } from '../services';

export function makeCitation(overrides: Partial<SourceCitation> = {}): SourceCitation {
  return {
    document: 'Apple Annual Report 2024',
    documentId: 'apple-2024',
    page: 32,
    relevance: 0.91,
    company: 'Apple Inc',
    year: 2024,
    reportType: '10-K',
    section: 'Item 7. MD&A',
    chunkId: 'apple-2024::p32::c4',
    excerpt: 'Total revenue was $4,820 million, an increase of 12.4%.',
    ...overrides,
  };
}

export function makeChunk(overrides: Partial<RetrievedChunk> = {}): RetrievedChunk {
  return {
    chunkId: 'apple-2024::p32::c4',
    documentId: 'apple-2024',
    sourceFile: 'AAPL_Apple-Inc_10-K_2024.txt',
    company: 'Apple Inc',
    year: 2024,
    reportType: '10-K',
    title: 'Apple Annual Report 2024',
    section: 'Item 7. MD&A',
    pageNumber: 32,
    chunkIndex: 4,
    relevance: 0.91,
    text: 'Total revenue was $4,820 million, an increase of 12.4% over fiscal 2023.',
    ...overrides,
  };
}

export function makeAssistantMessage(overrides: Partial<MessageDto> = {}): MessageDto {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: 'Revenue increased by 12.4% [S1].',
    keyPoints: ['Total revenue was $4,820 million [S1]'],
    sources: [makeCitation()],
    confidence: 'high',
    grounded: true,
    unsupportedFigures: [],
    elapsedMs: 5200,
    model: 'qwen2.5-1.5b',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

export function makeUserMessage(content = 'Did revenue increase?'): MessageDto {
  return {
    id: 'msg-0',
    role: 'user',
    content,
    keyPoints: [],
    sources: [],
    confidence: null,
    grounded: true,
    unsupportedFigures: [],
    elapsedMs: null,
    model: null,
    createdAt: new Date().toISOString(),
  };
}
