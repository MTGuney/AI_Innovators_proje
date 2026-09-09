import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { reportsApi, searchApi } from '../services';
import { describeError, useAsync } from '../hooks/useAsync';
import { EmptyState, ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { IndexStatusBadge, RelevanceMeter } from '../components/Badges';
import { formatBytes, formatDateTime, formatNumber } from '../utils/format';
import './ReportDetailPage.css';

export function ReportDetailPage() {
  const { id = '' } = useParams();
  const { data: report, loading, error, reload } = useAsync(
    (signal) => reportsApi.get(id, signal),
    [id],
  );

  if (loading) return <div className="page"><LoadingState /></div>;
  if (error) return <div className="page"><ErrorState message={error} onRetry={reload} /></div>;
  if (!report) return null;

  return (
    <div className="page">
      <header className="page-head">
        <div className="grow">
          <Link to="/reports" className="back-link">
            ← Back to reports
          </Link>
          <h1 style={{ marginTop: 6 }}>{report.title}</h1>
          <p className="muted">
            {report.companyName}
            {report.ticker && <span className="mono"> · {report.ticker}</span>}
          </p>
        </div>
        <IndexStatusBadge status={report.indexStatus} />
      </header>

      <section className="card card-pad" style={{ marginBottom: 18 }}>
        <h2>Metadata</h2>
        <dl className="meta-grid">
          <Meta label="Company" value={report.companyName} />
          <Meta label="Fiscal year" value={report.year?.toString() ?? '--'} />
          <Meta label="Report type" value={report.reportType} />
          <Meta label="File name" value={report.fileName} mono />
          <Meta label="Pages" value={formatNumber(report.pageCount)} />
          <Meta label="Indexed passages" value={formatNumber(report.chunkCount)} />
          <Meta label="File size" value={formatBytes(report.fileSizeBytes)} />
          <Meta label="Uploaded" value={formatDateTime(report.uploadedAt)} />
          <Meta label="Document id" value={report.documentId ?? '--'} mono />
        </dl>
      </section>

      <PassageExplorer
        company={report.companyName}
        year={report.year ?? undefined}
      />
    </div>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={mono ? 'mono' : undefined}>{value}</dd>
    </div>
  );
}

/**
 * Search within this report's company/year. Lets a user see exactly which
 * passages retrieval would surface, without generating an answer.
 */
function PassageExplorer({ company, year }: { company: string; year?: number }) {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Awaited<ReturnType<typeof searchApi.search>> | null>(null);

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed.length < 3 || busy) return;

    setBusy(true);
    setError(null);
    setSubmitted(trimmed);
    try {
      setResults(await searchApi.search(trimmed, { company, year, topK: 8 }));
    } catch (searchError) {
      setError(describeError(searchError));
      setResults(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card card-pad">
      <h2>Explore passages</h2>
      <p className="muted" style={{ marginTop: 4 }}>
        Semantic search across this report only. No answer is generated — this is
        the raw retrieval step.
      </p>

      <form className="row gap-8" onSubmit={run} style={{ margin: '14px 0' }}>
        <input
          className="input grow"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="e.g. revenue growth drivers, supply chain risk..."
        />
        <button type="submit" className="btn btn-primary" disabled={busy || query.trim().length < 3}>
          {busy ? 'Searching...' : 'Search'}
        </button>
      </form>

      {error && <ErrorState message={error} />}
      {busy && <LoadingState label="Searching passages..." compact />}

      {results && !busy && (
        results.chunks.length === 0 ? (
          <EmptyState
            title="No sufficiently relevant passages"
            description={`Nothing in this report passed the similarity threshold for "${submitted}".`}
          />
        ) : (
          <div className="stack gap-10">
            <span className="subtle" style={{ fontSize: 12 }}>
              {results.chunks.length} of {results.totalCandidates} candidates passed the{' '}
              {Math.round(results.similarityThreshold * 100)}% similarity threshold.
            </span>
            {results.chunks.map((chunk) => (
              <article key={chunk.chunkId} className="passage">
                <div className="row gap-8 wrap">
                  {chunk.pageNumber && (
                    <span className="badge badge-neutral">page {chunk.pageNumber}</span>
                  )}
                  {chunk.section && <span className="passage-section">{chunk.section}</span>}
                  <span className="spacer" />
                  <RelevanceMeter relevance={chunk.relevance} />
                </div>
                <p className="passage-text">{chunk.text}</p>
              </article>
            ))}
          </div>
        )
      )}
    </section>
  );
}
