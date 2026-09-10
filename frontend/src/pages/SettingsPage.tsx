import { indexApi } from '../services';
import { useAsync } from '../hooks/useAsync';
import { ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';

/**
 * Read-only view of how the system is wired. Tuning values (TOP_K, chunk size,
 * models) are deployment configuration and live in `.env`, not in the UI.
 */
export function SettingsPage() {
  const { data, loading, error, reload } = useAsync((signal) => indexApi.status(signal));

  return (
    <div className="page">
      <header className="page-head">
        <div className="grow">
          <h1>Pipeline</h1>
          <p className="muted">The retrieval index and the services behind it.</p>
        </div>
      </header>

      <section className="card card-pad">
        <h2>Retrieval index</h2>

        {loading && <LoadingState label="Checking services..." compact />}
        {error && <ErrorState message={error} onRetry={reload} />}

        {data && (
          <>
            <div className="row gap-8" style={{ margin: '12px 0' }}>
              <span
                className={`badge ${data.aiServiceHealthy ? 'badge-success' : 'badge-danger'}`}
              >
                {data.aiServiceHealthy ? 'Healthy' : 'Unavailable'}
              </span>
              <span className="subtle">{data.aiServiceDetail}</span>
            </div>

            <dl className="meta-grid">
              <div>
                <dt>Indexed documents</dt>
                <dd>{data.indexedDocuments}</dd>
              </div>
              <div>
                <dt>Indexed passages</dt>
                <dd>{data.indexedChunks}</dd>
              </div>
            </dl>

            {!data.aiServiceHealthy && (
              <div style={{ marginTop: 14 }}>
                <ErrorState
                  variant="warning"
                  message="Questions cannot be answered while the AI service is down."
                  hint="Start Foundry Local (`foundry server start`), load the configured models, then start the Python service."
                />
              </div>
            )}
          </>
        )}
      </section>

      <section className="card card-pad" style={{ marginTop: 18 }}>
        <h2>How answers are produced</h2>
        <ol className="muted" style={{ paddingLeft: 18, marginTop: 10, lineHeight: 1.75 }}>
          <li>The question is embedded locally into a vector.</li>
          <li>ChromaDB returns the closest report passages by cosine similarity.</li>
          <li>Passages below the similarity threshold are discarded.</li>
          <li>The surviving passages become the model's only context.</li>
          <li>Foundry Local generates a grounded answer and cites the passages used.</li>
        </ol>
        <p className="subtle" style={{ fontSize: 12 }}>
          Retrieval and generation settings (TOP_K, chunk size and overlap,
          similarity threshold, model names) are deployment configuration and are
          set in the project's <span className="mono">.env</span> file.
        </p>
      </section>
    </div>
  );
}
