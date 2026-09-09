import './LoadingState.css';

interface LoadingStateProps {
  label?: string;
  /** Show the slow-path hint used while a local model is generating. */
  hint?: string;
  compact?: boolean;
}

export function LoadingState({ label = 'Loading...', hint, compact }: LoadingStateProps) {
  return (
    <div className={compact ? 'loading loading-compact' : 'loading'} role="status">
      <span className="spinner" aria-hidden="true" />
      <span className="loading-label">{label}</span>
      {hint && <span className="loading-hint">{hint}</span>}
    </div>
  );
}

/** Grey placeholder blocks used while cards and tables load. */
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skeleton-group" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton-row" />
      ))}
    </div>
  );
}
