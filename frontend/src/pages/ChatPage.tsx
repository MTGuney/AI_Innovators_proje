import { useCallback, useEffect, useState } from 'react';
import {
  chatApi,
  compareApi,
  type ConversationSummaryDto,
  type MessageDto,
  type RetrievedChunk,
} from '../services';
import { describeError } from '../hooks/useAsync';
import { ChatWindow } from '../components/ChatWindow';
import { CompanySelector } from '../components/CompanySelector';
import { formatDateTime } from '../utils/format';
import './ChatPage.css';

export function ChatPage() {
  const [conversations, setConversations] = useState<ConversationSummaryDto[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageDto[]>([]);
  const [chunksByMessage, setChunksByMessage] = useState<Record<string, RetrievedChunk[]>>({});

  // null until the lookup resolves, so an empty index and a failed request
  // are distinguishable -- only the former should block asking.
  const [companies, setCompanies] = useState<string[] | null>(null);
  const [selectedCompanies, setSelectedCompanies] = useState<string[]>([]);

  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await chatApi.conversations());
    } catch {
      // The sidebar is non-essential; a failure here must not block asking.
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
    compareApi
      .companies()
      .then(setCompanies)
      .catch(() => setCompanies(null));
  }, [refreshConversations]);

  const openConversation = async (id: string) => {
    setError(null);
    try {
      const detail = await chatApi.conversation(id);
      setActiveId(detail.id);
      setMessages(detail.messages);
      // Retrieval detail is only kept for answers produced in this session.
      setChunksByMessage({});
    } catch (loadError) {
      setError(describeError(loadError));
    }
  };

  const startNew = () => {
    setActiveId(null);
    setMessages([]);
    setChunksByMessage({});
    setError(null);
  };

  const send = async (question: string) => {
    setError(null);
    setPending(true);

    // Show the question immediately; the local model can take a while.
    const optimistic: MessageDto = {
      id: `pending-${Date.now()}`,
      role: 'user',
      content: question,
      keyPoints: [],
      sources: [],
      confidence: null,
      grounded: true,
      unsupportedFigures: [],
      elapsedMs: null,
      model: null,
      createdAt: new Date().toISOString(),
    };
    setMessages((previous) => [...previous, optimistic]);

    try {
      const response = await chatApi.ask({
        question,
        conversationId: activeId,
        companies: selectedCompanies.length > 0 ? selectedCompanies : undefined,
      });

      const answer: MessageDto = {
        id: response.messageId,
        role: 'assistant',
        content: response.answer,
        keyPoints: response.keyPoints,
        sources: response.sources,
        confidence: response.confidence,
        grounded: response.grounded,
        unsupportedFigures: response.unsupportedFigures,
        elapsedMs: response.elapsedMs,
        model: response.model,
        createdAt: response.createdAt,
      };

      setMessages((previous) => [...previous, answer]);
      setChunksByMessage((previous) => ({
        ...previous,
        [response.messageId]: response.retrievedChunks,
      }));
      setActiveId(response.conversationId);
      void refreshConversations();
    } catch (askError) {
      setError(describeError(askError));
      // Drop the optimistic question so it is not mistaken for a sent message.
      setMessages((previous) => previous.filter((message) => message.id !== optimistic.id));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="chat-page">
      <aside className="chat-side">
        <div className="chat-side-head">
          <span className="section-title">Conversations</span>
          <button type="button" className="btn btn-sm" onClick={startNew}>
            New
          </button>
        </div>

        <div className="chat-list scroll-y">
          {conversations.length === 0 ? (
            <p className="subtle" style={{ padding: '8px 4px', fontSize: 12 }}>
              No conversations yet.
            </p>
          ) : (
            conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                className={`chat-list-item ${activeId === conversation.id ? 'active' : ''}`}
                onClick={() => openConversation(conversation.id)}
              >
                <span className="chat-list-title">{conversation.title}</span>
                <span className="chat-list-meta">
                  {conversation.messageCount} messages · {formatDateTime(conversation.updatedAt)}
                </span>
              </button>
            ))
          )}
        </div>

        <div className="chat-side-filters">
          <CompanySelector
            companies={companies ?? []}
            selected={selectedCompanies}
            onChange={setSelectedCompanies}
            label="Restrict to"
            max={4}
          />
          <p className="subtle" style={{ fontSize: 11, margin: 0 }}>
            {selectedCompanies.length === 0
              ? 'Searching all indexed reports. Companies named in the question are detected automatically.'
              : `Retrieval is limited to ${selectedCompanies.join(', ')}.`}
          </p>
        </div>
      </aside>

      <section className="chat-main">
        <header className="chat-head">
          <div className="grow">
            <h1>AI Assistant</h1>
            <p className="muted">
              Grounded answers from the indexed reports, with every source shown.
            </p>
          </div>
        </header>

        <ChatWindow
          messages={messages}
          chunksByMessage={chunksByMessage}
          pending={pending}
          error={error}
          onSend={send}
          onDismissError={() => setError(null)}
          disabled={companies !== null && companies.length === 0}
        />
      </section>
    </div>
  );
}
