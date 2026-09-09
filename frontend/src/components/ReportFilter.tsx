import type { ReportFilters } from '../services';
import './ReportFilter.css';

interface ReportFilterProps {
  filters: ReportFilters;
  companies: string[];
  years: number[];
  reportTypes: string[];
  onChange: (next: ReportFilters) => void;
}

/** Search and metadata filters for the report catalogue. */
export function ReportFilter({
  filters,
  companies,
  years,
  reportTypes,
  onChange,
}: ReportFilterProps) {
  // Any filter change resets to page 1, or the user can land on an empty page.
  const update = (patch: Partial<ReportFilters>) =>
    onChange({ ...filters, ...patch, page: 1 });

  const isFiltered =
    Boolean(filters.search || filters.company || filters.year || filters.reportType);

  return (
    <div className="filter-bar">
      <input
        className="input filter-search"
        type="search"
        placeholder="Search reports by title, file or company..."
        value={filters.search ?? ''}
        onChange={(event) => update({ search: event.target.value })}
        aria-label="Search reports"
      />

      <select
        className="select filter-select"
        value={filters.company ?? ''}
        onChange={(event) => update({ company: event.target.value || undefined })}
        aria-label="Filter by company"
      >
        <option value="">All companies</option>
        {companies.map((company) => (
          <option key={company} value={company}>
            {company}
          </option>
        ))}
      </select>

      <select
        className="select filter-select"
        value={filters.year ?? ''}
        onChange={(event) =>
          update({ year: event.target.value ? Number(event.target.value) : undefined })
        }
        aria-label="Filter by year"
      >
        <option value="">All years</option>
        {years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>

      <select
        className="select filter-select"
        value={filters.reportType ?? ''}
        onChange={(event) => update({ reportType: event.target.value || undefined })}
        aria-label="Filter by report type"
      >
        <option value="">All types</option>
        {reportTypes.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>

      {isFiltered && (
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          onClick={() => onChange({ page: 1, pageSize: filters.pageSize })}
        >
          Clear
        </button>
      )}
    </div>
  );
}
