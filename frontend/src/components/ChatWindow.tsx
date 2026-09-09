import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import type { MessageDto, RetrievedChunk } from '../services';
import { ChatMessage } from './ChatMessage';
import { EmptyState, ErrorState } from './ErrorState';
import { LoadingState } from './LoadingState';
import './ChatWindow.css';

interface ChatWindowProps {
  messages: MessageDto[];
  /** Retrieval detail for the most recent answer, keyed by message id. */
  chunksByMessage: Record<string, RetrievedChunk[]>;
  pending: boolean;
  error: string | null;
  onSend: (question: string) => void;
  onDismissError: () => void;
  disabled?: boolean;
}

const SUGGESTIONS = [
  'What were the main revenue sources?',
  'What are the main risk factors mentioned in the report?',
  'How did operating income change compared with the previous year?',
  "Compare Apple's revenue growth with Microsoft's.",
];

export function ChatWindow({
  messages,
  chunksByMessage,
  pending,
  error,
  onSend,
  onDismissError,
  disabled,
}: ChatWindowProps) {
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Follow the conversation as it grows, including while an answer streams in.
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages.length, pending]);

  const submit = (question: string) => {
    const trimmed = question.trim();
    if (trimmed.length < 3 || pending || disabled) return;
    onSend(trimmed);
    setDraft('');
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(draft);
  };

  // Enter sends, Shift+Enter inserts a newline.
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit(draft);
    }
  };

  return (
    <div className="chat">
      <div className="chat-scroll scroll-y" ref={scrollRef}>
        {messages.length === 0 && !pending ? (
          <div className="chat-welcome">
            <EmptyState
              title="Ask a question about the indexed reports"
              description="Answers are generated locally and always cite the passages they came from."
            />
            <div className="chat-suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="suggestion"
                  onClick={() => submit(suggestion)}
                  disabled={disabled}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-messages">
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                retrievedChunks={chunksByMessage[message.id]}
              />
            ))}

            {pending && (
              <LoadingState
                label="Searching the reports and generating an answer..."
                hint="The model runs locally, so this can take up to a minute."
              />
            )}
          </div>
        )}

        {error && (
          <div className="chat-error">
            <ErrorState message={error} onRetry={onDismissError} />
          </div>
        )}
      </div>

      <form className="chat-composer" onSubmit={handleSubmit}>
        <textarea
          className="textarea"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            disabled
              ? 'Index some reports before asking questions.'
              : 'Ask about revenue, risk factors, operating income, or compare two companies...'
          }
          rows={2}
          maxLength={2000}
          disabled={disabled || pending}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={disabled || pending || draft.trim().length < 3}
        >
          {pending ? 'Thinking...' : 'Ask'}
        </button>
      </form>
    </div>
  );
}
