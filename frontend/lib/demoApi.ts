/**
 * Cliente de la API de la demo pública (`/demo`, Sprint 32, #614).
 *
 * Contrato (BITACORA, Sprint 32):
 *   POST /demo/iniciar               → 202 {demo_id, token}
 *   GET  /demo/{demo_id}/estado      → {estado, empresa, productos?, mensaje_sugerido?}
 *   POST /demo/{demo_id}/chat {message} → {actions, session: null, finished, handoff}
 * Las dos últimas llevan el token en el header `X-Demo-Token`. El historial
 * del chat y el contador de turnos viven en el servidor (#608, A3): el front
 * manda solo `{message}`, no guarda ni reenvía `session` (siempre llega null)
 * y el tope de 15 turnos llega como `finished=true`. Sin token
 * válido el backend responde 404 (no 403), así que aquí 404 = «esta demo ya
 * no está disponible».
 *
 * Base URL: `NEXT_PUBLIC_DEMO_API_URL`. Por defecto `/api`, el mismo rewrite
 * de `next.config.js` que usa el resto del frontend. En producción seguridad
 * (#608, A1) pide llamar directo a `https://api.glomacx.com` para que API
 * Gateway vea la IP real; eso lo configura deploy-aws (#617) solo con la env
 * var. OJO: al ser otro origen, el backend tiene que permitir por CORS el
 * origen de la landing y el header `X-Demo-Token`.
 *
 * Sesión de la demo: `demo_id` y token viven en el estado de React y en
 * `sessionStorage['gloma_demo']` para sobrevivir a una recarga. NUNCA en la
 * clave `token` ni en `lib/session.ts` (regla #7: esa es la sesión de la
 * plataforma), nunca en localStorage ni en la URL. Todo acceso a
 * `sessionStorage` va con try/catch: en modo privado o con el almacenamiento
 * bloqueado la demo sigue funcionando, solo que no sobrevive a la recarga.
 *
 * Errores: el cliente nunca muestra el cuerpo crudo del backend (regla #6).
 * `DemoApiError.status` es lo único que decide qué se pinta; `0` = red.
 */

const BASE_API = (process.env.NEXT_PUBLIC_DEMO_API_URL || '/api').replace(/\/+$/, '');

/** Modo simulado para desarrollo. Nunca activo por defecto. */
export const DEMO_MOCK = process.env.NEXT_PUBLIC_DEMO_MOCK === '1';

/**
 * El simulador vive en `demoMock.ts` y se carga con `import()` solo si
 * `DEMO_MOCK`: así no viaja en el bundle de la página en producción.
 */
const simulador = () => import('./demoMock').then((m) => m.mock);

/**
 * WhatsApp público de Gloma (el mismo de `_HANDOFF_TEXT` en
 * `backend/app/routers/landing.py` y del widget de la landing).
 */
const WHATSAPP_GLOMA = '573150764000';

// --------------------------------------------------------------------------
// Tipos del contrato
// --------------------------------------------------------------------------

export type EstadoGeneracion = 'generando' | 'lista' | 'error';

export interface ProductoDemo {
  nombre: string;
  resumen: string;
}

export interface EstadoDemo {
  estado: EstadoGeneracion;
  empresa: string;
  productos: ProductoDemo[];
  mensaje_sugerido: string | null;
}

export interface DatosIniciar {
  nombre: string;
  empresa: string;
  telefono: string;
  correo: string;
  tipo_empresa: string;
  tipo_otro?: string;
  acepta_contacto: true;
  acepta_promociones: boolean;
  /** Honeypot (#608, M7): una persona lo deja vacío. */
  sitio_web: string;
  /** Milisegundos desde que se abrió el formulario hasta el envío (#608, M7). */
  form_ms: number;
  /** Solo si Turnstile está activo. */
  turnstile_token?: string;
}

export interface IniciarOut {
  demo_id: string;
  token: string;
}

export interface AccionChat {
  type: string;
  text: string;
  url?: string | null;
  media_type?: string | null;
}

/** `session` existe en la respuesta pero siempre es null: se ignora. */
export interface ChatOut {
  actions: AccionChat[];
  finished: boolean;
  handoff: boolean;
}

export class DemoApiError extends Error {
  /** HTTP status; `0` cuando no hubo respuesta (red, timeout). */
  status: number;
  /** Campos que el backend rechazó en un 422, si lo dijo. */
  campos: string[];
  constructor(status: number, campos: string[] = []) {
    super(status === 0 ? 'red' : `HTTP ${status}`);
    this.status = status;
    this.campos = campos;
  }
}

// --------------------------------------------------------------------------
// Transporte
// --------------------------------------------------------------------------

