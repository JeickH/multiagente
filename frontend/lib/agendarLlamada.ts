/**
 * «Agendar una llamada» con Cal.com (#625, controles de seguridad #629).
 *
 * Lo usan la demo (`/demo`) y la landing (`/gloma`) a través de
 * `components/AgendarLlamadaModal.tsx`. Sin React, para poder probarlo.
 *
 * Por qué un iframe y no el `embed.js` de Cal: en `/demo` el token de la demo
 * y el hilo viven en `sessionStorage`, y un script de terceros en la página
 * podría leerlos. El iframe es otro origen: no ve nada de la página.
 *
 * Configuración del CEO (embed oficial, 17-oct): `layout=month_view`,
 * `useSlotsViewOnSmallScreen=true`, `theme=dark` y color de marca #4DB6AC.
 * `embed.js` pasa las tres primeras por query; aquí van igual. Lo que de
 * verdad pinta oscuro el calendario es `color-scheme: dark` en el `<iframe>`
 * (`CAL_COLOR_SCHEME`): la página normal de Cal ignora `theme` por query y
 * sigue `prefers-color-scheme`, que dentro de un iframe toma el
 * `color-scheme` del elemento (verificado con el sistema en modo claro). El
 * color de marca NO se puede pasar: `embed.js` lo manda con la instrucción
 * `ui` por `postMessage` (prohibido por #629) y `brandColor` por query no
 * tiene efecto; se configura en el panel de Cal.com.
 *
 * Por qué la página normal de reservas y no la de `/embed`: la de `/embed`
 * deja su `body` oculto (`visibility:hidden`, `opacity:0`) hasta que la página
 * padre le responde un saludo por `postMessage`, y #629 prohíbe escribirle al
 * iframe. La página normal se pinta sola, en modo oscuro y en español, con la
 * vista mensual, prellena `name` y `email`, y aun así le avisa a la página
 * padre lo que pasa con mensajes `{originator: 'CAL', type, fullType, data}`
 * desde `https://app.cal.com` (verificado con Chrome el 2026-10-17:
 * `navigatedToBooker`, `availabilityLoaded`). Sin cabeceras `X-Frame-Options`
 * ni `frame-ancestors`: se puede enmarcar.
 */

/** `color-scheme` del `<iframe>`: hace que Cal se pinte en su tema oscuro. */
export const CAL_COLOR_SCHEME = 'dark';

/** Origen fijo de Cal (#629). Los mensajes de cualquier otro origen se ignoran. */
export const CAL_ORIGIN = 'https://app.cal.com';

/** Evento de Gloma en Cal: «Hablemos de Gloma», 30 min. */
const CAL_EVENTO = '/gloma/hablemos-de-gloma';

/**
 * Atributo `sandbox` del iframe, el más restrictivo que funciona (#629):
 * scripts y su propio origen (Cal es una app y guarda su estado), formularios
 * (la reserva) y ventanas nuevas (los enlaces «agregar al calendario» de la
 * confirmación). PROHIBIDO `allow-top-navigation*`: Cal nunca puede sacar al
 * visitante de la página.
 */
export const CAL_SANDBOX =
  'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox';

/** Tipos de mensaje con los que Cal avisa que la reserva quedó hecha. */
const TIPOS_RESERVA = new Set(['bookingSuccessful', 'bookingSuccessfulV2']);

const MAX_NOMBRE = 80;
const MAX_CORREO = 254;

/**
 * URL del iframe. Además de la configuración fija del evento, solo `name` y
 * `email` (#629): nunca teléfono, token,
 * demo_id, empresa ni la conversación. `URL.searchParams` codifica cada valor
 * (equivale a `encodeURIComponent`), así que un nombre con `&` o `#` no puede
 * agregar parámetros ni cambiar el destino.
 */
export function urlCal(datos?: { nombre?: string | null; correo?: string | null }): string {
  const url = new URL(CAL_EVENTO, CAL_ORIGIN);
  url.searchParams.set('layout', 'month_view');
  url.searchParams.set('theme', 'dark');
  url.searchParams.set('useSlotsViewOnSmallScreen', 'true');
  const nombre = (datos?.nombre || '').trim().slice(0, MAX_NOMBRE);
  const correo = (datos?.correo || '').trim();
  if (nombre) url.searchParams.set('name', nombre);
  if (correo && correo.length <= MAX_CORREO && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(correo)) {
    url.searchParams.set('email', correo);
  }
  return url.toString();
}

/**
 * ¿Este `message` es Cal avisando que se hizo la reserva? Las cuatro
 * condiciones de #629: origen fijo, que venga de NUESTRO iframe (no de otra
 * ventana del mismo origen), objeto con `originator === 'CAL'` y tipo de
 * reserva exitosa. Nada de `data` se usa más allá de esta comprobación.
 */
export function esReservaDeCal(
  evento: { origin: string; source: unknown; data: unknown },
  ventanaDelIframe: unknown,
): boolean {
  if (evento.origin !== CAL_ORIGIN) return false;
  if (!ventanaDelIframe || evento.source !== ventanaDelIframe) return false;
  const d = evento.data;
  if (!d || typeof d !== 'object') return false;
  const { originator, type } = d as { originator?: unknown; type?: unknown };
  return originator === 'CAL' && typeof type === 'string' && TIPOS_RESERVA.has(type);
}

/** Textos del modal y de los dos botones (iguales en la demo y la landing). */
export const TEXTOS_AGENDAR = {
  agendar: 'Agendar una llamada',
  /** Para espacios chicos (barra fija del celular, cabecera del chat). */
  agendarCorto: 'Agendar',
  whatsapp: 'Escribir por WhatsApp',
  whatsappCorto: 'WhatsApp',
  nuevaPestana: ' (se abre en otra pestaña)',
  titulo: 'Agenda una llamada con Gloma',
  subtitulo: '30 minutos por videollamada. Elige el día y la hora que te sirvan.',
  cerrar: 'Cerrar',
  iframe: 'Calendario de Gloma para agendar una llamada',
  cargando: 'Cargando el calendario…',
  lento: '¿No carga el calendario?',
  abrirAparte: 'Ábrelo en otra pestaña',
  agendada: '¡Listo! Te llegará la invitación a tu correo.',
} as const;
