import { useState } from 'react';
import type { MessageDto, RetrievedChunk } from '../services';
import { formatDuration } from '../utils/format';
import { ConfidenceBadge, RelevanceMeter } from './Badges';
import { SourceList } from './SourceCitation';
import './ChatMessage.css';

interface ChatMessageProps {
  message: MessageDto;
  /** Chunks retrieval considered, available for the newest answer. */
  retrievedChunks?: RetrievedChunk[];
}

export function ChatMessage({ message, retrievedChunks = [] }: ChatMessageProps) {
  if (message.role === 'user') {
    return (
      <div className="msg msg-user fade-in">
        <div className="msg-bubble">{message.content}</div>
      </div>
    );
  }

  return (
    <article className="msg msg-assistant fade-in">
      <div className="msg-body card card-pad">
        {!message.grounded && (
          <div className="msg-ungrounded">
            No supporting passages were found, so this is not an answer from the reports.
          </div>
        )}

        {message.unsupportedFigures.length > 0 && (
          <div className="msg-unverified">
            <strong>Check these figures against the sources.</strong> The
            following did not appear verbatim in the retrieved passages:{' '}
            <span className="mono">{message.unsupportedFigures.join(', ')}</span>.
            They may be restated units, or the model may have introduced them.
          </div>
        )}

        <div className="msg-answer">{renderWithTags(message.content)}</div>

        {message.keyPoints.length > 0 && (
          <section className="msg-points">
            <h4 className="section-title">Key points</h4>
            <ul>
              {message.keyPoints.map((point, index) => (
                <li key={index}>{renderWithTags(point)}</li>
              ))}
            </ul>
          </section>
        )}

        <SourceList sources={message.sources} chunks={retrievedChunks} />

        {retrievedChunks.length > 0 && (
          <RetrievalTrace chunks={retrievedChunks} />
        )}

        <footer className="msg-footer">
          <ConfidenceBadge confidence={message.confidence} />
          {message.model && <span className="mono subtle">{message.model}</span>}
          {message.elapsedMs != null && (
            <span className="subtle">{formatDuration(message.elapsedMs)}</span>
          )}
        </footer>
      </div>
    </article>
  );
}

/**
 * Everything retrieval selected, including passages the model may not have
 * cited. Keeping this visible is what makes the pipeline inspectable rather
 * than a black box.
 */
function RetrievalTrace({ chunks }: { chunks: RetrievedChunk[] }) {
  const [open, setOpen] = useState(false);

  return (
    <section className="trace">
      <button type="button" className="trace-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? 'Hide' : 'Show'} retrieval details ({chunks.length} passages considered)
      </button>

      {open && (
        <div className="trace-body fade-in">
          {chunks.map((chunk) => (
            <div key={chunk.chunkId} className="trace-item">
              <div className="row gap-8 wrap">
                <strong className="trace-title">
                  {chunk.title ?? chunk.sourceFile}
                </strong>
                <span className="subtle">
                  {[chunk.company, chunk.year, chunk.pageNumber ? `p.${chunk.pageNumber}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
                <span className="spacer" />
                <RelevanceMeter relevance={chunk.relevance} />
              </div>
              {chunk.section && <div className="trace-section">{chunk.section}</div>}
              <p className="trace-text">{chunk.text}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Highlight inline [S1] citation tags so a claim visibly points at a source.
 */
function renderWithTags(text: string) {
  const parts = text.split(/(\[S\d+\])/gi);
  return parts.map((part, index) =>
    /^\[S\d+\]$/i.test(part) ? (
      <span key={index} className="inline-tag mono">
        {part.replace(/[[\]]/g, '')}
      </span>
    ) : (
      <span key={index}>{part}</span>
    ),
  );
}
