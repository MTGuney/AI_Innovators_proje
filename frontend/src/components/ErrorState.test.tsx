import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { EmptyState, ErrorState } from './ErrorState';
import { LoadingState, Skeleton } from './LoadingState';

describe('ErrorState', () => {
  it('announces the failure to assistive technology', () => {
    render(<ErrorState message="Something failed." />);

    expect(screen.getByRole('alert')).toHaveTextContent('Something failed.');
  });

  it('shows actionable guidance alongside the message', () => {
    render(
      <ErrorState
        message="AI service is currently unavailable."
        hint="Start Foundry Local, then reload."
      />,
    );

    expect(screen.getByText('Start Foundry Local, then reload.')).toBeInTheDocument();
  });

  it('retries on demand', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorState message="Failed." onRetry={onRetry} />);

    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('omits the retry control when no handler is given', () => {
    render(<ErrorState message="Failed." />);

    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });
});

describe('LoadingState', () => {
  it('exposes progress as a status region', () => {
    render(<LoadingState label="Loading reports..." />);

    expect(screen.getByRole('status')).toHaveTextContent('Loading reports...');
  });

  it('renders skeleton placeholders', () => {
    const { container } = render(<Skeleton rows={4} />);

    expect(container.querySelectorAll('.skeleton-row')).toHaveLength(4);
  });
});

describe('EmptyState', () => {
  it('explains what to do next', () => {
    render(
      <EmptyState
        title="No reports indexed yet"
        description="Upload a report to get started."
      />,
    );

    expect(screen.getByText('No reports indexed yet')).toBeInTheDocument();
    expect(screen.getByText('Upload a report to get started.')).toBeInTheDocument();
  });
});
