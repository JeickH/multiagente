/**
 * Teléfono con país para el formulario de la demo (#634). Sin React, para
 * probarlo (`demoApi.test.ts`).
 *
 * El formulario pide el país (Colombia por defecto) y el número nacional, y
 * manda el número en E.164 (`+573001234567`), que es lo que guarda el backend
 * (`normalizar_telefono` en `backend/app/routers/demo.py`: 8 a 15 dígitos, sin
 * empezar por 0).
 *
 * Los largos son del número NACIONAL (sin indicativo ni el 0 de larga
 * distancia) y son rangos razonables, no un validador de numeración: lo único
 * que se quiere es atajar el número a medias o con dígitos de más. Colombia sí
 * va con regla exacta porque es casi todo el tráfico: 10 dígitos, celular 3XX o
 * fijo 60X.
 */

export interface PaisTelefono {
  iso: string;
  nombre: string;
  /** Solo dígitos, sin «+». Vacío en «Otro» (lo escribe la persona). */
  indicativo: string;
  bandera: string;
  min: number;
  max: number;
  /** Para el placeholder. */
  ejemplo: string;
}

export const PAIS_OTRO = 'OTRO';
export const PAIS_POR_DEFECTO = 'CO';

/** Colombia primero (es el mercado), después en orden alfabético, y «Otro» al final. */
export const PAISES_TELEFONO: readonly PaisTelefono[] = [
  { iso: 'CO', nombre: 'Colombia', indicativo: '57', bandera: '🇨🇴', min: 10, max: 10, ejemplo: '300 123 4567' },
  { iso: 'AR', nombre: 'Argentina', indicativo: '54', bandera: '🇦🇷', min: 10, max: 11, ejemplo: '11 2345 6789' },
  { iso: 'BO', nombre: 'Bolivia', indicativo: '591', bandera: '🇧🇴', min: 8, max: 8, ejemplo: '7123 4567' },
  { iso: 'BR', nombre: 'Brasil', indicativo: '55', bandera: '🇧🇷', min: 10, max: 11, ejemplo: '11 91234 5678' },
  { iso: 'CA', nombre: 'Canadá', indicativo: '1', bandera: '🇨🇦', min: 10, max: 10, ejemplo: '416 555 0123' },
  { iso: 'CL', nombre: 'Chile', indicativo: '56', bandera: '🇨🇱', min: 9, max: 9, ejemplo: '9 1234 5678' },
  { iso: 'CR', nombre: 'Costa Rica', indicativo: '506', bandera: '🇨🇷', min: 8, max: 8, ejemplo: '8312 3456' },
  { iso: 'CU', nombre: 'Cuba', indicativo: '53', bandera: '🇨🇺', min: 8, max: 8, ejemplo: '5123 4567' },
  { iso: 'EC', nombre: 'Ecuador', indicativo: '593', bandera: '🇪🇨', min: 8, max: 9, ejemplo: '99 123 4567' },
  { iso: 'SV', nombre: 'El Salvador', indicativo: '503', bandera: '🇸🇻', min: 8, max: 8, ejemplo: '7012 3456' },
  { iso: 'ES', nombre: 'España', indicativo: '34', bandera: '🇪🇸', min: 9, max: 9, ejemplo: '612 34 56 78' },
  { iso: 'US', nombre: 'Estados Unidos', indicativo: '1', bandera: '🇺🇸', min: 10, max: 10, ejemplo: '201 555 0123' },
  { iso: 'GT', nombre: 'Guatemala', indicativo: '502', bandera: '🇬🇹', min: 8, max: 8, ejemplo: '5123 4567' },
  { iso: 'HN', nombre: 'Honduras', indicativo: '504', bandera: '🇭🇳', min: 8, max: 8, ejemplo: '9123 4567' },
  { iso: 'MX', nombre: 'México', indicativo: '52', bandera: '🇲🇽', min: 10, max: 10, ejemplo: '55 1234 5678' },
  { iso: 'NI', nombre: 'Nicaragua', indicativo: '505', bandera: '🇳🇮', min: 8, max: 8, ejemplo: '8123 4567' },
  { iso: 'PA', nombre: 'Panamá', indicativo: '507', bandera: '🇵🇦', min: 7, max: 8, ejemplo: '6123 4567' },
  { iso: 'PY', nombre: 'Paraguay', indicativo: '595', bandera: '🇵🇾', min: 7, max: 9, ejemplo: '961 456789' },
  { iso: 'PE', nombre: 'Perú', indicativo: '51', bandera: '🇵🇪', min: 8, max: 9, ejemplo: '912 345 678' },
  { iso: 'PR', nombre: 'Puerto Rico', indicativo: '1', bandera: '🇵🇷', min: 10, max: 10, ejemplo: '787 234 5678' },
  { iso: 'DO', nombre: 'República Dominicana', indicativo: '1', bandera: '🇩🇴', min: 10, max: 10, ejemplo: '809 234 5678' },
  { iso: 'UY', nombre: 'Uruguay', indicativo: '598', bandera: '🇺🇾', min: 8, max: 8, ejemplo: '94 231 234' },
  { iso: 'VE', nombre: 'Venezuela', indicativo: '58', bandera: '🇻🇪', min: 10, max: 10, ejemplo: '412 123 4567' },
  { iso: PAIS_OTRO, nombre: 'Otro país', indicativo: '', bandera: '🌐', min: 4, max: 14, ejemplo: 'Número sin indicativo' },
];

