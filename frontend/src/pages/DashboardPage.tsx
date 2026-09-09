import { Link } from 'react-router-dom';
import { dashboardApi } from '../services';
import { useAsync } from '../hooks/useAsync';
import { EmptyState, ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { ReportCard } from '../components/ReportCard';
import { formatNumber } from '../utils/format';
import './DashboardPage.css';

export function DashboardPage() {
  const { data, loading, error, reload } = useAsync((signal) => dashboardApi.stats(signal));

  if (loading) return <div className="page"><LoadingState label="Loading dashboard..." /></div>;
  if (error) return <div className="page"><ErrorState message={error} onRetry={reload} /></div>;
  if (!data) return null;

  const years = Object.entries(data.reportsByYear);
  const peakYear = Math.max(1, ...years.map(([, count]) => count));

  return (
    <div className="page">
      <header className="page-head">
        <div className="grow">
          <h1>Dashboard</h1>
          <p className="muted">
            Corpus overview. The assistant answers only from these indexed reports.
          </p>
        </div>
        <Link to="/chat" className="btn btn-primary">
          Ask a question
        </Link>
      </header>

      {!data.aiServiceHealthy && (
        <div style={{ marginBottom: 18 }}>
          <ErrorState
            variant="warning"
            message="The AI service is unavailable, so questions cannot be answered right now."
            hint={
              data.aiServiceDetail ??
              'Start Foundry Local and the Python RAG service, then reload.'
            }
            onRetry={reload}
          />
        </div>
      )}

      <section className="stat-grid">
        <StatTile label="Companies" value={data.totalCompanies} />
        <StatTile label="Reports" value={data.totalReports} />
        <StatTile
          label="Indexed documents"
          value={data.indexedDocuments}
          hint="Documents present in the vector index"
        />
        <StatTile
          label="Indexed passages"
          value={data.indexedChunks}
          hint="Searchable chunks across all reports"
        />
      </section>

      <div className="dash-grid">
        <section className="card card-pad">
          <h2>Reports by year</h2>
          {years.length === 0 ? (
            <p className="muted">No reports yet.</p>
          ) : (
            <div className="year-chart">
              {years.map(([year, count]) => (
                <div key={year} className="year-bar">
                  <div className="year-track">
                    <div
                      className="year-fill"
                      style={{ height: `${(count / peakYear) * 100}%` }}
                      title={`${count} report(s)`}
                    />
                  </div>
                  <span className="year-count">{count}</span>
                  <span className="year-label">{year}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="card card-pad">
          <h2>Most queried companies</h2>
          {data.mostQueriedCompanies.length === 0 ? (
            <p className="muted">
              No questions asked yet. Usage builds up as you use the assistant.
            </p>
          ) : (
            <ol className="query-list">
              {data.mostQueriedCompanies.map((entry) => (
                <li key={entry.company}>
                  <span className="grow">{entry.company}</span>
                  <span className="badge badge-neutral">
                    {formatNumber(entry.queryCount)}
                  </span>
                </li>
              ))}
            </ol>
          )}

          <h3 style={{ marginTop: 18 }}>Report categories</h3>
          <div className="row gap-8 wrap" style={{ marginTop: 8 }}>
            {data.reportTypes.length === 0 ? (
              <span className="muted">None yet.</span>
            ) : (
              data.reportTypes.map((type) => (
                <span key={type} className="badge badge-accent">
                  {type}
                </span>
              ))
            )}
          </div>
        </section>
      </div>

      <section style={{ marginTop: 20 }}>
        <div className="row gap-8" style={{ marginBottom: 12 }}>
          <h2>Recent uploads</h2>
          <span className="spacer" />
          <Link to="/reports">Browse all reports</Link>
        </div>

        {data.recentUploads.length === 0 ? (
          <div className="card">
            <EmptyState
              title="No reports indexed yet"
              description="Upload a report, or run the ingestion script to load SEC filings."
              action={
                <Link to="/reports" className="btn btn-primary">
                  Go to reports
                </Link>
              }
            />
          </div>
        ) : (
          <div className="card-grid">
            {data.recentUploads.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  return (
    <div className="card stat-tile" title={hint}>
      <span className="stat-value">{formatNumber(value)}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}
