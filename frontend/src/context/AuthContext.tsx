import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { authApi, type UserDto } from '../services';
import { getToken, setToken, setUnauthorizedHandler } from '../services/apiClient';

const USER_KEY = 'finrag.user';

interface AuthContextValue {
  user: UserDto | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredUser(): UserDto | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as UserDto) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Restore the session synchronously so a refresh does not flash the login page.
  const [user, setUser] = useState<UserDto | null>(() =>
    getToken() ? readStoredUser() : null,
  );

  const logout = useCallback(() => {
    setToken(null);
    try {
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    setUser(null);
  }, []);

  // A 401 from any request means the token is dead; drop it everywhere at once.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const persist = useCallback((response: { token: string; user: UserDto }) => {
    setToken(response.token);
    try {
      localStorage.setItem(USER_KEY, JSON.stringify(response.user));
    } catch {
      /* ignore */
    }
    setUser(response.user);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      persist(await authApi.login(email, password));
    },
    [persist],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      persist(await authApi.register(email, password, displayName));
    },
    [persist],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: user !== null, login, register, logout }),
    [user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
