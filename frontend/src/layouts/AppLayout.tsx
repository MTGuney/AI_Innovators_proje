import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { initials } from '../utils/format';
import './AppLayout.css';

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', glyph: '▤' },
  { to: '/reports', label: 'Reports', glyph: '▦' },
  { to: '/chat', label: 'AI Assistant', glyph: '✦' },
  { to: '/compare', label: 'Compare', glyph: '⇄' },
  { to: '/settings', label: 'Settings', glyph: '⚙' },
];

export function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">FR</span>
          <span className="stack">
            <strong className="brand-name">FinRAG</strong>
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

          <div className="user-row">
            <span className="avatar" aria-hidden="true">
              {initials(user?.displayName ?? 'User')}
            </span>
            <span className="stack grow" style={{ minWidth: 0 }}>
              <strong className="user-name">{user?.displayName}</strong>
              <span className="user-mail">{user?.email}</span>
            </span>
            <button
              type="button"
              className="btn btn-sm btn-ghost sign-out"
              onClick={logout}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
