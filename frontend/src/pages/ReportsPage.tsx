import { useMemo, useState } from 'react';
import { reportsApi, type ReportDto, type ReportFilters } from '../services';
import { describeError, useAsync } from '../hooks/useAsync';
import { useDebounced } from '../hooks/useDebounced';
import { EmptyState, ErrorState } from '../components/ErrorState';
import { LoadingState } from '../components/LoadingState';
import { ReportCard } from '../components/ReportCard';
import { ReportFilter } from '../components/ReportFilter';
import { ReportTable } from '../components/ReportTable';
import { UploadModal } from '../components/UploadModal';
import './ReportsPage.css';

const PAGE_SIZE = 20;

export function ReportsPage() {
  const [filters, setFilters] = useState<ReportFilters>({ page: 1, pageSize: PAGE_SIZE });
  const [view, setView] = useState<'table' | 'grid'>('table');
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  // Typing must not fire one request per keystroke; the other filters are
  // discrete choices and can apply immediately.
  const debouncedSearch = useDebounced(filters.search ?? '', 350);

  const { data, loading, error, reload } = useAsync(
    (signal) => reportsApi.list({ ...filters, search: debouncedSearch }, signal),
    [debouncedSearch, filters.company, filters.year, filters.reportType, filters.page],
  );

  // Filter options are derived from the reports currently on screen.
  const { companies, years, reportTypes } = useMemo(() => {
    const items = data?.items ?? [];
    return {
      companies: [...new Set(items.map((r) => r.companyName))].sort(),
      years: [...new Set(items.map((r) => r.year).filter((y): y is number => y != null))]
        .sort((a, b) => b - a),
      reportTypes: [...new Set(items.map((r) => r.reportType))].sort(),
    };
  }, [data]);

  const remove = async (report: ReportDto) => {
    const confirmed = window.confirm(
      `Delete "${report.title}"? Its passages will also be removed from the index.`,
    );
    if (!confirmed) return;

    setDeletingId(report.id);
    setActionError(null);
    try {
      await reportsApi.remove(report.id);
      reload();
    } catch (deleteError) {
      setActionError(describeError(deleteError));
    } finally {
      setDeletingId(null);
    }
  };

  const sync = async () => {
    setSyncing(true);
    setActionError(null);
    try {
      const { imported } = await reportsApi.sync();
      if (imported === 0) {
        setActionError('No new documents were found in the index.');
      }
      reload();
    } catch (syncError) {
      setActionError(describeError(syncError));
    } finally {
      setSyncing(false);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / (filters.pageSize ?? PAGE_SIZE))) : 1;
  const page = filters.page ?? 1;

  return (
    <div className="page">
      <header className="page-head">
        <div className="grow">
          <h1>Reports</h1>
          <p className="muted">
            {data ? `${data.total} report(s) in the catalogue` : 'Loading catalogue...'}
          </p>
        </div>

        <div className="row gap-8">
          <div className="view-toggle">
            <button
              type="button"
              className={view === 'table' ? 'active' : ''}
              onClick={() => setView('table')}
            >
              Table
            </button>
            <button
              type="button"
              className={view === 'grid' ? 'active' : ''}
              onClick={() => setView('grid')}
            >
              Cards
            </button>
          </div>

          <button type="button" className="btn" onClick={sync} disabled={syncing}>
            {syncing ? 'Importing...' : 'Import indexed'}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setUploading(true)}>
            Upload report
          </button>
        </div>
      </header>

      <div className="card card-pad" style={{ marginBottom: 16 }}>
        <ReportFilter
          filters={filters}
          companies={companies}
          years={years}
          reportTypes={reportTypes}
          onChange={setFilters}
        />
      </div>

      {actionError && (
        <div style={{ marginBottom: 14 }}>
          <ErrorState message={actionError} onRetry={() => setActionError(null)} />
        </div>
      )}

      {loading && <LoadingState label="Loading reports..." />}
      {error && <ErrorState message={error} onRetry={reload} />}

      {data && !loading && (
        data.items.length === 0 ? (
          <div className="card">
            <EmptyState
              title="No reports match these filters"
              description="Clear the filters, upload a report, or import documents already present in the vector index."
            />
          </div>
        ) : (
          <>
            {view === 'table' ? (
              <div className="card">
                <ReportTable reports={data.items} onDelete={remove} busyId={deletingId} />
              </div>
            ) : (
              <div className="card-grid">
                {data.items.map((report) => (
                  <ReportCard key={report.id} report={report} />
                ))}
              </div>
            )}

            {totalPages > 1 && (
              <nav className="pager">
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={page <= 1}
                  onClick={() => setFilters({ ...filters, page: page - 1 })}
                >
                  Previous
                </button>
                <span className="subtle">
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={page >= totalPages}
                  onClick={() => setFilters({ ...filters, page: page + 1 })}
                >
                  Next
                </button>
              </nav>
            )}
          </>
        )
      )}

      {uploading && (
        <UploadModal onClose={() => setUploading(false)} onUploaded={reload} />
      )}
    </div>
  );
}
