import { useState, type FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { describeError } from '../hooks/useAsync';
import { useAuth } from '../hooks/useAuth';
import { ErrorState } from '../components/ErrorState';
import './LoginPage.css';

export function LoginPage() {
  const { isAuthenticated, login, register } = useAuth();
  const location = useLocation();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('demo@finrag.local');
  const [password, setPassword] = useState('demo12345');
  const [displayName, setDisplayName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (isAuthenticated) {
    const from = (location.state as { from?: string } | null)?.from ?? '/dashboard';
    return <Navigate to={from} replace />;
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') {
        await login(email.trim(), password);
      } else {
        await register(email.trim(), password, displayName.trim());
      }
    } catch (authError) {
      setError(describeError(authError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <section className="login-pitch">
        <div className="login-brand">
          <span className="brand-mark">FR</span>
          <strong>FinRAG</strong>
        </div>

        <h1>Ask questions of financial reports, and see the evidence.</h1>

        <p>
          A retrieval-augmented research assistant that answers from real annual
          reports. Every answer cites the passages it was built from.
        </p>

        <ul className="login-points">
          <li>
            <strong>Runs locally.</strong> Inference and embeddings are served by
            Foundry Local — no report text leaves the machine.
          </li>
          <li>
            <strong>Semantic retrieval.</strong> Questions are matched against
            report passages by meaning, not keywords.
          </li>
          <li>
            <strong>Traceable answers.</strong> Document, page, section and
            relevance are shown for every source.
          </li>
        </ul>
      </section>

      <section className="login-form-wrap">
        <form className="login-form card" onSubmit={submit}>
          <h2>{mode === 'login' ? 'Sign in' : 'Create an account'}</h2>

          {error && <ErrorState message={error} />}

          {mode === 'register' && (
            <div className="field">
              <label className="label" htmlFor="name">
                Display name
              </label>
              <input
                id="name"
                className="input"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                minLength={2}
                maxLength={128}
                autoComplete="name"
              />
            </div>
          )}

          <div className="field">
            <label className="label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
            />
          </div>

          <div className="field">
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>

          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login');
              setError(null);
            }}
          >
            {mode === 'login'
              ? 'Need an account? Register'
              : 'Already registered? Sign in'}
          </button>

          {mode === 'login' && (
            <p className="login-hint subtle">
              A demo account is seeded on first run:
              <br />
              <span className="mono">demo@finrag.local / demo12345</span>
            </p>
          )}
        </form>
      </section>
    </div>
  );
}
