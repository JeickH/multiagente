/**
 * Pruebas de la lógica de Interesados: niveles de la ventana, cuenta regresiva,
 * agrupación sin reordenar y pestaña inicial.
 *
 * El "ahora" se pasa explícito (hora del servidor ya corregida), así que no hace
 * falta congelar el reloj del sistema. Las fechas van como las manda el backend:
 * UTC sin marcar la zona. Si alguien cambiara `aInstante` por `new Date(iso)`,
 * en un CI con `TZ` distinta de UTC los minutos se correrían y esto fallaría.
 */

import { describe, expect, it } from 'vitest';
import {
  agrupar,
  desfaseServidor,
  duracionCorta,
  esReintentable,
  haceTexto,
  HORA_MS,
  Interesado,
  MINUTO_MS,
  msRestantes,
  nivelVentana,
  nombreVisible,
  porcentajeVentana,
  textoInteres,
  textoMes,
  textoMotivo,
  textoReloj,
  textoSenal,
  vistaInicial,
} from './interesados';

// 2026-10-07 17:00 UTC = 12:00 en Colombia.
const AHORA = Date.UTC(2026, 9, 7, 17, 0, 0);

/** ISO como lo manda el backend (UTC naive) a `ms` de AHORA. */
function iso(msDesdeAhora: number): string {
  return new Date(AHORA + msDesdeAhora).toISOString().replace('Z', '');
}

function interesado(id: number, cierraEnMs: number | null): Interesado {
  return {
    id,
    conversation_id: 100 + id,
    contacto: `Cliente ${id}`,
    telefono: '573000000000',
    tipos: ['anticipo'],
    fragmento: null,
    resumen: null,
    detectado_at: iso(-HORA_MS),
    conversacion_inicio_at: iso(-7 * HORA_MS),
    interesado_desde: iso(-HORA_MS),
    ultimo_mensaje_cliente_at: cierraEnMs === null ? null : iso(cierraEnMs - 24 * HORA_MS),
    ventana_cierra_at: cierraEnMs === null ? null : iso(cierraEnMs),
    interes: null,
    bot: { id: 1, nombre: 'Bot de prueba' },
    estado: 'por_contactar',
    gestionado_por: null,
    gestionado_at: null,
    motivo_descarte: null,
  };
}

describe('nivelVentana', () => {
  it('menos de 3 h es urgente', () => {
    expect(nivelVentana(2 * HORA_MS + 59 * MINUTO_MS)).toBe('urgente');
    expect(nivelVentana(1)).toBe('urgente');
  });
  it('de 3 a 8 h es pronto (bordes incluidos)', () => {
    expect(nivelVentana(3 * HORA_MS)).toBe('pronto');
    expect(nivelVentana(8 * HORA_MS)).toBe('pronto');
  });
  it('más de 8 h es con tiempo', () => {
    expect(nivelVentana(8 * HORA_MS + 1)).toBe('con_tiempo');
  });
  it('cerrada o sin dato', () => {
    expect(nivelVentana(0)).toBe('cerrada');
    expect(nivelVentana(-5)).toBe('cerrada');
    expect(nivelVentana(null)).toBe('cerrada');
  });
});

describe('cuenta regresiva', () => {
  it('lee la fecha naive como UTC', () => {
    expect(msRestantes(iso(90 * MINUTO_MS), AHORA)).toBe(90 * MINUTO_MS);
    expect(msRestantes(null, AHORA)).toBeNull();
  });

  it('textos del wireframe', () => {
    expect(textoReloj(HORA_MS + 50 * MINUTO_MS)).toBe('Quedan 1 h 50 min');
    expect(textoReloj(40 * MINUTO_MS)).toBe('Quedan 40 min');
    expect(textoReloj(15 * HORA_MS + 30 * MINUTO_MS)).toBe('Quedan 15 h');
    expect(textoReloj(6 * HORA_MS)).toBe('Quedan 6 h');
    expect(textoReloj(30_000)).toBe('Queda menos de 1 min');
    expect(textoReloj(-3 * HORA_MS)).toBe('Cerrada hace 3 h');
    expect(textoReloj(null)).toBe('Sin mensajes del cliente');
  });

  it('redondea hacia abajo: no promete minutos que no hay', () => {
    expect(duracionCorta(2 * HORA_MS - 1)).toBe('1 h 59 min');
    expect(duracionCorta(3 * 24 * HORA_MS)).toBe('3 días');
  });

  it('barra de porcentaje de las 24 h', () => {
    expect(porcentajeVentana(12 * HORA_MS)).toBe(50);
    expect(porcentajeVentana(-1)).toBe(0);
    expect(porcentajeVentana(null)).toBe(0);
    expect(porcentajeVentana(30 * HORA_MS)).toBe(100);
  });

  it('haceTexto', () => {
    expect(haceTexto(iso(-21 * HORA_MS), AHORA)).toBe('hace 21 h');
    expect(haceTexto(iso(-30 * MINUTO_MS), AHORA)).toBe('hace 30 min');
    expect(haceTexto(iso(-10_000), AHORA)).toBe('hace un momento');
    expect(haceTexto(null, AHORA)).toBe('');
  });

  it('el desfase corrige el reloj del equipo con el del servidor', () => {
    // El navegador va 20 min atrasado respecto al servidor.
    const local = AHORA - 20 * MINUTO_MS;
    const d = desfaseServidor(iso(0), local);
    expect(d).toBe(20 * MINUTO_MS);
    expect(local + d).toBe(AHORA);
    expect(desfaseServidor(null, local)).toBe(0);
  });
});

