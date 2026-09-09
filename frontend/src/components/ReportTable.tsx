import { Link } from 'react-router-dom';
import type { ReportDto } from '../services';
import { formatBytes, formatDate, formatNumber } from '../utils/format';
import { IndexStatusBadge } from './Badges';

interface ReportTableProps {
  reports: ReportDto[];
  onDelete?: (report: ReportDto) => void;
  busyId?: string | null;
}

/** Dense table view -- the default for browsing a large corpus. */
export function ReportTable({ reports, onDelete, busyId }: ReportTableProps) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Report</th>
            <th>Company</th>
            <th>Year</th>
            <th>Type</th>
            <th style={{ textAlign: 'right' }}>Pages</th>
            <th style={{ textAlign: 'right' }}>Chunks</th>
            <th style={{ textAlign: 'right' }}>Size</th>
            <th>Indexed</th>
            <th>Uploaded</th>
            {onDelete && <th />}
          </tr>
        </thead>
        <tbody>
          {reports.map((report) => (
            <tr key={report.id}>
              <td>
                <Link to={`/reports/${report.id}`} className="nowrap">
                  {report.title}
                </Link>
              </td>
              <td className="nowrap">
                {report.ticker && <span className="mono subtle">{report.ticker} </span>}
                {report.companyName}
              </td>
              <td>{report.year ?? '--'}</td>
              <td>{report.reportType}</td>
              <td style={{ textAlign: 'right' }}>{formatNumber(report.pageCount)}</td>
              <td style={{ textAlign: 'right' }}>{formatNumber(report.chunkCount)}</td>
              <td style={{ textAlign: 'right' }} className="nowrap">
                {formatBytes(report.fileSizeBytes)}
              </td>
              <td>
                <IndexStatusBadge status={report.indexStatus} />
              </td>
              <td className="nowrap subtle">{formatDate(report.uploadedAt)}</td>
              {onDelete && (
                <td>
                  <button
                    type="button"
                    className="btn btn-sm btn-danger"
                    onClick={() => onDelete(report)}
                    disabled={busyId === report.id}
                  >
                    {busyId === report.id ? 'Removing...' : 'Delete'}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