async function pedir(
  ruta: string,
  init: RequestInit & { token?: string },
  timeoutMs: number,
): Promise<Response> {
  const headers = new Headers(init.headers || {});
  if (init.body) headers.set('Content-Type', 'application/json');
  if (init.token) headers.set('X-Demo-Token', init.token);

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(`${BASE_API}${ruta}`, {
      method: init.method,
      body: init.body,
      headers,
      signal: ctrl.signal,
      // Otro origen en producción: sin cookies, el acceso va solo por el token.
      credentials: 'omit',
      cache: 'no-store',
    });
  } catch {
    throw new DemoApiError(0);
  } finally {
    clearTimeout(t);
  }
}

/** Nombres de campo de un 422 de FastAPI (`detail: [{loc: ['body', 'correo']}]`). */
async function camposRechazados(res: Response): Promise<string[]> {
  try {
    const body = await res.json();
    if (!Array.isArray(body?.detail)) return [];
    return body.detail
      .map((d: { loc?: unknown[] }) => (Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null))
      .filter((c: unknown): c is string => typeof c === 'string');
  } catch {
    return [];
  }
}

function idSeguro(demoId: string): string {
  return encodeURIComponent(demoId);
}

function normalizarEstado(raw: unknown): EstadoDemo {
  const r = (raw || {}) as Record<string, unknown>;
  const estado: EstadoGeneracion =
    r.estado === 'lista' || r.estado === 'error' ? r.estado : 'generando';
  const productos = Array.isArray(r.productos)
    ? (r.productos as Record<string, unknown>[])
        .filter((p) => p && typeof p.nombre === 'string')
        .map((p) => ({
          nombre: String(p.nombre),
          resumen: typeof p.resumen === 'string' ? p.resumen : '',
        }))
    : [];
  return {
    estado,
    empresa: typeof r.empresa === 'string' ? r.empresa : '',
    productos,
    mensaje_sugerido: typeof r.mensaje_sugerido === 'string' ? r.mensaje_sugerido : null,
  };
}

// --------------------------------------------------------------------------
// Endpoints
// --------------------------------------------------------------------------

export async function iniciarDemo(datos: DatosIniciar): Promise<IniciarOut> {
  if (DEMO_MOCK) return (await simulador()).iniciar(datos);
  const res = await pedir('/demo/iniciar', { method: 'POST', body: JSON.stringify(datos) }, 20000);
  if (res.status === 422) throw new DemoApiError(422, await camposRechazados(res));
  if (!res.ok) throw new DemoApiError(res.status);
  const body = await res.json().catch(() => null);
  if (!body || typeof body.demo_id !== 'string' || typeof body.token !== 'string') {
    throw new DemoApiError(500);
  }
  return { demo_id: body.demo_id, token: body.token };
}

export async function consultarEstado(demoId: string, token: string): Promise<EstadoDemo> {
  if (DEMO_MOCK) return (await simulador()).estado(demoId, token);
  const res = await pedir(`/demo/${idSeguro(demoId)}/estado`, { method: 'GET', token }, 10000);
  if (!res.ok) throw new DemoApiError(res.status);
  return normalizarEstado(await res.json().catch(() => null));
}

export async function enviarChat(demoId: string, token: string, message: string): Promise<ChatOut> {
  if (DEMO_MOCK) return (await simulador()).chat(demoId, token, message);
  const res = await pedir(
    `/demo/${idSeguro(demoId)}/chat`,
    { method: 'POST', token, body: JSON.stringify({ message }) },
    // Un turno de Bedrock puede tardar (cliente propio: 25 s × 2 intentos).
    60000,
  );
  if (!res.ok) throw new DemoApiError(res.status);
  const body = (await res.json().catch(() => null)) as Partial<ChatOut> | null;
  if (!body) throw new DemoApiError(500);
  return {
    actions: Array.isArray(body.actions) ? body.actions.filter((a) => a && typeof a.text === 'string') : [],
    finished: Boolean(body.finished),
    handoff: Boolean(body.handoff),
  };
}

// --------------------------------------------------------------------------
// Eventos de seguimiento (#625): POST /demo/{id}/evento → 204
// --------------------------------------------------------------------------

export type TipoEvento = 'whatsapp' | 'llamada_abierta' | 'llamada_agendada';

/**
 * Cuenta un clic de cierre de la demo. Fire-and-forget: nunca bloquea, nunca
 * muestra error y nunca lanza. Solo si hay una demo con token (en la landing
 * o tras un 429 no hay a quién sumarle el clic).
 *
 * `keepalive: true` porque el clic de WhatsApp abre otra pestaña y en
 * celular la página puede quedar congelada: así la petición sale igual.
 * Controles de #629: token SOLO en el header `X-Demo-Token` (nunca en la URL
 * ni en el body), `credentials: 'omit'` y nada de `sendBeacon` (no permite
 * headers propios).
 */
