/**
 * Single HTTP entry point for the backend.
 *
 * Owns the base URL, the bearer token, and the translation of the backend's
 * error envelope into an `ApiError` the UI can display verbatim -- components
 * never touch `fetch` directly.
 */

const BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:5080/api';

const TOKEN_KEY = 'finrag.token';

export class ApiError extends Error {
  readonly status: number;
  readonly detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }

  /** True when the session is missing or expired and the user must sign in. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** True when the AI service or Foundry Local is down rather than the request being wrong. */
  get isServiceUnavailable(): boolean {
    return this.status === 503 || this.status === 504;
  }
}

// --- Token storage ------------------------------------------------------- //

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    // Private browsing can make storage throw; the app still works per-session.
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

/** Notified when the server rejects our token, so the app can sign out. */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

// --- Request ------------------------------------------------------------- //

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, signal } = options;

  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  // Let the browser set the multipart boundary for FormData.
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: formData ?? (body === undefined ? undefined : JSON.stringify(body)),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error;
    throw new ApiError(
      'Cannot reach the API. Please check that the backend is running.',
      0,
    );
  }

  if (response.status === 401) {
    onUnauthorized?.();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await readBody(response);

  if (!response.ok) {
    const envelope = payload as { error?: string; detail?: string; title?: string } | null;
    throw new ApiError(
      envelope?.error ?? envelope?.title ?? `Request failed (${response.status}).`,
      response.status,
      envelope?.detail,
    );
  }

  return payload as T;
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

/** Build a query string, omitting empty values. */
export function toQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body: body ?? {}, signal }),
  upload: <T>(path: string, formData: FormData, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', formData, signal }),
  delete: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { method: 'DELETE', signal }),
};
