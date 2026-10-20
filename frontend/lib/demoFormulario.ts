/**
 * Datos y validación del formulario de la demo (`/demo`, #614). Sin React,
 * para poder probarlos con vitest (`demoApi.test.ts`).
 */
import { DEMO_UI, TIPOS_EMPRESA } from './demo_copy';
import { PAIS_POR_DEFECTO, normalizarTelefono } from './telefonoPais';

export interface DatosFormulario {
  nombre: string;
  empresa: string;
  tipo_empresa: string;
  tipo_otro: string;
  /** Número nacional tal como lo escribió (o pegó) la persona. */
  telefono: string;
  /** ISO del país del teléfono (`CO` por defecto, `OTRO` para escribir el indicativo). */
  telefono_pais: string;
  /** Solo con `telefono_pais = 'OTRO'`. */
  telefono_indicativo: string;
  correo: string;
  acepta_contacto: boolean;
  acepta_promociones: boolean;
  sitio_web: string;
}

export const FORMULARIO_VACIO: DatosFormulario = {
  nombre: '',
  empresa: '',
  tipo_empresa: '',
  tipo_otro: '',
  telefono: '',
  telefono_pais: PAIS_POR_DEFECTO,
  telefono_indicativo: '',
  correo: '',
  acepta_contacto: false,
  acepta_promociones: false,
  sitio_web: '',
};

export type AlertaFormulario = null | 'red' | 'tope' | 'verificacion';

export type Campo = 'nombre' | 'empresa' | 'tipo_empresa' | 'telefono' | 'correo' | 'acepta_contacto';
export const ORDEN_CAMPOS: Campo[] = ['nombre', 'empresa', 'tipo_empresa', 'telefono', 'correo', 'acepta_contacto'];
const E = DEMO_UI.form.errores;

/** Reglas del wireframe. Teléfono: 7 a 15 dígitos, sin forzar +57 (LatAm). */
export function validarCampo(campo: Campo, d: DatosFormulario): string {
  switch (campo) {
    case 'nombre':
      return d.nombre.trim() ? '' : E.nombre;
    case 'empresa':
      return d.empresa.trim() ? '' : E.empresa;
    case 'tipo_empresa':
      return TIPOS_EMPRESA.some((t) => t.clave === d.tipo_empresa) ? '' : E.tipo;
    case 'telefono': {
      const r = normalizarTelefono(d.telefono_pais, d.telefono_indicativo, d.telefono);
      switch (r.error) {
        case null:
          return '';
        case 'vacio':
          return E.telefonoVacio;
        case 'colombia':
          return E.telefonoColombia;
        case 'indicativo':
          return E.telefonoIndicativo;
        case 'largo':
          return E.telefonoLargo
            .replace('{pais}', r.pais.nombre)
            .replace('{digitos}', r.pais.min === r.pais.max ? String(r.pais.min) : `${r.pais.min} a ${r.pais.max}`);
        default:
          return E.telefonoInvalido;
      }
    }
    case 'correo':
      if (!d.correo.trim()) return E.correoVacio;
      return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(d.correo.trim()) ? '' : E.correoInvalido;
    case 'acepta_contacto':
      return d.acepta_contacto ? '' : E.contacto;
    default:
      return '';
  }
}


/** Palabras que no cuentan para las iniciales del avatar del chat. */
const PALABRAS_VACIAS = new Set(['el', 'la', 'los', 'las', 'de', 'del', 'y', '&']);
/** Sufijos societarios, comparados sin puntos: «S.A.S.» → «sas». */
const SUFIJOS_SOCIETARIOS = new Set(['sas', 'ltda', 'sa']);

/**
 * Iniciales del avatar de la cabecera del chat: «Posada El Colibrí» → «PC»
 * (no «PE»), «Viajes del Sol S.A.S.» → «VS». Si todo lo que hay son palabras
 * vacías, usa las palabras tal cual; si no queda nada, «G».
 */
export function inicialesEmpresa(empresa: string): string {
  const palabras = empresa.split(/\s+/).filter(Boolean);
  const utiles = palabras.filter((p) => {
    const norm = p.toLowerCase().replace(/[.,]/g, '');
    return norm && !PALABRAS_VACIAS.has(norm) && !SUFIJOS_SOCIETARIOS.has(norm);
  });
  const base = utiles.length > 0 ? utiles : palabras;
  const ini = base
    .slice(0, 2)
    .map((p) => Array.from(p)[0] || '')
    .join('')
    .toUpperCase();
  return ini || 'G';
}

/** El teléfono en E.164 para `POST /demo/iniciar`, o `null` si no es válido. */
export function telefonoE164(d: Pick<DatosFormulario, 'telefono' | 'telefono_pais' | 'telefono_indicativo'>): string | null {
  return normalizarTelefono(d.telefono_pais, d.telefono_indicativo, d.telefono).e164;
}
