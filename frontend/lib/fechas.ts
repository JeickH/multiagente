/**
 * Fechas y horas de la app, siempre en hora de Colombia.
 *
 * El backend guarda todo con `datetime.utcnow()` y lo serializa **sin marcar
 * la zona** ("2026-08-20T21:26:57.533129"). El estándar de JavaScript manda
 * interpretar esa forma —sin `Z` ni offset— como hora *local del navegador*,
 * así que un mensaje de las 4:26 p. m. de Colombia se pintaba a las 9:26 p. m.:
 * cinco horas adelantado. De ahí que la bandeja de asesores mostrara horas que
 * no existieron.
 *
 * `aInstante` es el arreglo: si el texto no trae zona, se le pone la `Z` que el
 * backend omitió. Y todo se formatea con `timeZone: 'America/Bogota'` para que
 * la hora sea la misma en el portátil del asesor, en el celular del CEO y en un
 * navegador configurado en otro país. Colombia no tiene horario de verano, así
 * que el offset es -05:00 todo el año.
 */

/** Zona del equipo que opera el panel. */
export const ZONA_CO = 'America/Bogota';

const LOCALE = 'es-CO';

/** ¿El texto ISO ya dice en qué zona está? (`...Z` o `...-05:00`). */
const TIENE_ZONA = /[Zz]$|[+-]\d{2}:?\d{2}$/;

/**
 * Convierte lo que manda el backend en un instante real en la línea de tiempo.
 * Devuelve `null` si viene vacío o no es una fecha válida — quien llame decide
 * qué pintar en ese caso, en vez de mostrar "Invalid Date".
 */
export function aInstante(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const texto = TIENE_ZONA.test(iso) ? iso : `${iso}Z`;
  const d = new Date(texto);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Solo la hora, como en la burbuja de un chat: "4:26 p. m.". */
export function horaCorta(iso: string | null | undefined, fallback = ''): string {
  const d = aInstante(iso);
  if (!d) return fallback;
  return d.toLocaleTimeString(LOCALE, {
    timeZone: ZONA_CO,
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Día y hora sin año, para listados: "20 ago, 4:26 p. m.". */
export function fechaHoraCorta(iso: string | null | undefined, fallback = ''): string {
  const d = aInstante(iso);
  if (!d) return fallback;
  return d.toLocaleString(LOCALE, {
    timeZone: ZONA_CO,
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Fecha y hora completas, para el `title` de algo que muestra una forma
 * abreviada: la lista dice "Ayer" y al pasar el mouse se ve el dato exacto.
 */
export function fechaHoraLarga(iso: string | null | undefined, fallback = ''): string {
  const d = aInstante(iso);
  if (!d) return fallback;
  return d.toLocaleString(LOCALE, {
    timeZone: ZONA_CO,
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * El día del calendario **en Colombia**, como "2026-08-31".
 *
 * `en-CA` se usa por su formato, no por el idioma: es el único locale que
 * devuelve ISO (año-mes-día) de fábrica, y eso hace que dos fechas se puedan
 * comparar con `===`. Comparar con `getDate()` sería leer el día del
 * navegador: a las 8 p. m. de Colombia el `getDate()` de un equipo en UTC ya
 * es el día siguiente, y "hoy" saldría "ayer".
 */
function diaEnColombia(d: Date): string {
  return d.toLocaleDateString('en-CA', { timeZone: ZONA_CO });
}

/** Cuántos días de calendario colombiano hay entre `d` y hoy. 0 = hoy. */
function diasDesdeHoy(d: Date): number {
  const dia = diaEnColombia(d);
  const hoy = diaEnColombia(new Date());
  // Se restan como fechas puras (mediodía UTC, para no rozar ningún cambio de
  // día) en vez de restar los instantes: entre las 11 p. m. y la 1 a. m. hay
  // dos horas pero son días distintos, y lo que importa acá es el calendario.
  const ms = Date.parse(`${hoy}T12:00:00Z`) - Date.parse(`${dia}T12:00:00Z`);
  return Math.round(ms / 86400000);
}

/**
 * Marca de tiempo de la lista de conversaciones, al estilo de WhatsApp: la
 * hora si es de hoy, "Ayer" si es de ayer, y la fecha si es más vieja.
 *
 * Antes acá salía **siempre la hora sola**, y esa era la queja: un chat del
 * 27 de agosto mostraba "12:33 p. m." sin más, que se lee como "hace un rato".
 * La hora nunca estuvo mal calculada —el arreglo de zona ya estaba— pero sin
 * el día la respuesta era engañosa igual.
 */
export function marcaDeTiempoLista(iso: string | null | undefined, fallback = ''): string {
  const d = aInstante(iso);
  if (!d) return fallback;

  const dias = diasDesdeHoy(d);
  if (dias <= 0) return horaCorta(iso, fallback);
  if (dias === 1) return 'Ayer';
  if (dias < 7) {
    // "mié", "jue": dentro de la semana el nombre del día ubica mejor que un
    // número, que es como lo resuelve cualquier app de mensajería.
    return d.toLocaleDateString(LOCALE, { timeZone: ZONA_CO, weekday: 'short' });
  }
  if (dias < 365) {
    return d.toLocaleDateString(LOCALE, {
      timeZone: ZONA_CO,
      day: '2-digit',
      month: 'short',
    });
  }
  return d.toLocaleDateString(LOCALE, {
    timeZone: ZONA_CO,
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  });
}

/**
 * Encabezado del separador de día dentro del chat: "Hoy", "Ayer" o
 * "miércoles, 27 de agosto de 2026".
 *
 * Sin esto, un historial de varios días es una fila de burbujas con horas
 * sueltas: "9:14 a. m." debajo de "6:40 p. m." parece que el bot contestó
 * antes de que le escribieran.
 */
export function encabezadoDeDia(iso: string | null | undefined, fallback = ''): string {
  const d = aInstante(iso);
  if (!d) return fallback;

  const dias = diasDesdeHoy(d);
  if (dias <= 0) return 'Hoy';
  if (dias === 1) return 'Ayer';
  return d.toLocaleDateString(LOCALE, {
    timeZone: ZONA_CO,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/**
 * ¿Los dos instantes caen el mismo día en Colombia? Es lo que decide dónde va
 * un separador. Con fechas inválidas devuelve `true` para no inventar un corte
 * donde no se sabe si lo hay.
 */
export function mismoDia(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const da = aInstante(a);
  const dbb = aInstante(b);
  if (!da || !dbb) return true;
  return diaEnColombia(da) === diaEnColombia(dbb);
}
