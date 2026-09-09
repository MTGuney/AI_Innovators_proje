import { useState } from 'react';
import type { SourceCitation as Citation, RetrievedChunk } from '../services';
import { RelevanceMeter } from './Badges';
import './SourceCitation.css';

interface SourceCitationProps {
  citation: Citation;
  index: number;
  /** The full chunk behind the citation, when the answer carries it. */
  chunk?: RetrievedChunk;
}

/**
 * One citation under an answer. Collapsed it shows provenance (document, page,
 * section, relevance); expanded it reveals the exact retrieved passage, so a
 * user can check the claim against the source text without leaving the page.
 */
export function SourceCitationCard({ citation, index, chunk }: SourceCitationProps) {
  const [expanded, setExpanded] = useState(false);
  const passage = chunk?.text ?? citation.excerpt;

  return (
    <div className={`citation ${expanded ? 'citation-open' : ''}`}>
      <button
        type="button"
        className="citation-head"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
      >
        <span className="citation-tag mono">S{index}</span>

        <span className="citation-meta">
          <span className="citation-doc" title={citation.document}>
            {citation.document}
          </span>
          <span className="citation-sub">
            {[
              citation.company,
              citation.year ? String(citation.year) : null,
              citation.page ? `page ${citation.page}` : null,
              citation.section,
            ]
              .filter(Boolean)
              .join('  ·  ')}
          </span>
        </span>

        <RelevanceMeter relevance={citation.relevance} />
        <span className="citation-chevron" aria-hidden="true">
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="citation-body fade-in">
          <div className="citation-why">
            This passage was retrieved because it ranked among the closest matches to
            the question by semantic similarity.
          </div>
          <blockquote className="citation-quote">{passage}</blockquote>
          <div className="citation-ids mono subtle">{citation.chunkId}</div>
        </div>
      )}
    </div>
  );
}

/** The list of citations rendered under an assistant answer. */
export function SourceList({
  sources,
  chunks = [],
}: {
  sources: Citation[];
  chunks?: RetrievedChunk[];
}) {
  if (sources.length === 0) return null;

  const byId = new Map(chunks.map((chunk) => [chunk.chunkId, chunk]));

  return (
    <section className="citation-list">
      <h4 className="section-title">
        Sources ({sources.length})
      </h4>
      <div className="stack gap-8">
        {sources.map((citation, index) => (
          <SourceCitationCard
            key={citation.chunkId || index}
            citation={citation}
            index={index + 1}
            chunk={byId.get(citation.chunkId)}
          />
        ))}
      </div>
    </section>
  );
}
