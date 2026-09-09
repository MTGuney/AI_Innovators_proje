import { useState, type FormEvent } from 'react';
import { reportsApi } from '../services';
import { describeError } from '../hooks/useAsync';
import { ErrorState } from './ErrorState';
import { Modal } from './Modal';

const ACCEPTED = '.pdf,.txt,.md,.html,.htm';

interface UploadModalProps {
  onClose: () => void;
  onUploaded: () => void;
}

/** Upload a report and hand it straight to the AI service for indexing. */
export function UploadModal({ onClose, onUploaded }: UploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [company, setCompany] = useState('');
  const [title, setTitle] = useState('');
  const [year, setYear] = useState('');
  const [reportType, setReportType] = useState('10-K');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || busy) return;

    setBusy(true);
    setError(null);
    try {
      await reportsApi.upload(file, {
        company: company.trim() || undefined,
        year: year ? Number(year) : undefined,
        reportType: reportType.trim() || undefined,
        title: title.trim() || undefined,
      });
      onUploaded();
      onClose();
    } catch (uploadError) {
      setError(describeError(uploadError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Upload a report"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="submit"
            form="upload-form"
            className="btn btn-primary"
            disabled={!file || busy}
          >
            {busy ? 'Indexing...' : 'Upload and index'}
          </button>
        </>
      }
    >
      <form id="upload-form" className="stack gap-16" onSubmit={submit}>
        {error && <ErrorState message={error} />}

        <div className="field">
          <label className="label" htmlFor="upload-file">
            Document
          </label>
          <input
            id="upload-file"
            className="input"
            type="file"
            accept={ACCEPTED}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            required
          />
          <span className="subtle" style={{ fontSize: 11.5 }}>
            PDF, TXT, Markdown or HTML. Indexing runs immediately and may take a
            moment for a long filing.
          </span>
        </div>

        <div className="field">
          <label className="label" htmlFor="upload-company">
            Company
          </label>
          <input
            id="upload-company"
            className="input"
            value={company}
            onChange={(event) => setCompany(event.target.value)}
            placeholder="e.g. Apple Inc"
          />
        </div>

        <div className="field">
          <label className="label" htmlFor="upload-title">
            Title
          </label>
          <input
            id="upload-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Defaults to the file name"
          />
        </div>

        <div className="row gap-12">
          <div className="field grow">
            <label className="label" htmlFor="upload-year">
              Fiscal year
            </label>
            <input
              id="upload-year"
              className="input"
              type="number"
              min={1900}
              max={2200}
              value={year}
              onChange={(event) => setYear(event.target.value)}
              placeholder="2024"
            />
          </div>

          <div className="field grow">
            <label className="label" htmlFor="upload-type">
              Report type
            </label>
            <input
              id="upload-type"
              className="input"
              value={reportType}
              onChange={(event) => setReportType(event.target.value)}
              placeholder="10-K"
            />
          </div>
        </div>
      </form>
    </Modal>
  );
}