export function paisPorIso(iso: string): PaisTelefono {
  return PAISES_TELEFONO.find((p) => p.iso === iso) ?? PAISES_TELEFONO[0];
}

export type ErrorTelefono = 'vacio' | 'largo' | 'colombia' | 'indicativo' | 'total';

export interface ResultadoTelefono {
  /** `+573001234567`, o `null` si no es válido. */
  e164: string | null;
  error: ErrorTelefono | null;
  pais: PaisTelefono;
}

/**
 * Normaliza lo que escribió (o pegó) la persona.
 *
 * - Si empieza por `+` o `00`, ya trae indicativo: se toma tal cual (así
 *   «+57 300…» con Colombia elegida no queda «+57 57 300…»). Si el indicativo
 *   es el del país elegido, se valida el largo de ese país.
 * - Si no, y los dígitos empiezan por el indicativo del país con el largo
 *   exacto de «indicativo + número» (p. ej. «573001234567» pegado con
 *   Colombia), se quita el indicativo repetido.
 * - Se quita el 0 de larga distancia del número nacional («011…» → «11…»).
 */
export function normalizarTelefono(isoPais: string, indicativoOtro: string, entrada: string): ResultadoTelefono {
  const pais = paisPorIso(isoPais);
  const crudo = (entrada || '').trim();
  let digitos = crudo.replace(/\D/g, '');
  if (!digitos) return { e164: null, error: 'vacio', pais };

  const otro = pais.iso === PAIS_OTRO;
  const indicativo = otro ? (indicativoOtro || '').replace(/\D/g, '') : pais.indicativo;

  // Ya viene con indicativo internacional.
  if (crudo.startsWith('+') || digitos.startsWith('00')) {
    if (!crudo.startsWith('+')) digitos = digitos.replace(/^00/, '');
    if (!otro && digitos.startsWith(indicativo)) {
      return validarNacional(pais, indicativo, digitos.slice(indicativo.length));
    }
    return validarTotal(pais, digitos);
  }

  if (!otro && digitos.startsWith(indicativo) && digitos.length - indicativo.length >= pais.min && digitos.length - indicativo.length <= pais.max) {
    // «573001234567»: el indicativo vino pegado al número.
    // Un número nacional nunca tiene ese largo, así que no hay ambigüedad.
    return validarNacional(pais, indicativo, digitos.slice(indicativo.length));
  }

  if (otro && !/^[1-9]\d{0,3}$/.test(indicativo)) return { e164: null, error: 'indicativo', pais };
  return validarNacional(pais, indicativo, digitos.replace(/^0+/, ''));
}

function esNacionalColombia(nacional: string): boolean {
  return /^(3\d{9}|60\d{8})$/.test(nacional);
}

function validarNacional(pais: PaisTelefono, indicativo: string, nacional: string): ResultadoTelefono {
  if (nacional.length < pais.min || nacional.length > pais.max) return { e164: null, error: 'largo', pais };
  if (pais.iso === 'CO' && !esNacionalColombia(nacional)) return { e164: null, error: 'colombia', pais };
  return validarTotal(pais, indicativo + nacional);
}

/** El mismo techo del backend: 8 a 15 dígitos en total y sin empezar por 0. */
function validarTotal(pais: PaisTelefono, digitos: string): ResultadoTelefono {
  if (digitos.length < 8 || digitos.length > 15 || digitos.startsWith('0')) return { e164: null, error: 'total', pais };
  return { e164: `+${digitos}`, error: null, pais };
}

/**
 * `+573001234567` → «+57 300 123 4567», para mostrarlo (#643). Separa el
 * indicativo según el país elegido (o el que escribió en «Otro») y agrupa el
 * número nacional para que se lea fácil. Si no reconoce el indicativo, lo
 * deja en un solo bloque detrás del «+».
 */
export function formatearE164(e164: string, isoPais: string, indicativoOtro = ''): string {
  const digitos = (e164 || '').replace(/\D/g, '');
  if (!digitos) return '';
  const pais = paisPorIso(isoPais);
  const candidatos = [pais.iso === PAIS_OTRO ? indicativoOtro.replace(/\D/g, '') : pais.indicativo];
  // Si pegó otro indicativo con «+», se busca entre los de la lista.
  PAISES_TELEFONO.forEach((p) => p.indicativo && candidatos.push(p.indicativo));
  const cc = candidatos.find((c) => c && digitos.startsWith(c) && digitos.length - c.length >= 4);
  if (!cc) return `+${digitos}`;
  return `+${cc} ${agrupar(digitos.slice(cc.length))}`;
}

function agrupar(n: string): string {
  if (n.length === 10) return `${n.slice(0, 3)} ${n.slice(3, 6)} ${n.slice(6)}`;
  if (n.length === 11) return `${n.slice(0, 2)} ${n.slice(2, 7)} ${n.slice(7)}`;
  if (n.length === 9) return `${n.slice(0, 3)} ${n.slice(3, 6)} ${n.slice(6)}`;
  if (n.length === 8) return `${n.slice(0, 4)} ${n.slice(4)}`;
  return n.replace(/(\d{3})(?=\d)/g, '$1 ');
}

/** ¿El número registrado es de Colombia? (define el monto del premio). */
export function esTelefonoColombia(e164: string | null | undefined): boolean {
  return /^\+57\d{10}$/.test(e164 || '');
}
