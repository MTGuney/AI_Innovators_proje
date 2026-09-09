import './ErrorState.css';

interface ErrorStateProps {
  message: string;
  /** Extra guidance, e.g. how to start Foundry Local. */
  hint?: string;
  onRetry?: () => void;
  variant?: 'error' | 'warning';
}

export function ErrorState({ message, hint, onRetry, variant = 'error' }: ErrorStateProps) {
  return (
    <div className={`state-panel state-${variant}`} role="alert">
      <div className="state-icon" aria-hidden="true">
        {variant === 'error' ? '!' : 'i'}
      </div>
      <div className="stack gap-4 grow">
        <strong className="state-message">{message}</strong>
        {hint && <span className="state-hint">{hint}</span>}
      </div>
      {onRetry && (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty">
      <div className="stack gap-8" style={{ alignItems: 'center' }}>
        <strong>{title}</strong>
        {description && (
          <span className="subtle" style={{ maxWidth: 420 }}>
            {description}
          </span>
        )}
        {action}
      </div>
    </div>
  );
}
