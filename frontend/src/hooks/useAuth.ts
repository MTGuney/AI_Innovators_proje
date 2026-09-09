import { useContext } from 'react';
import { AuthContext } from '../context/AuthContext';

/** Access the session. Throws if used outside `AuthProvider`, which is a bug. */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside an AuthProvider.');
  }
  return context;
}
