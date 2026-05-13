/**
 * Helper de fetch autenticado.
 *
 * Patrón ya usado en `pages/bots.tsx`/`mensajes.tsx`: JWT en `localStorage`
 * bajo la clave `token`, las requests al backend se hacen al path `/api/...`
 * (rewrite definido en `next.config.js` → `${BACKEND_URL}/...`).
 *
 * Si el backend responde 401, limpiamos el token y redirigimos a /login.
 * Si responde otro error, lanzamos un `Error` con el mensaje sanitizado del
 * backend (o un fallback genérico). El detalle completo NO se loggea desde
 * el cliente — el backend ya lo logea en su lado (regla 6 de Seguridad).
 */

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

function redirectToLogin() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('token');
  } catch {
    /* no-op */
  }
  window.location.assign('/login');
}

export async function authedFetch<T = unknown>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const token = getToken();
  if (!token) {
    redirectToLogin();
    throw new ApiError('No autenticado', 401);
  }

  const url = path.startsWith('/api/') || path.startsWith('http')
    ? path
    : `/api${path.startsWith('/') ? '' : '/'}${path}`;

  const headers = new Headers(opts.headers || {});
  headers.set('Authorization', `Bearer ${token}`);
  if (opts.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(url, { ...opts, headers });

  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError('Sesión expirada', 401);
  }

  if (!res.ok) {
    let detail = 'Error temporal al conectar con el servidor.';
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* no-op: respuesta no-JSON */
    }
    throw new ApiError(detail, res.status);
  }

  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;

  return (await res.json()) as T;
}
