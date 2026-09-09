import type { ComparisonResponse } from '../services';
import { formatDuration } from '../utils/format';
import { ConfidenceBadge, FactKindBadge } from './Badges';
import { SourceList } from './SourceCitation';
import './ComparisonPanel.css';

/**
 * Renders a comparison with its provenance made explicit: verbatim retrieved
 * facts sit in their own column per company, and the model's summary is
 * clearly labelled as generated rather than quoted.
 */
export function ComparisonPanel({ result }: { result: ComparisonResponse }) {
  return (
    <div className="comparison stack gap-16">
      <section className="card card-pad">
        <div className="row gap-8 wrap">
          <h2>AI summary</h2>
          <FactKindBadge kind={result.summaryKind} />
          <span className="spacer" />
          <ConfidenceBadge confidence={result.confidence} />
          <span className="subtle mono">{result.model}</span>
          <span className="subtle">{formatDuration(result.elapsedMs)}</span>
        </div>

        <p className="comparison-summary">{result.summary}</p>

        <p className="comparison-caveat subtle">
          Figures are only reproduced from the retrieved excerpts below. Nothing
          here is investment advice.
        </p>
      </section>

      <div className="comparison-grid">
        {result.perCompany.map((entry) => (
          <section key={entry.company} className="card card-pad stack gap-12">
            <div className="row gap-8 wrap">
              <h3>{entry.company}</h3>
              <span className="spacer" />
              <FactKindBadge kind={entry.kind} />
            </div>

            {!entry.hasData ? (
              <p className="muted">
                No relevant passages were found for this company on
                “{result.metric}”. Index a report for it, or try a different metric.
              </p>
            ) : (
              <>
                {entry.findings.length > 0 ? (
                  <ul className="comparison-facts">
                    {entry.findings.map((finding, index) => (
                      <li key={index}>{finding}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">
                    Passages were retrieved, but none stated a figure directly.
                  </p>
                )}

                <SourceList sources={entry.sources} />
              </>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
