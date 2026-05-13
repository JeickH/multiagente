/**
 * Helpers de formato compartidos por el módulo Campañas.
 *
 * SEGURIDAD: `maskPhone` se aplica a TODO teléfono que se renderice en
 * UI (regla 1 — no exponer PII más de lo necesario al operador, aunque
 * el dueño del team técnicamente sí puede ver el dato completo).
 */

/** Formateador de miles localizado (es-MX). */
export function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '0';
  return new Intl.NumberFormat('es-MX').format(n);
}

/** Porcentaje seguro frente a divisores 0. */
export function fmtPct(part: number, total: number, digits = 1): string {
  if (!total) return '0%';
  return `${((part / total) * 100).toFixed(digits)}%`;
}

/** Fecha corta (es-MX). Devuelve `—` si la entrada es nula/invalida. */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('es-MX', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  });
}

/** Fecha + hora corta (es-MX). Útil en cabecera y celdas de timestamps. */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('es-MX', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Solo la hora HH:MM (es-MX). Para columnas Enviado/Entregado/Leído. */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('es-MX', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Enmascara un teléfono E.164 dejando visibles el código de país
 * (primeros 1-3 dígitos tras `+`) y los últimos 4 dígitos.
 *
 *   +573001234567 → "+57 XXX XXX 4567"
 *   +5215512345678 → "+52 XXXX XX 5678"
 *
 * Si el input no parece E.164 se devuelve tal cual (defensivo, sin lanzar).
 */
export function maskPhone(raw: string | null | undefined): string {
  if (!raw) return '—';
  const trimmed = raw.trim();
  // Detectar el código de país (1-3 dígitos tras el '+').
  const m = trimmed.match(/^\+?(\d{1,3})(\d+)$/);
  if (!m) return trimmed;
  const country = m[1];
  const rest = m[2];
  if (rest.length <= 4) {
    // Demasiado corto para enmascarar de forma útil.
    return `+${country} ${rest}`;
  }
  const last4 = rest.slice(-4);
  const middleLen = rest.length - 4;
  // Agrupar la zona enmascarada en bloques de 3 para legibilidad.
  const masked: string[] = [];
  let remaining = middleLen;
  while (remaining > 0) {
    const take = Math.min(3, remaining);
    masked.push('X'.repeat(take));
    remaining -= take;
  }
  return `+${country} ${masked.join(' ')} ${last4}`;
}
