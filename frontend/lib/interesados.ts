/**
 * Interesados (estrategia #22): tipos del contrato y la lógica que no es UI.
 *
 * Un interesado es una conversación a la que el bot le notó intención de compra
 * y que, `umbral_horas` después de su primer mensaje, sigue abierta con el bot.
 * Lo que la asesora necesita saber de cada uno es **cuánto le queda para
 * escribirle por WhatsApp**: la ventana de 24 h desde el último mensaje del
 * cliente. Pasada la ventana solo le queda llamar o mandar plantilla.
 *
 * Todo lo que sigue es puro (sin React, sin `fetch`) para poder probarlo con el
 * reloj congelado: el orden lo da el backend y aquí solo se agrupa, se mide la
 * ventana y se escribe en palabras.
 *
 * Fechas: el backend manda UTC **sin marcar la zona**. Todo pasa por
 * `aInstante` de `lib/fechas.ts`, que le pone la `Z` que falta; leerlas con
 * `new Date(iso)` las correría cinco horas.
 */

import { aInstante } from './fechas';

// ---------------------------------------------------------------------------
// Contrato HTTP (spec compartida, "Contrato HTTP de Interesados")
// ---------------------------------------------------------------------------

export type EstadoInteresado = 'por_contactar' | 'contactado' | 'descartado';

export type Interesado = {
  id: number;
  conversation_id: number;
  contacto: string | null;
  telefono: string;
  tipos: string[];
  fragmento: string | null;
  resumen: string | null;
  detectado_at: string;
  conversacion_inicio_at: string;
  interesado_desde: string;
  ultimo_mensaje_cliente_at: string | null;
  ventana_cierra_at: string | null;
  interes: { mes?: string | null; hotel?: string | null } | null;
  bot: { id: number; nombre: string } | null;
  estado: EstadoInteresado;
  gestionado_por: string | null;
  gestionado_at: string | null;
  motivo_descarte: string | null;
};

export type RespuestaInteresados = {
  habilitado: boolean;
  interesados: Interesado[];
  total: number;
  pagina: number;
  por_pagina: number;
  resumen: {
    por_contactar: number;
    urgentes: number;
    ventana_cerrada: number;
    /** No está en el contrato de hoy; si el backend lo agrega, se pinta. */
    contactados_hoy?: number;
  };
  generado_at: string;
  umbral_horas: number;
  puede_tomar: boolean;
};

// ---------------------------------------------------------------------------
// Reloj del servidor
// ---------------------------------------------------------------------------

/**
 * Cuánto va adelantado (o atrasado) el servidor respecto a este navegador.
 *
 * La ventana se mide contra la hora del servidor, no la del equipo de la
 * asesora: un portátil con la hora corrida 20 minutos haría ver "Quedan 10 min"
 * a alguien a quien ya no se le puede escribir. Se calcula una vez por
 * respuesta (`generado_at - Date.now()` al recibirla) y se suma a cada tic.
 */
export function desfaseServidor(generadoAt: string | null | undefined, ahoraLocal: number): number {
  const g = aInstante(generadoAt);
  return g ? g.getTime() - ahoraLocal : 0;
}

// ---------------------------------------------------------------------------
// Ventana de WhatsApp
// ---------------------------------------------------------------------------

export const HORA_MS = 3_600_000;
export const MINUTO_MS = 60_000;
export const VENTANA_MS = 24 * HORA_MS;

/** Menos de esto es urgente (rojo). Igual al `urgentes` del backend. */
export const UMBRAL_URGENTE_MS = 3 * HORA_MS;
/** Hasta esto es "pronto" (ámbar); más es "con tiempo" (menta). */
export const UMBRAL_PRONTO_MS = 8 * HORA_MS;

export type NivelVentana = 'urgente' | 'pronto' | 'con_tiempo' | 'cerrada';

/**
 * Milisegundos que le quedan a la ventana, negativos si ya se cerró, o `null`
 * si no se sabe (el cliente nunca escribió: no hay ventana que medir).
 */
