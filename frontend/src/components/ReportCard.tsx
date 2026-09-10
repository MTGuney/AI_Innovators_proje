import { Link } from 'react-router-dom';
import type { ReportDto } from '../services';
import { formatBytes, formatDate, formatNumber } from '../utils/format';
import { IndexStatusBadge } from './Badges';
import './ReportCard.css';

/** Compact card used in the reports grid view. */
export function ReportCard({ report }: { report: ReportDto }) {
  return (
    <Link to={`/reports/${report.id}`} className="report-card card">
      <div className="row gap-8">
        <span className="report-ticker mono">{report.ticker ?? '--'}</span>
        <span className="spacer" />
        <IndexStatusBadge status={report.indexStatus} />
      </div>

      <h3 className="report-title" title={report.title}>
        {report.title}
      </h3>

      <div className="report-company">{report.companyName}</div>

      <dl className="report-facts">
        <div>
          <dt>Year</dt>
          <dd>{report.year ?? '--'}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{report.reportType}</dd>
        </div>
        <div>
          <dt>Pages</dt>
          <dd>{formatNumber(report.pageCount)}</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>{formatNumber(report.chunkCount)}</dd>
        </div>
      </dl>

      <div className="report-foot subtle">
        {formatDate(report.uploadedAt)}
        {report.fileSizeBytes > 0 && ` · ${formatBytes(report.fileSizeBytes)}`}
      </div>
    </Link>
  );
}
