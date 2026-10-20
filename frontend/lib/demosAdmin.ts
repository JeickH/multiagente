/**
 * Panel privado «Demos web» (`/demos`, Sprint 32, #630): tipos del contrato y
 * lógica pura (rangos en hora de Colombia, query, etapas, formatos). Sin
 * React, para poder probarlo (`demosAdmin.test.ts`).
 *
 * Contrato (backend #627, detrás de `require_gloma_account`):
 *   GET /admin/demos/access          → {allowed}
 *   GET /admin/demos?desde&hasta&incluir_internas&q&tipo&estado&etapa&page&page_size
 *       → {resumen, total, page, page_size, items}
 *   GET /admin/demos/{public_id}     → item + datos completos, productos y transcripción
 * El `resumen` depende solo del rango y de `incluir_internas`; los demás
 * filtros tocan solo `items`/`total`. Las fechas llegan en UTC sin zona: todo
 * se formatea con `lib/fechas.ts`.
 */
import { ZONA_CO, aInstante, fechaHoraCorta, horaCorta } from './fechas';

// --------------------------------------------------------------------------
// Tipos del contrato
// --------------------------------------------------------------------------

export type EstadoDemoAdmin = 'generando' | 'lista' | 'error';
export type FiltroEstado = '' | 'modelo' | 'respaldo' | 'generando' | 'error';
export type Etapa =
  | ''
  | 'conversaron'
  | 'traspaso'
  | 'whatsapp'
  | 'llamada_abierta'
  | 'llamada_agendada'
  | 'pidieron_hablar';

export interface ResumenDemos {
  demos: number;
  conversaron: number;
  traspaso: number;
  clic_whatsapp: number;
  abrieron_llamada: number;
  agendaron_llamada: number;
  pidieron_hablar: number;
  por_estado: { modelo: number; respaldo: number; generando: number; error: number };
}

export interface ItemDemo {
  public_id: string;
  created_at: string;
  nombre: string | null;
  empresa: string;
  tipo_empresa: string;
  tipo_otro: string | null;
  tipo_empresa_label: string;
  /** Enmascarado en la lista; completo en el detalle. */
  telefono: string | null;
  correo: string | null;
  acepta_promociones: boolean;
  estado: EstadoDemoAdmin;
  origen_productos: 'modelo' | 'respaldo' | null;
  turnos: number;
  traspaso_at: string | null;
  clics_whatsapp: number;
  aperturas_llamada: number;
  llamada_agendada_at: string | null;
  interna: boolean;
  lead_borrado: boolean;
}

export interface ListaDemos {
  resumen: ResumenDemos;
  total: number;
  page: number;
  page_size: number;
  items: ItemDemo[];
}

export interface ProductoAdmin {
  nombre: string;
  resumen: string | null;
  ficha: string | null;
  precio_cop: number | null;
  unidad_precio: string | null;
}

export interface MensajeTranscripcion {
  rol: 'usuario' | 'bot';
  texto: string;
  at: string | null;
}

export interface DetalleDemo extends ItemDemo {
  acepto_contacto_at: string | null;
  acepta_promociones_at: string | null;
  consent_version: string | null;
  lista_at: string | null;
  primer_clic_whatsapp_at: string | null;
  primer_apertura_llamada_at: string | null;
  productos: ProductoAdmin[];
  transcripcion: MensajeTranscripcion[];
}

// --------------------------------------------------------------------------
// Rango de fechas (días de Colombia)
// --------------------------------------------------------------------------

export type PresetRango = 'hoy' | '7' | '30' | 'custom';

/** Tope del rango personalizado (el backend rechaza más de 366 días). */
export const MAX_DIAS_RANGO = 366;

/** «AAAA-MM-DD» del día de calendario en Colombia para ese instante. */
export function diaColombia(instante: Date): string {
  return instante.toLocaleDateString('en-CA', { timeZone: ZONA_CO });
}

