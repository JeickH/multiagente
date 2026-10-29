import { describe, expect, it } from 'vitest';

import { rellenarCopy } from './demo_copy';
import {
  CALIFICACION,
  MENSAJES_POR_HORA,
  PASOS,
  RECORDATORIOS,
  REPORTE_TEXTOS,
  RESPUESTA_POR_FRANJA,
  duracion,
  enHorarioDeOficina,
  horaDelDia,
  mayorCaida,
  miles,
  millones,
  pesos,
  resumenReporte,
} from './demoReporte';

describe('reporte de ejemplo: las cifras ficticias cuadran entre sí', () => {
  it('~870 conversaciones y cada paso tiene menos gente que el anterior', () => {
    expect(PASOS[0].personas).toBe(870);
    for (let i = 1; i < PASOS.length; i += 1) {
      expect(PASOS[i].personas).toBeLessThan(PASOS[i - 1].personas);
    }
  });

  it('donde más gente se va es después del precio (lo dice el texto de la pantalla)', () => {
    expect(PASOS[mayorCaida().indice].clave).toBe('datos');
    expect(mayorCaida().seFueron).toBe(712 - 341);
  });

  it('la calificación suma las conversaciones y «listos» coincide con el paso', () => {
    expect(CALIFICACION.reduce((a, c) => a + c.personas, 0)).toBe(PASOS[0].personas);
    const listos = CALIFICACION.find((c) => c.clave === 'listos')!.personas;
    expect(listos).toBe(PASOS.find((p) => p.clave === 'listos')!.personas);
  });

  it('24 horas, y de noche los asesores tardan más que en el día', () => {
    expect(MENSAJES_POR_HORA).toHaveLength(24);
    const noche = RESPUESTA_POR_FRANJA[RESPUESTA_POR_FRANJA.length - 1];
    for (const f of RESPUESTA_POR_FRANJA) {
      expect(f.agenteSeg).toBeLessThan(60);
      expect(noche.asesoresMin).toBeGreaterThanOrEqual(f.asesoresMin);
    }
  });

  it('los recordatorios van de más a menos', () => {
    expect(RECORDATORIOS.volvieron).toBeLessThan(RECORDATORIOS.dejaronDeContestar);
    expect(RECORDATORIOS.reservaron).toBeLessThan(RECORDATORIOS.volvieron);
  });

  it('resumen', () => {
    const r = resumenReporte();
    expect(r.totalMensajes).toBe(7018);
    expect(r.fueraDeHorario).toBe(2903);
    expect(r.pctFueraDeHorario).toBe(41);
    expect(r.agenteSeg).toBe(7);
    expect(r.recuperadoPesos).toBe(27_550_000);
  });
});

describe('reporte de ejemplo: formatos', () => {
  it('miles con punto y pesos', () => {
    expect(miles(7018)).toBe('7.018');
    expect(miles(870)).toBe('870');
    expect(pesos(19_200_000)).toBe('$19.200.000');
    expect(millones(19_200_000)).toBe('$19,2 millones');
    expect(millones(21_000_000)).toBe('$21 millones');
  });

  it('duraciones', () => {
    expect(duracion(7)).toBe('7 s');
    expect(duracion(14 * 60)).toBe('14 min');
    expect(duracion(85 * 60)).toBe('1 h 25 min');
    expect(duracion(580 * 60)).toBe('9 h 40 min');
    expect(duracion(120 * 60)).toBe('2 h');
  });

  it('horas y horario de oficina (8 a. m. a 6 p. m.)', () => {
    expect(horaDelDia(0)).toBe('12 a. m.');
    expect(horaDelDia(12)).toBe('12 p. m.');
    expect(horaDelDia(20)).toBe('8 p. m.');
    expect(enHorarioDeOficina(7)).toBe(false);
    expect(enHorarioDeOficina(8)).toBe(true);
    expect(enHorarioDeOficina(17)).toBe(true);
    expect(enHorarioDeOficina(18)).toBe(false);
  });

  it('el rótulo de datos ficticios lleva el nombre de la empresa', () => {
    expect(rellenarCopy(REPORTE_TEXTOS.rotulo, { empresa: 'Posada El Colibrí' })).toBe(
      'Ejemplo con datos ficticios: así se vería el reporte de Posada El Colibrí',
    );
    expect(rellenarCopy(REPORTE_TEXTOS.rotulo, { empresa: '' })).toMatch(/reporte de tu empresa$/);
  });
});
