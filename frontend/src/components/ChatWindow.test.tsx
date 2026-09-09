import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChatWindow } from './ChatWindow';
import { makeAssistantMessage, makeUserMessage } from '../test/factories';

const baseProps = {
  messages: [],
  chunksByMessage: {},
  pending: false,
  error: null,
  onSend: vi.fn(),
  onDismissError: vi.fn(),
};

describe('ChatWindow', () => {
  it('offers starter questions when the conversation is empty', () => {
    render(<ChatWindow {...baseProps} />);

    expect(screen.getByText(/Ask a question about the indexed reports/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /What are the main risk factors/ }),
    ).toBeInTheDocument();
  });

  it('sends a typed question', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatWindow {...baseProps} onSend={onSend} />);

    await user.type(screen.getByRole('textbox'), 'Did revenue increase?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(onSend).toHaveBeenCalledWith('Did revenue increase?');
  });

  it('sends a starter question in one click', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatWindow {...baseProps} onSend={onSend} />);

    await user.click(screen.getByRole('button', { name: /What are the main risk factors/ }));

    expect(onSend).toHaveBeenCalledWith('What are the main risk factors mentioned in the report?');
  });

  it('refuses to send a question that is too short', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<ChatWindow {...baseProps} onSend={onSend} />);

    await user.type(screen.getByRole('textbox'), 'ab');

    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it('shows a loading state that sets expectations about local inference', () => {
    render(
      <ChatWindow {...baseProps} messages={[makeUserMessage()]} pending />,
    );

    expect(screen.getByText(/Searching the reports/)).toBeInTheDocument();
    expect(screen.getByText(/model runs locally/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Thinking...' })).toBeDisabled();
  });

  it('surfaces errors without losing the conversation', () => {
    render(
      <ChatWindow
        {...baseProps}
        messages={[makeUserMessage(), makeAssistantMessage()]}
        error="AI service is currently unavailable."
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      'AI service is currently unavailable.',
    );
    expect(screen.getByText(/Revenue increased by/)).toBeInTheDocument();
  });

  it('blocks input when there is nothing indexed', () => {
    render(<ChatWindow {...baseProps} disabled />);

    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.getByPlaceholderText(/Index some reports/)).toBeInTheDocument();
  });
});