export function msRestantes(
  ventanaCierraAt: string | null | undefined,
  ahoraServidor: number,
): number | null {
  const cierre = aInstante(ventanaCierraAt);
  return cierre ? cierre.getTime() - ahoraServidor : null;
}

/**
 * Tres niveles, no un degradé: lo que la asesora necesita es saber cuántos son
 * "ya", no comparar 5 h 10 min con 5 h 40 min. Sin dato de ventana se trata
 * como cerrada: no se le puede prometer que todavía puede escribirle.
 */
export function nivelVentana(ms: number | null): NivelVentana {
  if (ms === null || ms <= 0) return 'cerrada';
  if (ms < UMBRAL_URGENTE_MS) return 'urgente';
  if (ms <= UMBRAL_PRONTO_MS) return 'pronto';
  return 'con_tiempo';
}

/** Fracción (0–100) que queda de las 24 h, para la barrita del reloj. */
export function porcentajeVentana(ms: number | null): number {
  if (ms === null || ms <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((ms / VENTANA_MS) * 100)));
}

/**
 * "1 h 50 min", "40 min", "15 h". Desde 10 h se omiten los minutos: a esa
 * distancia el minuto no cambia nada y alarga la etiqueta en el celular.
 * Se redondea hacia abajo: decir "Quedan 2 h" cuando quedan 1 h 59 min es
 * prometer un minuto que no existe.
 */
export function duracionCorta(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / MINUTO_MS));
  const horas = Math.floor(totalMin / 60);
  const min = totalMin % 60;
  if (horas >= 48) return `${Math.floor(horas / 24)} días`;
  if (horas >= 10) return `${horas} h`;
  if (horas === 0) return `${min} min`;
  return min === 0 ? `${horas} h` : `${horas} h ${min} min`;
}

/** La etiqueta grande del reloj. */
export function textoReloj(ms: number | null): string {
  if (ms === null) return 'Sin mensajes del cliente';
  if (ms <= 0) return `Cerrada hace ${duracionCorta(-ms)}`;
  if (ms < MINUTO_MS) return 'Queda menos de 1 min';
  return `Quedan ${duracionCorta(ms)}`;
}

/** "hace 21 h", "hace 30 min", "hace un momento" — para los metadatos. */
export function haceTexto(iso: string | null | undefined, ahoraServidor: number): string {
  const d = aInstante(iso);
  if (!d) return '';
  const ms = ahoraServidor - d.getTime();
  if (ms < MINUTO_MS) return 'hace un momento';
  return `hace ${duracionCorta(ms)}`;
}

// ---------------------------------------------------------------------------
// Agrupación (el orden lo da el backend)
// ---------------------------------------------------------------------------

export type Grupo = {
  nivel: NivelVentana;
  items: Interesado[];
};

const ORDEN_GRUPOS: NivelVentana[] = ['urgente', 'pronto', 'con_tiempo', 'cerrada'];

/**
 * Parte la página recibida en Urgente / Pronto / Con tiempo / Ventana cerrada
 * **sin reordenar**: dentro de cada grupo queda el orden del backend (ventana
 * abierta por cierre ascendente; cerradas por último mensaje descendente).
 *
 * Se recalcula con cada tic del reloj, así una tarjeta cuya ventana se cierra
 * con la página abierta pasa sola al grupo plegado y su botón cambia a
 * "Llamar". Como el backend la mandaba primera entre las abiertas, cae primera
 * entre las cerradas, que es justo el orden "último mensaje descendente".
 * Los grupos vacíos no se devuelven.
 */
export function agrupar(interesados: Interesado[], ahoraServidor: number): Grupo[] {
  const porNivel: Record<NivelVentana, Interesado[]> = {
    urgente: [],
    pronto: [],
    con_tiempo: [],
    cerrada: [],
  };
  for (const it of interesados) {
    porNivel[nivelVentana(msRestantes(it.ventana_cierra_at, ahoraServidor))].push(it);
  }
  return ORDEN_GRUPOS.filter((n) => porNivel[n].length > 0).map((nivel) => ({
    nivel,
    items: porNivel[nivel],
  }));
}

