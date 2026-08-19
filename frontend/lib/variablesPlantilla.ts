/**
 * Variables de una plantilla de WhatsApp, en cristiano.
 *
 * Meta numera los huecos de una plantilla: `Hola {{1}}, tu viaje a {{2}}…`.
 * La campaña guarda en `campaigns.template_variables_json` qué va en cada
 * hueco: `{"1": "{{contact.name}}", "2": "Cartagena"}`.
 *
 * El formato guardado NO cambia — el backend sigue recibiendo exactamente lo
 * mismo. Lo que cambia es que la usuaria ya no lo escribe a mano: elige de una
 * lista y este módulo traduce en las dos direcciones. Todo lo que sepa de esa
 * convención vive aquí para que no vuelva a quedar repartido por las pantallas.
 *
 * Convención de tokens (la misma que emite `GET /contacts/campos`):
 *   {{contact.name}}              → nombre del contacto
 *   {{contact.phone}}             → teléfono del contacto
 *   {{contact.attributes.Ciudad}} → un atributo, por su nombre exacto
 * Cualquier otra cosa es texto fijo, tal cual, igual para todos.
 */
import { maskPhone } from './format';

export const TOKEN_NOMBRE = '{{contact.name}}';
export const TOKEN_TELEFONO = '{{contact.phone}}';

const PREFIJO_ATRIBUTO = '{{contact.attributes.';

/** Token del atributo `Ciudad` → `{{contact.attributes.Ciudad}}`. */
export function tokenAtributo(nombre: string): string {
  return `${PREFIJO_ATRIBUTO}${nombre}}}`;
}

/** Datos mínimos de un contacto para resolver un token. */
export interface ContactoParaVista {
  name: string | null;
  phone_e164: string;
  attributes: Record<string, unknown>;
}

/**
 * Lo que la usuaria eligió para un hueco de la plantilla.
 * `origen === 'texto'` guarda el literal; los demás guardan un token.
 */
export type OrigenVariable = 'texto' | 'name' | 'phone_e164' | string;

export interface SeleccionVariable {
  origen: OrigenVariable;
  /** Solo se usa cuando `origen === 'texto'`. */
  texto: string;
}

/** Convierte la selección de la UI al string que se guarda en el backend. */
export function aValorGuardado(sel: SeleccionVariable): string {
  if (sel.origen === 'texto') return sel.texto;
  if (sel.origen === 'name') return TOKEN_NOMBRE;
  if (sel.origen === 'phone_e164') return TOKEN_TELEFONO;
  return tokenAtributo(sel.origen);
}

/** El camino de vuelta: lo guardado → cómo se pinta el selector. */
export function desdeValorGuardado(valor: string | undefined): SeleccionVariable {
  const v = (valor ?? '').trim();
  if (!v) return { origen: 'texto', texto: '' };
  if (v === TOKEN_NOMBRE) return { origen: 'name', texto: '' };
  if (v === TOKEN_TELEFONO) return { origen: 'phone_e164', texto: '' };
  if (v.startsWith(PREFIJO_ATRIBUTO) && v.endsWith('}}')) {
    const nombre = v.slice(PREFIJO_ATRIBUTO.length, -2);
    if (nombre) return { origen: nombre, texto: '' };
  }
  return { origen: 'texto', texto: valor ?? '' };
}

/**
 * Resuelve un valor guardado contra un contacto real, para la vista previa.
 *
 * El teléfono sale enmascarado a propósito (regla 1): la vista previa es para
 * revisar la redacción, no para leer el número de nadie. En el envío real el
 * backend usa el dato completo.
 */
export function resolverValor(
  valor: string | undefined,
  contacto: ContactoParaVista | null,
): string {
  const sel = desdeValorGuardado(valor);
  if (sel.origen === 'texto') return sel.texto;
  if (!contacto) return '…';
  if (sel.origen === 'name') return contacto.name || '(sin nombre)';
  if (sel.origen === 'phone_e164') return maskPhone(contacto.phone_e164);
  const bruto = contacto.attributes?.[sel.origen];
  if (bruto === undefined || bruto === null || bruto === '') return '(sin dato)';
  return String(bruto);
}

/** Los huecos que trae el cuerpo: `Hola {{1}} y {{2}}` → `['1','2']`. */
export function clavesDeVariables(cuerpo: string): string[] {
  const encontradas = cuerpo.match(/\{\{\s*(\d+)\s*\}\}/g) || [];
  const claves = new Set<string>();
  for (const m of encontradas) {
    const n = m.replace(/[^0-9]/g, '');
    if (n) claves.add(n);
  }
  return Array.from(claves).sort((a, b) => Number(a) - Number(b));
}

export interface SegmentoCuerpo {
  tipo: 'texto' | 'variable';
  valor: string;
  /** Solo en `variable`: el número del hueco. */
  clave?: string;
}

/**
 * Parte el cuerpo en trozos para poder resaltar una variable en pantalla.
 * `Hola {{1}}!` → `[texto "Hola ", variable "1", texto "!"]`.
 */
export function segmentarCuerpo(cuerpo: string): SegmentoCuerpo[] {
  const salida: SegmentoCuerpo[] = [];
  const regex = /\{\{\s*(\d+)\s*\}\}/g;
  let ultimo = 0;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(cuerpo)) !== null) {
    if (m.index > ultimo) {
      salida.push({ tipo: 'texto', valor: cuerpo.slice(ultimo, m.index) });
    }
    salida.push({ tipo: 'variable', valor: m[0], clave: m[1] });
    ultimo = m.index + m[0].length;
  }
  if (ultimo < cuerpo.length) {
    salida.push({ tipo: 'texto', valor: cuerpo.slice(ultimo) });
  }
  return salida;
}

/**
 * El pedacito de plantilla alrededor de un hueco, para resaltarlo en pantalla
 * sin repetir el mensaje entero por cada variable.
 * `Hola {{1}}, tu viaje…` con clave `1` → `{ antes: 'Hola ', despues: ', tu viaje…' }`.
 */
export function contextoDeVariable(
  cuerpo: string,
  clave: string,
  margen = 45,
): { antes: string; despues: string } | null {
  const regex = new RegExp(`\\{\\{\\s*${clave}\\s*\\}\\}`);
  const m = regex.exec(cuerpo);
  if (!m) return null;
  const inicio = m.index;
  const fin = inicio + m[0].length;
  let antes = cuerpo.slice(Math.max(0, inicio - margen), inicio);
  let despues = cuerpo.slice(fin, fin + margen);
  if (inicio - margen > 0) antes = `…${antes}`;
  if (fin + margen < cuerpo.length) despues = `${despues}…`;
  return { antes, despues };
}

/** El mensaje ya armado con los datos de un contacto de ejemplo. */
export function renderizarVistaPrevia(
  cuerpo: string,
  valores: Record<string, string>,
  contacto: ContactoParaVista | null,
): string {
  return segmentarCuerpo(cuerpo)
    .map((seg) => {
      if (seg.tipo === 'texto') return seg.valor;
      const resuelto = resolverValor(valores[seg.clave as string], contacto);
      return resuelto || `{{${seg.clave}}}`;
    })
    .join('');
}