export function registrarEvento(demo: { id: string; token: string } | null | undefined, tipo: TipoEvento): void {
  if (!demo?.id || !demo.token) return;
  try {
    if (DEMO_MOCK) {
      void simulador()
        .then((m) => m.evento(demo.id, demo.token, tipo))
        .catch(() => undefined);
      return;
    }
    void fetch(`${BASE_API}/demo/${idSeguro(demo.id)}/evento`, {
      method: 'POST',
      keepalive: true,
      credentials: 'omit',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-Demo-Token': demo.token },
      body: JSON.stringify({ tipo }),
    }).catch(() => undefined);
  } catch {
    /* nunca rompe un clic */
  }
}

// --------------------------------------------------------------------------
// «Escribir por WhatsApp»
// --------------------------------------------------------------------------

/**
 * Enlace wa.me al WhatsApp público de Gloma con el texto prellenado. El
 * nombre de la empresa viaja como texto dentro de `encodeURIComponent`: no
 * puede romper la URL ni cambiar el destino.
 */
export function enlaceWhatsapp(empresa: string | null | undefined, plantilla: {
  despuesDeLaDemo: string;
  sinDemo: string;
}): string {
  const nombre = (empresa || '').trim().slice(0, 80);
  const texto = nombre ? plantilla.despuesDeLaDemo.replace('{empresa}', nombre) : plantilla.sinDemo;
  return `https://wa.me/${WHATSAPP_GLOMA}?text=${encodeURIComponent(texto)}`;
}

// --------------------------------------------------------------------------
// sessionStorage['gloma_demo']
// --------------------------------------------------------------------------

export const CLAVE_DEMO = 'gloma_demo';

export type CheckMensaje = 'enviado' | 'entregado' | 'leido' | 'error';

export interface MensajeChat {
  id: number;
  de: 'yo' | 'bot';
  texto: string;
  /** Hora ya formateada (Colombia), como en la burbuja. */
  hora: string;
  check?: CheckMensaje;
}

export type FinDemo = 'handoff' | 'finished' | null;

export interface ChatGuardado {
  fin: FinDemo;
  mensajes: MensajeChat[];
}

export interface DemoGuardada {
  v: 1;
  id: string;
  token: string;
  /** Primer nombre, para «Hola, Camila» en la slide 1. */
  nombre: string;
  empresa: string;
  /** Cuándo se creó: el aviso de 20 s y el corte de 90 s no se reinician al recargar. */
  creadoMs: number;
  etapa: 'slides' | 'chat';
  chat?: ChatGuardado;
}

/** Tope de mensajes que se guardan para pintar el hilo tras una recarga. */
const MAX_MENSAJES_GUARDADOS = 40;

export function almacen(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function leerDemoGuardada(): DemoGuardada | null {
  try {
    const raw = almacen()?.getItem(CLAVE_DEMO);
    if (!raw) return null;
    const d = JSON.parse(raw) as Partial<DemoGuardada>;
    if (
      d?.v !== 1 ||
      typeof d.id !== 'string' ||
      typeof d.token !== 'string' ||
      typeof d.creadoMs !== 'number' ||
      (d.etapa !== 'slides' && d.etapa !== 'chat')
    ) {
      return null;
    }
    const chat = d.chat && Array.isArray(d.chat.mensajes) ? d.chat : undefined;
    return {
      v: 1,
      id: d.id,
      token: d.token,
      nombre: typeof d.nombre === 'string' ? d.nombre : '',
      empresa: typeof d.empresa === 'string' ? d.empresa : '',
      creadoMs: d.creadoMs,
      etapa: d.etapa,
      chat: chat && {
        fin: chat.fin === 'handoff' || chat.fin === 'finished' ? chat.fin : null,
        mensajes: chat.mensajes
          .filter((m) => m && (m.de === 'yo' || m.de === 'bot') && typeof m.texto === 'string')
          .slice(-MAX_MENSAJES_GUARDADOS),
      },
    };
  } catch {
    return null;
  }
}

export function guardarDemo(d: DemoGuardada): void {
  try {
    const copia: DemoGuardada = d.chat
      ? { ...d, chat: { ...d.chat, mensajes: d.chat.mensajes.slice(-MAX_MENSAJES_GUARDADOS) } }
      : d;
    almacen()?.setItem(CLAVE_DEMO, JSON.stringify(copia));
  } catch {
    /* almacenamiento lleno o bloqueado: la demo sigue, solo no sobrevive a la recarga */
  }
}

export function borrarDemo(): void {
  try {
    almacen()?.removeItem(CLAVE_DEMO);
  } catch {
    /* no-op */
  }
}