// ---------------------------------------------------------------------------
// Textos
// ---------------------------------------------------------------------------

export const SENALES: Record<string, { icono: string; texto: string }> = {
  anticipo: { icono: '💰', texto: 'Preguntó por el anticipo' },
  reservar: { icono: '✅', texto: 'Pidió reservar' },
  fecha_concreta: { icono: '📅', texto: 'Preguntó por una fecha' },
  datos: { icono: '📝', texto: 'Dejó sus datos' },
  // El wireframe lo llamó así; el contrato final dice `datos`. Se aceptan los dos.
  datos_entregados: { icono: '📝', texto: 'Dejó sus datos' },
};

export function textoSenal(tipo: string): string {
  const s = SENALES[tipo];
  return s ? `${s.icono} ${s.texto}` : tipo;
}

export const MOTIVOS_DESCARTE: { valor: string; texto: string }[] = [
  { valor: 'no_interesa', texto: 'No le interesa' },
  { valor: 'ya_compro', texto: 'Ya compró' },
  { valor: 'numero_equivocado', texto: 'Número equivocado' },
  { valor: 'otro', texto: 'Otro motivo' },
];

export function textoMotivo(motivo: string | null | undefined): string {
  if (!motivo) return '';
  return MOTIVOS_DESCARTE.find((m) => m.valor === motivo)?.texto ?? motivo;
}

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

/**
 * "2026-12" → "diciembre". Es un mes de calendario, no un instante: se parte
 * el texto en vez de pasarlo por `Date` (que lo leería como medianoche UTC y
 * en Colombia lo pintaría en noviembre).
 */
export function textoMes(mes: string | null | undefined): string {
  if (!mes) return '';
  const m = /^(\d{4})-(\d{1,2})/.exec(mes);
  if (!m) return mes;
  return MESES[Number(m[2]) - 1] ?? mes;
}

/** "diciembre · Amor de Dios", o `null` si no se sabe qué le interesa. */
export function textoInteres(interes: Interesado['interes']): string | null {
  if (!interes) return null;
  const partes = [textoMes(interes.mes), interes.hotel || ''].filter(Boolean);
  return partes.length ? partes.join(' · ') : null;
}

/** Lo que va de título en la tarjeta: el nombre, o el teléfono si no hay. */
export function nombreVisible(it: Pick<Interesado, 'contacto' | 'telefono'>): string {
  return it.contacto?.trim() || `+${it.telefono}`;
}

// ---------------------------------------------------------------------------
// Pestaña inicial
// ---------------------------------------------------------------------------

export type Vista = 'interesados' | 'llamadas';

/**
 * Qué pestaña abrir. Si la URL dice cuál, esa (salvo que Interesados no esté
 * habilitado en la cuenta). Sin parámetro: Interesados cuando hay alguno por
 * contactar — para que la pestaña no se quede sin mirar —; si no, Llamadas.
 */
export function vistaInicial(
  pedida: string | string[] | undefined,
  habilitado: boolean,
  porContactar: number,
): Vista {
  const v = Array.isArray(pedida) ? pedida[0] : pedida;
  if (!habilitado) return 'llamadas';
  if (v === 'interesados' || v === 'llamadas') return v;
  return porContactar > 0 ? 'interesados' : 'llamadas';
}

// ---------------------------------------------------------------------------
// Errores al cargar
// ---------------------------------------------------------------------------

/**
 * ¿Vale la pena reintentar? Solo 5xx y fallas de red: la primera petición a
 * `/api/*` después de un rato puede dar 500 por el arranque en frío del SSR de
 * Amplify con el backend sano. Un 4xx no se arregla reintentando.
 */
export function esReintentable(e: unknown): boolean {
  const status = (e as { status?: unknown } | null)?.status;
  if (typeof status === 'number') return status >= 500;
  return true; // TypeError de fetch: sin red / conexión cortada
}
