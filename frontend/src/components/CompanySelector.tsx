import './CompanySelector.css';

interface CompanySelectorProps {
  companies: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  max?: number;
  label?: string;
}

/**
 * Multi-select for scoping retrieval to particular companies. Used both to
 * filter chat and to choose the two sides of a comparison.
 */
export function CompanySelector({
  companies,
  selected,
  onChange,
  max = 4,
  label = 'Companies',
}: CompanySelectorProps) {
  const toggle = (company: string) => {
    if (selected.includes(company)) {
      onChange(selected.filter((name) => name !== company));
      return;
    }
    // Silently ignore clicks past the limit rather than dropping a selection.
    if (selected.length >= max) return;
    onChange([...selected, company]);
  };

  if (companies.length === 0) {
    return <p className="subtle">No companies are indexed yet.</p>;
  }

  return (
    <div className="company-selector">
      <div className="row gap-8">
        <span className="section-title">{label}</span>
        {selected.length > 0 && (
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={() => onChange([])}
          >
            Clear
          </button>
        )}
      </div>

      <div className="company-chips">
        {companies.map((company) => {
          const active = selected.includes(company);
          const blocked = !active && selected.length >= max;
          return (
            <button
              key={company}
              type="button"
              className={`chip ${active ? 'chip-active' : ''}`}
              onClick={() => toggle(company)}
              disabled={blocked}
              title={blocked ? `Select at most ${max} companies` : undefined}
              aria-pressed={active}
            >
              {company}
            </button>
          );
        })}
      </div>
    </div>
  );
}
