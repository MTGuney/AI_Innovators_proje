import type { Confidence, FactKind } from '../services';
import { formatRelevance } from '../utils/format';
import './Badges.css';

/**
 * How sure the assistant is that the retrieved excerpts answer the question.
 * Shown next to every answer so the user can calibrate their trust.
 */
export function ConfidenceBadge({ confidence }: { confidence: Confidence | null }) {
  if (!confidence) return null;

  const variant =
    confidence === 'high' ? 'success' : confidence === 'medium' ? 'warning' : 'neutral';

  return (
    <span className={`badge badge-${variant}`} title={CONFIDENCE_HELP[confidence]}>
      {confidence} confidence
    </span>
  );
}

const CONFIDENCE_HELP: Record<Confidence, string> = {
  high: 'The retrieved excerpts state this directly.',
  medium: 'The answer was pieced together from several excerpts.',
  low: 'The excerpts are only loosely related -- verify against the source.',
};

export function IndexStatusBadge({ status }: { status: string }) {
  const variant =
    status === 'Indexed'
      ? 'success'
      : status === 'Failed'
        ? 'danger'
        : status === 'Duplicate'
          ? 'accent'
          : 'neutral';

  return <span className={`badge badge-${variant}`}>{status}</span>;
}

/**
 * Labels which kind of statement the user is reading. The specification
 * requires retrieved facts, AI summaries and calculations to be distinguishable.
 */
export function FactKindBadge({ kind }: { kind: FactKind }) {
  const label: Record<FactKind, string> = {
    retrieved_fact: 'Retrieved fact',
    ai_summary: 'AI summary',
    calculated_comparison: 'Calculated',
  };

  const variant: Record<FactKind, string> = {
    retrieved_fact: 'success',
    ai_summary: 'accent',
    calculated_comparison: 'warning',
  };

  return <span className={`badge badge-${variant[kind]}`}>{label[kind]}</span>;
}

/** A compact bar making retrieval scores comparable at a glance. */
export function RelevanceMeter({ relevance }: { relevance: number }) {
  const percent = Math.max(0, Math.min(100, relevance * 100));
  const strength = percent >= 50 ? 'strong' : percent >= 30 ? 'medium' : 'weak';

  return (
    <span
      className="relevance"
      title={`Cosine similarity between the question and this passage: ${formatRelevance(relevance)}`}
    >
      <span className="relevance-track">
        <span className={`relevance-fill relevance-${strength}`} style={{ width: `${percent}%` }} />
      </span>
      <span className="relevance-value mono">{formatRelevance(relevance)}</span>
    </span>
  );
}
