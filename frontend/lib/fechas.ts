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
