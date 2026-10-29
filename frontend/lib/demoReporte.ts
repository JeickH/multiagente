/**
 * Reporte de EJEMPLO de la demo pública (`/demo`, encargo del CEO del
 * 2026-10-28): «así se vería el reporte de {empresa}» con un mes de operación.
 *
 * TODO lo de aquí es ficticio y fijo: no sale de la base, ni de la demo que
 * hizo la persona, ni de ningún cliente. Las cifras son verosímiles para una
 * agencia u hotel que recibe ~870 conversaciones al mes, y la pantalla lo
 * rotula a la vista («Ejemplo con datos ficticios»). No son cifras públicas
 * autorizadas de Gloma: no se copian a la landing ni a material de ventas.
 *
 * Los números cuadran entre sí (lo verifica `demoReporte.test.ts`): el primer
 * paso son las conversaciones del mes, «listos para reservar» es lo mismo en
 * los pasos y en la calificación, y las horas suman los mensajes del mes.
 */

export const REPORTE_TEXTOS = {
  boton: 'Ver reporte de ejemplo',
  botonCorto: 'Reporte',
  /** Usa `{empresa}`. */
  rotulo: 'Ejemplo con datos ficticios: así se vería el reporte de {empresa}',
  titulo: 'Tu mes con Gloma',
  periodo: 'Últimos 30 días',
  cerrar: 'Cerrar el reporte',
  panelTitulo: '¿Y qué ves tú?',
  panelTexto: 'Un reporte de cómo le va a {empresa} con sus chats, cada semana.',
  cierreTitulo: 'Este reporte, con los chats de {empresa}',
  cierreTexto:
    'En la prueba gratis de 14 días lo armamos con tus conversaciones de verdad: dónde se te va la gente y cuánta venta se queda en el aire.',
} as const;

/** Ticket promedio de una reserva en el ejemplo (COP). */
export const TICKET_PROMEDIO = 1_450_000;

export interface PasoReporte {
  clave: string;
  etiqueta: string;
  personas: number;
}

/** En qué paso se va la gente (conversaciones del mes). */
export const PASOS: readonly PasoReporte[] = [
  { clave: 'llegaron', etiqueta: 'Te escribieron', personas: 870 },
  { clave: 'precio', etiqueta: 'Recibieron el precio', personas: 712 },
  { clave: 'datos', etiqueta: 'Dejaron sus datos', personas: 341 },
  { clave: 'listos', etiqueta: 'Listos para reservar', personas: 168 },
  { clave: 'reservaron', etiqueta: 'Reservaron', personas: 74 },
];

export interface FranjaRespuesta {
  franja: string;
  /** Promedio del agente, en segundos. */
  agenteSeg: number;
  /** Promedio de los asesores, en minutos. */
  asesoresMin: number;
}

/** Tiempo promedio hasta la primera respuesta, por franja del día. */
export const RESPUESTA_POR_FRANJA: readonly FranjaRespuesta[] = [
  { franja: '6 a 9 a. m.', agenteSeg: 8, asesoresMin: 42 },
  { franja: '9 a. m. a 1 p. m.', agenteSeg: 6, asesoresMin: 11 },
  { franja: '1 a 6 p. m.', agenteSeg: 7, asesoresMin: 18 },
  { franja: '6 a 10 p. m.', agenteSeg: 7, asesoresMin: 85 },
  { franja: '10 p. m. a 6 a. m.', agenteSeg: 9, asesoresMin: 580 },
];

/** Horario de oficina del ejemplo: de 8 a. m. a 6 p. m. (horas 8 a 17). */
export const HORARIO_OFICINA = { desde: 8, hasta: 18 } as const;

/**
 * Mensajes que llegaron en el mes por hora del día (índice = hora, 0 a 23).
 * Picos a media mañana y de 7 a 10 p. m., cuando la gente planea el viaje.
 */
export const MENSAJES_POR_HORA: readonly number[] = [
  118, 64, 31, 18, 15, 34, 96, 188, 342, 455, 512, 478,
  402, 366, 398, 421, 389, 352, 371, 452, 503, 468, 331, 214,
];

export interface Calificacion {
  clave: 'listos' | 'tibios' | 'no_listos';
  etiqueta: string;
  detalle: string;
  personas: number;
}

/** Cuáles interesados están listos para comprar (las 870 conversaciones). */
export const CALIFICACION: readonly Calificacion[] = [
  { clave: 'listos', etiqueta: 'Listos', detalle: 'Tienen fecha, personas y presupuesto', personas: 168 },
  { clave: 'tibios', etiqueta: 'Tibios', detalle: 'Preguntan para más adelante o comparan', personas: 297 },
  { clave: 'no_listos', etiqueta: 'No listos', detalle: 'Solo curiosean o buscan otra cosa', personas: 405 },
];

