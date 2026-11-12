export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || 'http://localhost:4000/api';

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface SuccessEnvelope<T> {
  success: true;
  data: T;
}

interface ErrorEnvelope {
  success: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface ApiFetchOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
  skipAuthRedirect?: boolean;
  _retried?: boolean;
}

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const NO_REFRESH_PATHS = new Set([
  '/auth/login',
  '/auth/signup',
  '/auth/refresh',
  '/auth/logout',
  '/auth/2fa/verify-login',
  '/auth/forgot-password',
  '/auth/reset-password',
  '/auth/verify-email'
]);
const PUBLIC_AUTH_ROUTES = [
  '/login',
  '/signup',
  '/forgot-password',
  '/reset-password',
  '/verify-email'
];

let cachedCsrfToken: string | null = null;
let csrfPromise: Promise<string | null> | null = null;
let refreshInFlight: Promise<boolean> | null = null;

function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return cachedCsrfToken;
  const match = document.cookie.match(/(?:^|;\s*)beanbox_csrf=([^;]+)/);
  if (match && match[1]) {
    const val = decodeURIComponent(match[1]);
    cachedCsrfToken = val;
    return val;
  }
  return cachedCsrfToken;
}

async function ensureCsrfToken(): Promise<string | null> {
  const existing = readCsrfCookie();
  if (existing) return existing;
  if (csrfPromise) return csrfPromise;

  csrfPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/auth/csrf`, {
        method: 'GET',
        credentials: 'include'
      });
      const headerTok = res.headers.get('X-CSRF-Token');
      if (headerTok) {
        cachedCsrfToken = headerTok;
        return headerTok;
      }
      const body = (await res.json().catch(() => null)) as SuccessEnvelope<{
        csrfToken: string;
      }> | null;
      if (body?.success && body.data?.csrfToken) {
        cachedCsrfToken = body.data.csrfToken;
        return body.data.csrfToken;
      }
      return readCsrfCookie();
    } catch {
      return null;
    } finally {
      csrfPromise = null;
    }
  })();

  return csrfPromise;
}

async function refreshAccessTokenSingleFlight(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const csrf = await ensureCsrfToken();
      const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {})
        }
      });
      const nextCsrf = res.headers.get('X-CSRF-Token');
      if (nextCsrf) cachedCsrfToken = nextCsrf;
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

function redirectToLogin(): void {
  if (typeof window === 'undefined') return;
  const { pathname, search } = window.location;
  if (PUBLIC_AUTH_ROUTES.some((p) => pathname.startsWith(p))) return;
  const next = encodeURIComponent(`${pathname}${search}`);
  window.location.assign(`/login?next=${next}`);
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { params, headers, skipAuthRedirect, _retried, ...init } = options;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;

  const url = new URL(`${API_BASE_URL}${normalizedPath}`);
  if (params) {
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== '') {
        url.searchParams.set(key, String(val));
      }
    }
  }

  const method = (init.method || 'GET').toUpperCase();
  let csrfHeader: string | null = null;
  if (MUTATING_METHODS.has(method) && normalizedPath !== '/auth/csrf') {
    csrfHeader = readCsrfCookie() || (await ensureCsrfToken());
  }

  const res = await fetch(url.toString(), {
    ...init,
    credentials: 'include',
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(csrfHeader ? { 'X-CSRF-Token': csrfHeader } : {}),
      ...headers
    }
  });

  const respCsrf = res.headers.get('X-CSRF-Token');
  if (respCsrf) {
    cachedCsrfToken = respCsrf;
  }

  if (res.status === 401 && !_retried && !NO_REFRESH_PATHS.has(normalizedPath)) {
    const refreshed = await refreshAccessTokenSingleFlight();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, _retried: true });
    }
    if (!skipAuthRedirect) {
      redirectToLogin();
    }
  }

  const json = (await res.json().catch(() => null)) as
    | SuccessEnvelope<T>
    | ErrorEnvelope
    | null;

  if (!res.ok || !json || !json.success) {
    const errObj = json && 'error' in json ? json.error : null;
    throw new ApiClientError(
      res.status,
      errObj?.code || 'REQUEST_FAILED',
      errObj?.message || `Request failed with status ${res.status}`,
      errObj?.details
    );
  }

  return json.data;
}
