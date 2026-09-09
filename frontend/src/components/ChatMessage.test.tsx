import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ChatMessage } from './ChatMessage';
import { makeAssistantMessage, makeChunk, makeUserMessage } from '../test/factories';

describe('ChatMessage', () => {
  it('renders the user question', () => {
    render(<ChatMessage message={makeUserMessage('What were the risk factors?')} />);

    expect(screen.getByText('What were the risk factors?')).toBeInTheDocument();
  });

  it('renders the answer, key points and confidence', () => {
    render(<ChatMessage message={makeAssistantMessage()} />);

    expect(screen.getByText(/Revenue increased by/)).toBeInTheDocument();
    expect(screen.getByText(/Total revenue was \$4,820 million/)).toBeInTheDocument();
    expect(screen.getByText(/high confidence/)).toBeInTheDocument();
    expect(screen.getByText('qwen2.5-1.5b')).toBeInTheDocument();
  });

  it('shows source provenance: document, page and section', () => {
    render(<ChatMessage message={makeAssistantMessage()} />);

    expect(screen.getByText('Sources (1)')).toBeInTheDocument();
    expect(screen.getByText('Apple Annual Report 2024')).toBeInTheDocument();
    expect(screen.getByText(/page 32/)).toBeInTheDocument();
    expect(screen.getByText(/Item 7\. MD&A/)).toBeInTheDocument();
  });

  it('reveals the retrieved passage when a citation is expanded', async () => {
    const user = userEvent.setup();
    render(
      <ChatMessage message={makeAssistantMessage()} retrievedChunks={[makeChunk()]} />,
    );

    // Collapsed by default: the full passage is not in the DOM.
    expect(screen.queryByText(/increase of 12\.4% over fiscal 2023/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Apple Annual Report 2024/ }));

    expect(screen.getByText(/increase of 12\.4% over fiscal 2023/)).toBeInTheDocument();
    expect(screen.getByText(/ranked among the closest matches/)).toBeInTheDocument();
  });

  it('exposes every retrieved passage, not only the cited ones', async () => {
    const user = userEvent.setup();
    const chunks = [makeChunk(), makeChunk({ chunkId: 'other::p1::c0', text: 'Uncited passage.' })];

    render(<ChatMessage message={makeAssistantMessage()} retrievedChunks={chunks} />);

    await user.click(screen.getByRole('button', { name: /2 passages considered/ }));

    expect(screen.getByText('Uncited passage.')).toBeInTheDocument();
  });

  it('warns when an answer is not grounded in any passage', () => {
    render(
      <ChatMessage
        message={makeAssistantMessage({
          grounded: false,
          sources: [],
          content: 'No sufficiently relevant information was found.',
        })}
      />,
    );

    expect(screen.getByText(/not an answer from the reports/)).toBeInTheDocument();
    expect(screen.queryByText(/^Sources/)).not.toBeInTheDocument();
  });

  it('highlights inline citation tags', () => {
    render(<ChatMessage message={makeAssistantMessage()} />);

    // "[S1]" is rendered as a tag chip so a claim visibly points at a source.
    expect(screen.getAllByText('S1').length).toBeGreaterThan(0);
  });
});

describe('ChatMessage numeric grounding', () => {
  it('warns about figures that are not in the retrieved passages', () => {
    render(
      <ChatMessage
        message={makeAssistantMessage({
          content: 'Revenue was $245.5 billion.',
          unsupportedFigures: ['245.5'],
          confidence: 'low',
        })}
      />,
    );

    expect(screen.getByText(/Check these figures against the sources/)).toBeInTheDocument();
    expect(screen.getByText('245.5')).toBeInTheDocument();
  });

  it('stays quiet when every figure is grounded', () => {
    render(<ChatMessage message={makeAssistantMessage()} />);

    expect(
      screen.queryByText(/Check these figures against the sources/),
    ).not.toBeInTheDocument();
  });
});