/** Suma días a una fecha pura «AAAA-MM-DD» (sin zonas: mediodía UTC). */
export function sumarDias(dia: string, n: number): string {
  const d = new Date(`${dia}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Días de calendario incluidos en `desde..hasta` (1 si son el mismo día). */
export function diasEnRango(desde: string, hasta: string): number {
  return Math.round((Date.parse(`${hasta}T12:00:00Z`) - Date.parse(`${desde}T12:00:00Z`)) / 86400000) + 1;
}

/**
 * `desde`/`hasta` para un preset, en días de Colombia. «Hoy» es el día
 * calendario de Bogotá aunque el navegador esté en otra zona.
 */
export function rangoDe(
  preset: PresetRango,
  ahora: Date,
  custom?: { desde: string; hasta: string },
): { desde: string; hasta: string } {
  const hoy = diaColombia(ahora);
  if (preset === 'hoy') return { desde: hoy, hasta: hoy };
  if (preset === '7') return { desde: sumarDias(hoy, -6), hasta: hoy };
  if (preset === '30') return { desde: sumarDias(hoy, -29), hasta: hoy };
  return custom ?? { desde: sumarDias(hoy, -29), hasta: hoy };
}

/** Por qué un rango personalizado no sirve, o `null` si sirve. */
export function errorDeRango(desde: string, hasta: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(desde) || !/^\d{4}-\d{2}-\d{2}$/.test(hasta)) return 'Elige las dos fechas.';
  if (desde > hasta) return 'La fecha «desde» va antes de «hasta».';
  if (diasEnRango(desde, hasta) > MAX_DIAS_RANGO) return 'El rango no puede pasar de un año.';
  return null;
}

// --------------------------------------------------------------------------
// Query
// --------------------------------------------------------------------------

export interface FiltrosDemos {
  desde: string;
  hasta: string;
  incluirInternas: boolean;
  q: string;
  tipo: string;
  estado: FiltroEstado;
  etapa: Etapa;
  pagina: number;
  porPagina: number;
}

export function queryDemos(f: FiltrosDemos): string {
  const p = new URLSearchParams();
  p.set('desde', f.desde);
  p.set('hasta', f.hasta);
  p.set('incluir_internas', f.incluirInternas ? 'true' : 'false');
  const q = f.q.trim();
  if (q) p.set('q', q.slice(0, 100));
  if (f.tipo) p.set('tipo', f.tipo);
  if (f.estado) p.set('estado', f.estado);
  if (f.etapa) p.set('etapa', f.etapa);
  p.set('page', String(Math.max(1, f.pagina)));
  p.set('page_size', String(Math.min(100, Math.max(1, f.porPagina))));
  return p.toString();
}

// --------------------------------------------------------------------------
// Derivaciones para pintar
// --------------------------------------------------------------------------

/** Etiqueta única del estado de generación (nunca solo color). */
export function estadoVisible(
  item: Pick<ItemDemo, 'estado' | 'origen_productos'>,
): { clave: Exclude<FiltroEstado, ''>; texto: string } {
  if (item.estado === 'generando') return { clave: 'generando', texto: 'Generando' };
  if (item.estado === 'error') return { clave: 'error', texto: 'Error' };
  if (item.origen_productos === 'respaldo') return { clave: 'respaldo', texto: 'Lista · respaldo' };
  return { clave: 'modelo', texto: 'Lista' };
}

export interface PasoRecorrido {
  clave: 'traspaso' | 'whatsapp' | 'llamada_abierta' | 'llamada_agendada';
  texto: string;
  /** El más fuerte del recorrido (agendó) va resaltado. */
  fuerte?: boolean;
}

/**
 * Chips de la columna «Recorrido»: solo lo que pasó. Se cuentan demos, no
 * clics; los clics repetidos solo se ven aquí como «×N». Si agendó, el chip
 * de «abrió el agendador» sobra.
 */
export function recorridoDe(
  item: Pick<ItemDemo, 'traspaso_at' | 'clics_whatsapp' | 'aperturas_llamada' | 'llamada_agendada_at'>,
): PasoRecorrido[] {
  const out: PasoRecorrido[] = [];
  if (item.traspaso_at) out.push({ clave: 'traspaso', texto: 'Traspaso' });
  if (item.clics_whatsapp > 0) {
    out.push({ clave: 'whatsapp', texto: `WhatsApp${item.clics_whatsapp > 1 ? ` ×${item.clics_whatsapp}` : ''}` });
  }
  if (item.llamada_agendada_at) out.push({ clave: 'llamada_agendada', texto: 'Agendó llamada', fuerte: true });
  else if (item.aperturas_llamada > 0) {
    out.push({
      clave: 'llamada_abierta',
      texto: `Abrió agendador${item.aperturas_llamada > 1 ? ` ×${item.aperturas_llamada}` : ''}`,
    });
  }
  return out;
}

/** Texto cuando no hay chips: «Solo conversó», «No escribió» o «—». */
export function recorridoVacio(item: Pick<ItemDemo, 'estado' | 'turnos'>): string {
  if (item.estado !== 'lista') return '—';
  return item.turnos > 0 ? 'Solo conversó' : 'No escribió';
}

/** ¿La demo cumple la etapa? (la misma regla que aplica el backend). */
export function cumpleEtapa(item: ItemDemo, etapa: Etapa): boolean {
  switch (etapa) {
    case '':
      return true;
    case 'conversaron':
      return item.turnos > 0;
    case 'traspaso':
      return Boolean(item.traspaso_at);
    case 'whatsapp':
      return item.clics_whatsapp > 0;
    case 'llamada_abierta':
      return item.aperturas_llamada > 0;
    case 'llamada_agendada':
      return Boolean(item.llamada_agendada_at);
    case 'pidieron_hablar':
      return item.clics_whatsapp > 0 || item.aperturas_llamada > 0;
    default:
      return true;
  }
}

/** «Otro: escuela de surf» o la etiqueta del backend. */
export function tipoTexto(item: Pick<ItemDemo, 'tipo_empresa' | 'tipo_empresa_label' | 'tipo_otro'>): string {
  if (item.tipo_empresa === 'otro' && item.tipo_otro?.trim()) return `Otro: ${item.tipo_otro.trim()}`;
  return item.tipo_empresa_label || item.tipo_empresa;
}

/** «44 %» o «—» si no hay base. */
export function pct(parte: number, base: number): string {
  if (!base) return '—';
  return `${Math.round((parte / base) * 100)} %`;
}

export function formatoCop(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return '';
  return `$${Math.round(Number(valor)).toLocaleString('es-CO')}`;
}

/** «Hoy, 4:26 p. m.», «Ayer, …» o «20 ago, 4:26 p. m.» en hora de Colombia. */
export function cuando(iso: string | null | undefined, ahora: Date = new Date()): string {
  const d = aInstante(iso);
  if (!d) return '';
  const dia = diaColombia(d);
  const hoy = diaColombia(ahora);
  if (dia === hoy) return `Hoy, ${horaCorta(iso)}`;
  if (dia === sumarDias(hoy, -1)) return `Ayer, ${horaCorta(iso)}`;
  return fechaHoraCorta(iso);
}

/** Primer nombre, para el saludo y la burbuja del chat. */
export function primerNombre(nombre: string | null | undefined): string {
  return (nombre || '').trim().split(/\s+/)[0] || '';
}

/**
 * wa.me al prospecto (solo en el detalle, junto al consentimiento). El texto
 * lleva solo el saludo y el primer nombre: nada de productos ni de la
 * conversación. Un número de 10 dígitos que empieza por 3 es un celular de
 * Colombia sin indicativo; se le antepone 57. Si no quedan 7-15 dígitos,
 * `null` (no se ofrece el botón).
 */
export function enlaceWhatsappProspecto(telefono: string | null | undefined, nombre: string | null | undefined): string | null {
  let digitos = (telefono || '').replace(/\D/g, '');
  if (digitos.length === 10 && digitos.startsWith('3')) digitos = `57${digitos}`;
  if (digitos.length < 7 || digitos.length > 15) return null;
  const pila = primerNombre(nombre);
  const texto = pila
    ? `Hola, ${pila}. Te escribo de Gloma por la demo que armaste.`
    : 'Hola. Te escribo de Gloma por la demo que armaste.';
  return `https://wa.me/${digitos}?text=${encodeURIComponent(texto)}`;
}

// --------------------------------------------------------------------------
// Conversación con las marcas del recorrido intercaladas
// --------------------------------------------------------------------------

export type EntradaHilo =
  | { tipo: 'mensaje'; rol: 'usuario' | 'bot'; texto: string; at: string | null; orden: number }
  | { tipo: 'marca'; texto: string; at: string; orden: number };

/**
 * Mensajes y marcas («Traspaso a asesor», «Clic en WhatsApp», «Abrió el
 * agendador», «Agendó una llamada») en orden de hora. A igual hora, la marca
 * va después del mensaje. Los mensajes sin hora conservan su lugar.
 */
export function hiloConMarcas(d: DetalleDemo): EntradaHilo[] {
  const ms = (iso: string | null) => aInstante(iso)?.getTime() ?? null;
  const mensajes: EntradaHilo[] = d.transcripcion.map((m, i) => ({
    tipo: 'mensaje',
    rol: m.rol,
    texto: m.texto,
    at: m.at,
    orden: i,
  }));
  const marcas: EntradaHilo[] = [];
  const marca = (at: string | null, texto: string) => {
    if (at) marcas.push({ tipo: 'marca', texto, at, orden: 0 });
  };
  marca(d.traspaso_at, 'Traspaso a asesor');
  marca(
    d.primer_clic_whatsapp_at,
    `Clic en «Hablar con un asesor» (WhatsApp)${d.clics_whatsapp > 1 ? ` (${d.clics_whatsapp} veces)` : ''}`,
  );
  marca(
    d.primer_apertura_llamada_at,
    `Abrió el agendador de llamada${d.aperturas_llamada > 1 ? ` (${d.aperturas_llamada} veces)` : ''}`,
  );
  marca(d.llamada_agendada_at, 'Agendó una llamada (reportada por el navegador)');

  // Cada marca se inserta después del último mensaje con hora <= a la suya.
  const out = [...mensajes];
  for (const m of marcas.sort((a, b) => (ms(a.at) ?? 0) - (ms(b.at) ?? 0))) {
    const t = ms(m.at) ?? 0;
    let idx = out.length;
    for (let i = 0; i < out.length; i += 1) {
      const ti = ms(out[i].at);
      if (ti !== null && ti > t) {
        idx = i;
        break;
      }
    }
    out.splice(idx, 0, m);
  }
  return out.map((e, i) => ({ ...e, orden: i }));
}
