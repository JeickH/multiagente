/**
 * Pruebas de las fechas de la bandeja.
 *
 * Dos cosas distintas se protegen acá, y las dos ya se rompieron en producción:
 *
 * 1. **La zona.** El backend serializa UTC *sin marcarlo*
 *    ("2026-08-20T21:26:57"), y el estándar de JavaScript manda leer eso como
 *    hora local del navegador. Sin `aInstante`, un mensaje de las 4:26 p. m. de
 *    Colombia se pintaba a las 9:26 p. m. Los tests fijan la hora esperada en
 *    hora de Bogotá, así que fallan si alguien saca el `timeZone`.
 *
 * 2. **El día.** La lista de conversaciones mostraba *sólo la hora*: un chat
 *    del 27 de agosto decía "12:33 p. m." y se leía como "hace un rato". La
 *    hora nunca estuvo mal calculada, pero sin el día la respuesta engañaba
 *    igual.
 *
 * El reloj se congela con `vi.setSystemTime` porque "hoy" y "ayer" dependen de
 * cuándo se corre la prueba, y un test que pasa hasta la medianoche no sirve.
 * La hora elegida (17:00 UTC = 12:00 en Colombia) está lejos de los dos bordes
 * del día en ambas zonas, para que el test no dependa de dónde corra el CI.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import {
  aInstante,
  encabezadoDeDia,
  fechaHoraLarga,
  horaCorta,
  marcaDeTiempoLista,
  mismoDia,
} from './fechas';

/** Mediodía de Colombia del 31-ago-2026 (un lunes). */
const AHORA = new Date('2026-08-31T17:00:00Z');

beforeAll(() => {
  vi.useFakeTimers();
  vi.setSystemTime(AHORA);
});

afterAll(() => {
  vi.useRealTimers();
});

/** Quita los espacios raros (NBSP y el finito) que mete `Intl`. */
const limpio = (s: string) => s.replace(/[  ]/g, ' ');

describe('aInstante', () => {
  it('le pone la Z que el backend omite', () => {
    // 21:26 UTC = 16:26 en Colombia.
    expect(aInstante('2026-08-20T21:26:57.533129')?.toISOString()).toBe(
      '2026-08-20T21:26:57.533Z',
    );
  });

  it('respeta la zona cuando el texto sí la trae', () => {
    expect(aInstante('2026-08-20T16:26:57-05:00')?.toISOString()).toBe(
      '2026-08-20T21:26:57.000Z',
    );
  });

  it('devuelve null con vacío o basura, en vez de "Invalid Date"', () => {
    expect(aInstante('')).toBeNull();
    expect(aInstante(null)).toBeNull();
    expect(aInstante(undefined)).toBeNull();
    expect(aInstante('no es una fecha')).toBeNull();
  });
});

describe('horaCorta', () => {
  it('pinta la hora de Colombia, no la del navegador', () => {
    // El bug original: sin zona esto salía 9:26 p. m. en un equipo en UTC.
    expect(limpio(horaCorta('2026-08-20T21:26:57'))).toBe('04:26 p. m.');
  });

  it('usa el fallback cuando no hay fecha', () => {
    expect(horaCorta(null, '—')).toBe('—');
  });
});

describe('marcaDeTiempoLista', () => {
  it('de hoy muestra la hora', () => {
    expect(limpio(marcaDeTiempoLista('2026-08-31T14:33:00'))).toBe('09:33 a. m.');
  });

  it('de ayer dice "Ayer"', () => {
    expect(marcaDeTiempoLista('2026-08-30T14:33:00')).toBe('Ayer');
  });

  it('dentro de la semana dice el día', () => {
    // Jueves 27 de agosto.
    expect(marcaDeTiempoLista('2026-08-27T17:33:40').toLowerCase()).toContain('jue');
  });

  it('más viejo que una semana muestra la fecha', () => {
    expect(marcaDeTiempoLista('2026-07-15T17:33:40')).toMatch(/15/);
    expect(marcaDeTiempoLista('2026-07-15T17:33:40')).not.toMatch(/:/);
  });

  it('de más de un año muestra también el año', () => {
    expect(marcaDeTiempoLista('2024-03-02T17:33:40')).toMatch(/24/);
  });

  it('el cambio de día se decide en Colombia, no en UTC', () => {
    // 02:00 UTC del 31-ago son las 21:00 del 30-ago en Colombia: es "Ayer",
    // aunque en UTC ya sea hoy. Este es exactamente el error que se evita.
    expect(marcaDeTiempoLista('2026-08-31T02:00:00')).toBe('Ayer');
  });

  it('no revienta sin fecha', () => {
    expect(marcaDeTiempoLista(null, '—')).toBe('—');
  });
});

describe('encabezadoDeDia', () => {
  it('dice "Hoy" y "Ayer"', () => {
    expect(encabezadoDeDia('2026-08-31T14:33:00')).toBe('Hoy');
    expect(encabezadoDeDia('2026-08-30T14:33:00')).toBe('Ayer');
  });

  it('más atrás escribe el día completo', () => {
    const texto = encabezadoDeDia('2026-08-27T17:33:40');
    expect(texto).toContain('27');
    expect(texto).toContain('agosto');
    expect(texto).toContain('2026');
  });
});

describe('mismoDia', () => {
  it('agrupa lo que cae el mismo día de Colombia', () => {
    expect(mismoDia('2026-08-27T13:00:00', '2026-08-27T22:00:00')).toBe(true);
  });

  it('separa lo que cae en días distintos', () => {
    expect(mismoDia('2026-08-27T22:00:00', '2026-08-28T13:00:00')).toBe(false);
  });

  it('el corte es la medianoche de Colombia, no la de UTC', () => {
    // 2026-08-28T02:00Z son las 21:00 del 27 en Colombia: mismo día que las
    // 13:00 del 27. Comparando en UTC saldría que son días distintos.
    expect(mismoDia('2026-08-27T18:00:00', '2026-08-28T02:00:00')).toBe(true);
  });

  it('sin fecha no inventa un corte', () => {
    expect(mismoDia(null, '2026-08-27T13:00:00')).toBe(true);
  });
});

describe('fechaHoraLarga', () => {
  it('trae día, mes, año y hora de Colombia', () => {
    const texto = limpio(fechaHoraLarga('2026-08-20T21:26:57'));
    expect(texto).toContain('20');
    expect(texto).toContain('agosto');
    expect(texto).toContain('2026');
    expect(texto).toContain('04:26 p. m.');
  });
});
