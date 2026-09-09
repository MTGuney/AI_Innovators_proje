import { useEffect, useState, type FormEvent } from 'react';
import { compareApi, type ComparisonResponse } from '../services';
import { describeError } from '../hooks/useAsync';
import { CompanySelector } from '../components/CompanySelector';
import { ComparisonPanel } from '../components/ComparisonPanel';
import { EmptyState, ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';

const METRICS = [
  'Revenue',
  'Operating income',
  'Net income',
  'Risk factors',
  'Research and development expense',
  'Gross margin',
];

export function ComparePage() {
  const [companies, setCompanies] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [metric, setMetric] = useState(METRICS[0]!);
  const [result, setResult] = useState<ComparisonResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    compareApi
      .companies()
      .then((names) => {
        setCompanies(names);
        // Pre-select two so the page is usable in one click.
        setSelected(names.slice(0, 2));
      })
      .catch((loadError) => setError(describeError(loadError)));
  }, []);

  const run = async (event: FormEvent) => {
    event.preventDefault();
    if (selected.length < 2 || busy) return;

    setBusy(true);
    setError(null);
    try {
      setResult(await compareApi.compare(selected, metric));
    } catch (compareError) {
      setError(describeError(compareError));
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div className="grow">
          <h1>Compare</h1>
          <p className="muted">
            Retrieve the same metric across companies. Facts are quoted from the
            reports; the summary is clearly labelled as generated.
          </p>
        </div>
      </header>

      <form className="card card-pad stack gap-16" onSubmit={run} style={{ marginBottom: 18 }}>
        <CompanySelector
          companies={companies}
          selected={selected}
          onChange={setSelected}
          max={4}
          label="Companies (choose 2-4)"
        />

        <div className="row gap-12 wrap" style={{ alignItems: 'flex-end' }}>
          <div className="field grow" style={{ minWidth: 240 }}>
            <label className="label" htmlFor="metric">
              Metric
            </label>
            <input
              id="metric"
              className="input"
              list="metric-options"
              value={metric}
              onChange={(event) => setMetric(event.target.value)}
              placeholder="e.g. Revenue"
              required
            />
            <datalist id="metric-options">
              {METRICS.map((option) => (
                <option key={option} value={option} />
              ))}
            </datalist>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy || selected.length < 2 || metric.trim().length < 2}
          >
            {busy ? 'Comparing...' : 'Compare'}
          </button>
        </div>

        {selected.length < 2 && companies.length > 0 && (
          <span className="subtle" style={{ fontSize: 12 }}>
            Select at least two companies.
          </span>
        )}
      </form>

      {error && <ErrorState message={error} />}

      {busy && (
        <LoadingState
          label={`Comparing ${selected.join(' and ')} on ${metric}...`}
          hint="Each company is searched separately so neither crowds the other out."
        />
      )}

      {result && !busy && <ComparisonPanel result={result} />}

      {!result && !busy && !error && (
        <div className="card">
          <EmptyState
            title="No comparison yet"
            description="Pick two or more companies and a metric, then run the comparison."
          />
        </div>
      )}
    </div>
  );
}
