import { NavLink, Outlet } from 'react-router-dom';
import './AppLayout.css';

const NAV_ITEMS = [
  { to: '/chat', label: 'Ask', glyph: '✦' },
  { to: '/reports', label: 'Indexed reports', glyph: '▦' },
  { to: '/compare', label: 'Compare', glyph: '⇄' },
];

export function AppLayout() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">FR</span>
          <span className="stack">
            <strong className="brand-name">FinAI</strong>
            <span className="brand-sub">Financial Research</span>
          </span>
        </div>

        <nav className="nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}
            >
              <span className="nav-glyph" aria-hidden="true">
                {item.glyph}
              </span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="nav-note">
            Answers are generated locally with Foundry Local. Retrieval is always
            shown alongside the answer.
          </div>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