describe('agrupar', () => {
  it('respeta el orden del backend dentro de cada grupo y omite vacíos', () => {
    const lista = [
      interesado(1, HORA_MS), // urgente
      interesado(2, 2 * HORA_MS), // urgente
      interesado(3, 15 * HORA_MS), // con tiempo
      interesado(4, -2 * HORA_MS), // cerrada
      interesado(5, -9 * HORA_MS), // cerrada
    ];
    const grupos = agrupar(lista, AHORA);
    expect(grupos.map((g) => g.nivel)).toEqual(['urgente', 'con_tiempo', 'cerrada']);
    expect(grupos[0].items.map((i) => i.id)).toEqual([1, 2]);
    expect(grupos[2].items.map((i) => i.id)).toEqual([4, 5]);
  });

  it('una ventana que se cierra con la página abierta pasa al grupo cerrado, primera', () => {
    const lista = [interesado(1, 30 * MINUTO_MS), interesado(2, 5 * HORA_MS), interesado(3, -HORA_MS)];
    const despues = agrupar(lista, AHORA + HORA_MS);
    expect(despues.map((g) => g.nivel)).toEqual(['pronto', 'cerrada']);
    expect(despues[1].items.map((i) => i.id)).toEqual([1, 3]);
  });

  it('sin ventana conocida va con las cerradas', () => {
    expect(agrupar([interesado(1, null)], AHORA)[0].nivel).toBe('cerrada');
  });
});

describe('textos', () => {
  it('señales, con el nombre del contrato y el del wireframe', () => {
    expect(textoSenal('anticipo')).toBe('💰 Preguntó por el anticipo');
    expect(textoSenal('datos')).toBe('📝 Dejó sus datos');
    expect(textoSenal('datos_entregados')).toBe('📝 Dejó sus datos');
    expect(textoSenal('otra_cosa')).toBe('otra_cosa');
  });

  it('interés: mes de calendario sin pasar por Date', () => {
    expect(textoMes('2026-12')).toBe('diciembre');
    expect(textoMes('2027-01')).toBe('enero');
    expect(textoInteres({ mes: '2026-12', hotel: 'Hotel Ficticio' })).toBe('diciembre · Hotel Ficticio');
    expect(textoInteres({ mes: null, hotel: null })).toBeNull();
    expect(textoInteres(null)).toBeNull();
  });

  it('motivo y nombre visible', () => {
    expect(textoMotivo('ya_compro')).toBe('Ya compró');
    expect(textoMotivo('algo libre')).toBe('algo libre');
    expect(nombreVisible({ contacto: null, telefono: '573000000000' })).toBe('+573000000000');
    expect(nombreVisible({ contacto: '  ', telefono: '1' })).toBe('+1');
    expect(nombreVisible({ contacto: 'Ana', telefono: '1' })).toBe('Ana');
  });
});

describe('vistaInicial', () => {
  it('sin Interesados habilitado siempre Llamadas', () => {
    expect(vistaInicial('interesados', false, 5)).toBe('llamadas');
  });
  it('la URL manda', () => {
    expect(vistaInicial('llamadas', true, 5)).toBe('llamadas');
    expect(vistaInicial(['interesados'], true, 0)).toBe('interesados');
  });
  it('sin parámetro: Interesados si hay por contactar', () => {
    expect(vistaInicial(undefined, true, 3)).toBe('interesados');
    expect(vistaInicial(undefined, true, 0)).toBe('llamadas');
    expect(vistaInicial('basura', true, 0)).toBe('llamadas');
  });
});

describe('esReintentable', () => {
  it('5xx y red sí; 4xx no', () => {
    expect(esReintentable({ status: 500 })).toBe(true);
    expect(esReintentable({ status: 503 })).toBe(true);
    expect(esReintentable(new TypeError('Failed to fetch'))).toBe(true);
    expect(esReintentable({ status: 404 })).toBe(false);
    expect(esReintentable({ status: 403 })).toBe(false);
  });
});
