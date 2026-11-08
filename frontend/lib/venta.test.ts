/**
 * Pruebas del formulario de «venta cerrada»: el valor se lee como lo escribe
 * una asesora en Colombia, y lo que el backend rechazaría se rechaza antes.
 */
import { describe, expect, it } from 'vitest';
import {
  VENTA_VALOR_MAX_COP,
  formatearPesos,
  leerValorPesos,
  problemaConMotivo,
} from './venta';

describe('leerValorPesos', () => {
  it.each([
    ['1250000', 1_250_000],
    ['1.250.000', 1_250_000],
    ['$ 1.250.000', 1_250_000],
    [' 980 000 ', 980_000],
    ['500.000.000', VENTA_VALOR_MAX_COP],
  ])('acepta %s', (texto, esperado) => {
    expect(leerValorPesos(texto)).toEqual({ ok: true, valor: esperado, motivo: null });
  });

  it.each(['', '0', '-5', '1.250,50', '1250.5', '12.34', 'mil', '500.000.001', '1e6'])(
    'rechaza %s',
    (texto) => {
      expect(leerValorPesos(texto).ok).toBe(false);
    },
  );
});

describe('formatearPesos', () => {
  it('pone separador de miles y sin decimales', () => {
    expect(formatearPesos(7_654_321)).toMatch(/7\.654\.321/);
    expect(formatearPesos(7_654_321)).not.toMatch(/,/);
  });

  it('sin valor no pinta nada', () => {
    expect(formatearPesos(null)).toBe('');
  });
});

describe('problemaConMotivo', () => {
  it('exige de 3 a 280 caracteres', () => {
    expect(problemaConMotivo('  ab ')).not.toBeNull();
    expect(problemaConMotivo('x'.repeat(281))).not.toBeNull();
    expect(problemaConMotivo('Valor mal digitado')).toBeNull();
  });
});
