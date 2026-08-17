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
 * ya no puede alimentar. Del payload se lee ÚNICAMENTE `exp`: nada de rol,
 * correo ni permisos, que son decisiones del servidor.
 */

const TOKEN_KEY = 'token';
const OFFSET_KEY = 'gloma_clock_offset_ms';

/**
 * Colchón contra relojes desajustados. El `exp` lo pone el servidor y lo
 * comparamos con el reloj del computador del usuario; si el suyo va adelantado
 * declararíamos vencido un token que el backend acepta sin problema, y como
 * además lo borramos, quedaría dando vueltas entre el login y el guard sin
 * poder entrar nunca. Ante la duda preferimos dejar pasar un token de más
 * (el backend responde 401 y ahí sí lo botamos) que trancar a alguien afuera.
 */
const MARGEN_DESFASE_MS = 60_000;

/** Diferencia medida entre el reloj del servidor y el de este navegador. */
function offsetReloj(): number {
  try {
    const guardado = Number(localStorage.getItem(OFFSET_KEY));
    return Number.isFinite(guardado) ? guardado : 0;
  } catch {
    return 0;
  }
}

/** "Ahora" según el servidor, hasta donde lo sabemos. */
function ahora(): number {
  return Date.now() + offsetReloj();
}

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
  if (exp === null || exp + MARGEN_DESFASE_MS <= ahora()) {
    limpiar();
    return null;
  }
  return token;
}

/** `true` si hay sesión viva. Azúcar sobre `getToken()` para leer mejor. */
export function haySesion(): boolean {
  return getToken() !== null;
}

/**
 * Cuánto le queda a la sesión, o `null` si no hay. Sirve para programar el
 * cierre: una pestaña abierta y quieta en una pantalla que no llama al backend
 * no se entera de que el token venció si nadie la despierta.
 */
export function msParaVencer(): number | null {
  const token = getToken();
  if (!token) return null;
  const exp = vencimiento(token);
  if (exp === null) return null;
  return Math.max(0, exp + MARGEN_DESFASE_MS - ahora());
}

/**
 * Guarda el token recién emitido.
 *
 * `fechaServidor` es el header `Date` de la respuesta del login: con él
 * calibramos el desfase del reloj del navegador y dejamos de depender de que
 * el usuario tenga la hora bien puesta.
 */
export function guardarToken(token: string, fechaServidor?: string | null): void {
  try {
    if (fechaServidor) {
      const servidor = Date.parse(fechaServidor);
      if (Number.isFinite(servidor)) {
        localStorage.setItem(OFFSET_KEY, String(servidor - Date.now()));
      }
    }
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* no-op */
  }
}

function limpiar(): void {
  try {
    // El offset del reloj NO se borra: no es del usuario sino del equipo, y
    // perderlo en cada logout reviviría el problema del reloj desajustado.
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* no-op */
  }
}

/**
 * Cierra sesión: borra el token y manda al login.
 *
 * `location.replace` en vez del router de Next y en vez de `assign`: descarta
 * el estado en memoria de la página que estaba abierta (datos del usuario,
 * listados, borradores) y además la saca del historial, para que el botón
 * "atrás" no la repinte — importa en un computador compartido.
 */
export function cerrarSesion(): void {
  limpiar();
  if (typeof window !== 'undefined') window.location.replace('/login');
}
