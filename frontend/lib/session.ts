/**
 * Sesión del navegador: el JWT y su vencimiento.
 *
 * Hasta ahora "tener sesión" en el frontend era "hay algo en
 * `localStorage.token`", y eso no es lo mismo que tener sesión: el token vence
 * a los 30 minutos (`ACCESS_TOKEN_EXPIRE_MINUTES`) pero se queda guardado para
 * siempre. Resultado: la plataforma pintaba el dashboard con una sesión muerta
 * y solo botaba al usuario cuando alguna pantalla llamaba al backend y recibía
 * un 401 — en `/` no hay ninguna llamada, así que ahí nunca botaba.
 *
 * Este módulo es la única fuente de verdad sobre la sesión del navegador.
 * `getToken()` mira el `exp` del JWT y borra el token vencido, de modo que
 * "hay token" vuelve a significar "hay sesión".
 *
 * Nota: esto es UX, no seguridad. Quien manda sobre la validez del token es el
 * backend, que verifica la firma. Acá solo leemos el payload (que no está
 * cifrado, solo firmado) para no mostrarle a alguien una pantalla que su token
 * ya no puede alimentar.
 */

const TOKEN_KEY = 'token';

/** Milisegundos de `exp`, o `null` si el token es ilegible o no trae `exp`. */
function vencimiento(token: string): number | null {
  const partes = token.split('.');
  if (partes.length !== 3) return null;
  try {
    // base64url → base64, con el padding que `atob` exige.
    const base64 = partes[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')));
    return typeof payload?.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * El token vigente, o `null`. Si está vencido o malformado lo borra: un token
 * que no podemos validar no sirve para nada y solo confunde al guard.
 */
export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  let token: string | null = null;
  try {
    token = localStorage.getItem(TOKEN_KEY);
  } catch {
    return null; // localStorage bloqueado (modo privado, cookies de terceros)
  }
  if (!token) return null;

  const exp = vencimiento(token);
  if (exp === null || exp <= Date.now()) {
    limpiar();
    return null;
  }
  return token;
}

/** `true` si hay sesión viva. Azúcar sobre `getToken()` para leer mejor. */
export function haySesion(): boolean {
  return getToken() !== null;
}

export function guardarToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* no-op */
  }
}

function limpiar(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* no-op */
  }
}

/**
 * Cierra sesión: borra el token y manda al login.
 *
 * `window.location.assign` en vez del router de Next a propósito — así se
 * descarta también el estado en memoria de la página que estaba abierta (datos
 * del usuario, listados, borradores) en lugar de dejarlo vivo bajo el login.
 */
export function cerrarSesion(): void {
  limpiar();
  if (typeof window !== 'undefined') window.location.assign('/login');
}