/** Venta que se queda en el aire, en pesos, en las últimas 4 semanas. */
export const VENTA_EN_EL_AIRE: readonly { semana: string; pesos: number }[] = [
  { semana: 'Semana 1', pesos: 21_300_000 },
  { semana: 'Semana 2', pesos: 17_900_000 },
  { semana: 'Semana 3', pesos: 24_600_000 },
  { semana: 'Semana 4', pesos: 19_200_000 },
];

/** Lo que recuperaron los recordatorios del agente en el mes. */
export const RECORDATORIOS = {
  dejaronDeContestar: 286,
  volvieron: 97,
  reservaron: 19,
} as const;

// ---------------------------------------------------------------------------
// Cuentas (puras, para la pantalla y los tests)
// ---------------------------------------------------------------------------

const FMT_ENTERO = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });

/** «1.285.200»: separador de miles con punto, como en Colombia. */
export function miles(n: number): string {
  // Algunos motores no traen los datos de `es-CO` y separan con coma o con
  // espacio fino: se normaliza a punto.
  return FMT_ENTERO.format(Math.round(n)).replace(/[,  \s]/g, '.');
}

/** «$19.200.000». */
export function pesos(n: number): string {
  return `$${miles(n)}`;
}

/** «$19,2 millones», para etiquetas cortas. */
export function millones(n: number): string {
  const m = Math.round(n / 100_000) / 10;
  return `$${String(m).replace('.', ',')} millones`;
}

/** Porcentaje entero de `parte` sobre `total`. */
export function porcentaje(parte: number, total: number): number {
  return total > 0 ? Math.round((parte / total) * 100) : 0;
}

/** «7 s», «14 min», «1 h 25 min», «9 h 40 min». */
export function duracion(segundos: number): string {
  if (segundos < 60) return `${Math.round(segundos)} s`;
  const min = Math.round(segundos / 60);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const resto = min % 60;
  return resto ? `${h} h ${resto} min` : `${h} h`;
}

/** Hora del día en formato corto: 0 → «12 a. m.», 13 → «1 p. m.». */
export function horaDelDia(h: number): string {
  const sufijo = h < 12 ? 'a. m.' : 'p. m.';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12} ${sufijo}`;
}

export function enHorarioDeOficina(h: number): boolean {
  return h >= HORARIO_OFICINA.desde && h < HORARIO_OFICINA.hasta;
}

/** Entre qué pasos se va más gente: el índice del paso de destino y cuántos se fueron. */
export function mayorCaida(pasos: readonly PasoReporte[] = PASOS): { indice: number; seFueron: number } {
  let mejor = { indice: 1, seFueron: -1 };
  for (let i = 1; i < pasos.length; i += 1) {
    const seFueron = pasos[i - 1].personas - pasos[i].personas;
    if (seFueron > mejor.seFueron) mejor = { indice: i, seFueron };
  }
  return mejor;
}

export function resumenReporte() {
  const totalMensajes = MENSAJES_POR_HORA.reduce((a, b) => a + b, 0);
  const fueraDeHorario = MENSAJES_POR_HORA.reduce((a, n, h) => a + (enHorarioDeOficina(h) ? 0 : n), 0);
  const enOficina = RESPUESTA_POR_FRANJA.filter((f) => f.franja === '9 a. m. a 1 p. m.' || f.franja === '1 a 6 p. m.');
  const asesoresOficinaMin = Math.round(enOficina.reduce((a, f) => a + f.asesoresMin, 0) / enOficina.length);
  const agenteSeg = Math.round(RESPUESTA_POR_FRANJA.reduce((a, f) => a + f.agenteSeg, 0) / RESPUESTA_POR_FRANJA.length);
  const aire = VENTA_EN_EL_AIRE.map((s) => s.pesos);
  return {
    conversaciones: PASOS[0].personas,
    reservaron: PASOS[PASOS.length - 1].personas,
    totalMensajes,
    fueraDeHorario,
    pctFueraDeHorario: porcentaje(fueraDeHorario, totalMensajes),
    agenteSeg,
    asesoresOficinaMin,
    asesoresNocheMin: RESPUESTA_POR_FRANJA[RESPUESTA_POR_FRANJA.length - 1].asesoresMin,
    ventaAireUltimaSemana: aire[aire.length - 1],
    ventaAirePromedio: Math.round(aire.reduce((a, b) => a + b, 0) / aire.length),
    recuperadoPesos: RECORDATORIOS.reservaron * TICKET_PROMEDIO,
  };
}
