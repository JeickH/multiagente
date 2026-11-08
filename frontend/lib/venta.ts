/**
 * Venta cerrada sobre una conversación (Sprint 36).
 *
 * La asesora marca que el chat terminó en venta —por WhatsApp, por llamada o en
 * la oficina— y con qué valor. Aquí viven las reglas que el formulario aplica
 * ANTES de enviar, que son las mismas del backend (`schemas.VentaIn` /
 * `AnularVentaIn`): rechazar acá ahorra el viaje y un 422 con texto técnico.
 * El backend las vuelve a exigir; esto es solo para que la pantalla no mienta.
 */

/** Mismo tope que `models.VENTA_VALOR_MAX_COP`: 500 millones de pesos. */
export const VENTA_VALOR_MAX_COP = 500_000_000;
export const VENTA_NOTA_MAX = 280;
export const MOTIVO_MIN = 3;
export const MOTIVO_MAX = 280;

/** La venta tal como la devuelve el detalle de `/mensajes` (`VentaOut`). */
export type Venta = {
  id: number;
  valor_cop: number;
  vendida_por: string | null;
  nota: string | null;
  registrada_at: string;
  registrada_por_nombre: string | null;
  anulada_at: string | null;
  motivo_anulacion: string | null;
};

const PESOS = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

/** `7654321` → `$ 7.654.321` (pesos colombianos, sin decimales). */
export function formatearPesos(valor: number | null | undefined): string {
  if (valor == null || !Number.isFinite(valor)) return '';
  // Intl mete un espacio duro entre el signo y el número; se normaliza a un
  // espacio normal para que se vea igual en todos los navegadores.
  return PESOS.format(valor).replace(/ /g, ' ');
}

/**
 * Lo que la asesora escribió en el campo de valor, a pesos enteros.
 *
 * Acepta como se escribe un valor en Colombia: `1.250.000`, `1250000`,
 * `$ 1.250.000`. NO acepta decimales: en pesos no hay centavos, y `1.250,50`
 * casi siempre es un error de dedo que convertiría 1,2 millones en 125 mil.
 */
export type ValorLeido = { ok: boolean; valor: number | null; motivo: string | null };

const error = (motivo: string): ValorLeido => ({ ok: false, valor: null, motivo });

export function leerValorPesos(texto: string): ValorLeido {
  const limpio = (texto || '').replace(/[\s$]/g, '');
  if (!limpio) return error('Escribe el valor de la venta.');
  if (/,/.test(limpio)) {
    return error('El valor va en pesos enteros, sin centavos.');
  }
  // Puntos solo como separador de miles (1.250.000), nunca como decimal.
  if (!/^\d{1,3}(\.\d{3})*$|^\d+$/.test(limpio)) {
    return error('Escribe solo números, por ejemplo 1.250.000.');
  }
  const valor = Number(limpio.replace(/\./g, ''));
  if (!Number.isSafeInteger(valor) || valor <= 0) {
    return error('El valor tiene que ser mayor que cero.');
  }
  if (valor > VENTA_VALOR_MAX_COP) {
    return error(`El valor no puede pasar de ${formatearPesos(VENTA_VALOR_MAX_COP)}.`);
  }
  return { ok: true, valor, motivo: null };
}

/** Motivo de anulación: obligatorio, de 3 a 280 caracteres. `null` = válido. */
export function problemaConMotivo(motivo: string): string | null {
  const limpio = (motivo || '').trim();
  if (limpio.length < MOTIVO_MIN) return 'Escribe por qué se anula (mínimo 3 caracteres).';
  if (limpio.length > MOTIVO_MAX) return `El motivo no puede pasar de ${MOTIVO_MAX} caracteres.`;
  return null;
}
