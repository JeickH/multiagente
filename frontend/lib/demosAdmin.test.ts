/**
 * Panel «Demos web» (#630): rangos en días de Colombia, query, derivación de
 * etapas y formatos. Datos ficticios.
 */
import { describe, expect, it } from 'vitest';

import {
  cumpleEtapa,
  cuando,
  diaColombia,
  enlaceWhatsappProspecto,
  errorDeRango,
  estadoVisible,
  formatoCop,
  hiloConMarcas,
  pct,
  queryDemos,
  rangoDe,
  recorridoDe,
  recorridoVacio,
  tipoTexto,
  type DetalleDemo,
  type ItemDemo,
} from './demosAdmin';

const BASE: ItemDemo = {
  public_id: 'pub-1',
  created_at: '2026-10-17T16:40:06',
  nombre: 'Laura Gómez',
  empresa: 'Posada El Colibrí',
  tipo_empresa: 'hotel',
  tipo_otro: null,
  tipo_empresa_label: 'Hotel',
  telefono: '+57 300 ••• 0001',
  correo: 'la•••@example.com',
  acepta_promociones: true,
  estado: 'lista',
  origen_productos: 'modelo',
  turnos: 0,
  traspaso_at: null,
  clics_whatsapp: 0,
  aperturas_llamada: 0,
  llamada_agendada_at: null,
  interna: false,
  lead_borrado: false,
  bot_eliminado_at: null,
};
const item = (c: Partial<ItemDemo>): ItemDemo => ({ ...BASE, ...c });

describe('rangos en días de Colombia', () => {
  // 17-oct 02:00 UTC = 16-oct 21:00 en Bogotá: «hoy» es el 16.
  const madrugadaUtc = new Date('2026-10-17T02:00:00Z');

  it('«hoy» es el día de Bogotá, no el UTC', () => {
    expect(diaColombia(madrugadaUtc)).toBe('2026-10-16');
    expect(rangoDe('hoy', madrugadaUtc)).toEqual({ desde: '2026-10-16', hasta: '2026-10-16' });
  });

  it('7 y 30 días incluyen hoy', () => {
    expect(rangoDe('7', madrugadaUtc)).toEqual({ desde: '2026-10-10', hasta: '2026-10-16' });
    expect(rangoDe('30', madrugadaUtc)).toEqual({ desde: '2026-09-17', hasta: '2026-10-16' });
  });

  it('valida el rango personalizado (≤ 366 días, en orden)', () => {
    expect(errorDeRango('2026-10-01', '2026-10-17')).toBeNull();
    expect(errorDeRango('2026-10-18', '2026-10-17')).toMatch(/antes/);
    expect(errorDeRango('2025-01-01', '2026-10-17')).toMatch(/año/);
    expect(errorDeRango('', '2026-10-17')).toMatch(/fechas/);
  });
});

describe('queryDemos', () => {
  it('manda el contrato y omite los filtros vacíos', () => {
    const q = new URLSearchParams(
      queryDemos({ desde: '2026-10-10', hasta: '2026-10-16', incluirInternas: false, q: '  ', tipo: '', estado: '', etapa: '', pagina: 1, porPagina: 20 }),
    );
    expect(Object.fromEntries(q)).toEqual({
      desde: '2026-10-10',
      hasta: '2026-10-16',
      incluir_internas: 'false',
      page: '1',
      page_size: '20',
    });
  });

  it('con filtros, y el page_size nunca pasa de 100', () => {
    const q = new URLSearchParams(
      queryDemos({ desde: 'a', hasta: 'b', incluirInternas: true, q: 'colibrí & co', tipo: 'hotel', estado: 'respaldo', etapa: 'pidieron_hablar', pagina: 3, porPagina: 500 }),
    );
    expect(q.get('q')).toBe('colibrí & co');
    expect(q.get('incluir_internas')).toBe('true');
    expect(q.get('estado')).toBe('respaldo');
    expect(q.get('etapa')).toBe('pidieron_hablar');
    expect(q.get('page')).toBe('3');
    expect(q.get('page_size')).toBe('100');
  });
});

describe('etapas y recorrido', () => {
  it('sin recorrido: «No escribió», «Solo conversó» o «—»', () => {
    expect(recorridoDe(item({}))).toEqual([]);
    expect(recorridoVacio(item({}))).toBe('No escribió');
    expect(recorridoVacio(item({ turnos: 3 }))).toBe('Solo conversó');
    expect(recorridoVacio(item({ estado: 'generando' }))).toBe('—');
  });

  it('chips solo de lo que pasó; «agendó» reemplaza a «abrió agendador»', () => {
    const r = recorridoDe(item({ traspaso_at: '2026-10-17T16:45:00', clics_whatsapp: 2, aperturas_llamada: 1 }));
    expect(r.map((p) => p.texto)).toEqual(['Traspaso', 'WhatsApp ×2', 'Abrió agendador']);
    const agendo = recorridoDe(item({ aperturas_llamada: 3, llamada_agendada_at: '2026-10-17T17:00:00' }));
    expect(agendo.map((p) => p.texto)).toEqual(['Agendó llamada']);
    expect(agendo[0].fuerte).toBe(true);
  });

  it('cumpleEtapa cuenta demos, no clics, y «pidieron hablar» es WhatsApp o agendador', () => {
    const d = item({ turnos: 2, clics_whatsapp: 3 });
    expect(cumpleEtapa(d, 'conversaron')).toBe(true);
    expect(cumpleEtapa(d, 'whatsapp')).toBe(true);
    expect(cumpleEtapa(d, 'traspaso')).toBe(false);
    expect(cumpleEtapa(d, 'pidieron_hablar')).toBe(true);
    expect(cumpleEtapa(item({ aperturas_llamada: 1 }), 'pidieron_hablar')).toBe(true);
    expect(cumpleEtapa(item({}), 'pidieron_hablar')).toBe(false);
    expect(cumpleEtapa(item({}), '')).toBe(true);
  });

  it('estado visible: modelo, respaldo, generando, error', () => {
    expect(estadoVisible(item({})).clave).toBe('modelo');
    expect(estadoVisible(item({ origen_productos: 'respaldo' })).texto).toBe('Lista · respaldo');
    expect(estadoVisible(item({ estado: 'generando', origen_productos: null })).clave).toBe('generando');
    expect(estadoVisible(item({ estado: 'error', origen_productos: null })).clave).toBe('error');
  });
});

describe('formatos', () => {
  it('tipo, porcentaje y pesos', () => {
    expect(tipoTexto(item({}))).toBe('Hotel');
    expect(tipoTexto(item({ tipo_empresa: 'otro', tipo_empresa_label: 'Otro', tipo_otro: 'escuela de surf' }))).toBe('Otro: escuela de surf');
    expect(pct(4, 9)).toBe('44 %');
    expect(pct(1, 0)).toBe('—');
    expect(formatoCop(1890000)).toBe('$1.890.000');
    expect(formatoCop(null)).toBe('');
  });

  it('cuando: hoy y ayer en hora de Colombia', () => {
    const ahora = new Date('2026-10-17T20:00:00Z'); // 15:00 en Bogotá
    expect(cuando('2026-10-17T16:40:06', ahora)).toMatch(/^Hoy, /);
    expect(cuando('2026-10-17T03:00:00', ahora)).toMatch(/^Ayer, /); // 16-oct 22:00 en Bogotá
    expect(cuando('2026-10-10T16:00:00', ahora)).not.toMatch(/^(Hoy|Ayer)/);
    expect(cuando(null, ahora)).toBe('');
  });
});

describe('enlaceWhatsappProspecto', () => {
  it('celular colombiano sin indicativo → 57; saludo solo con el primer nombre', () => {
    const url = enlaceWhatsappProspecto('300 000 0001', 'Laura Gómez');
    expect(url?.startsWith('https://wa.me/573000000001?text=')).toBe(true);
    expect(decodeURIComponent((url as string).split('text=')[1])).toBe('Hola, Laura. Te escribo de Gloma por la demo que armaste.');
  });

  it('respeta el indicativo y rechaza números imposibles', () => {
    expect(enlaceWhatsappProspecto('+52 55 1234 5678', null)).toMatch(/^https:\/\/wa\.me\/525512345678\?/);
    expect(enlaceWhatsappProspecto('123', 'Ana')).toBeNull();
    expect(enlaceWhatsappProspecto(null, 'Ana')).toBeNull();
  });

  it('un nombre con caracteres raros no cambia el destino', () => {
    const u = new URL(enlaceWhatsappProspecto('3000000001', 'A&b?x=1#y') as string);
    expect(u.host).toBe('wa.me');
    expect([...u.searchParams.keys()]).toEqual(['text']);
  });
});

describe('hiloConMarcas', () => {
  const detalle = (c: Partial<DetalleDemo>): DetalleDemo => ({
    ...BASE,
    acepto_contacto_at: null,
    acepta_promociones_at: null,
    consent_version: null,
    lista_at: null,
    primer_clic_whatsapp_at: null,
    primer_apertura_llamada_at: null,
    productos: [],
    transcripcion: [],
    uso_resumen: null,
    ...c,
  });

  it('intercala las marcas por hora, después de los mensajes de la misma hora', () => {
    const h = hiloConMarcas(
      detalle({
        transcripcion: [
          { rol: 'usuario', texto: 'hola', at: '2026-10-17T16:40:00' },
          { rol: 'bot', texto: 'Te paso con un asesor', at: '2026-10-17T16:41:00' },
          { rol: 'usuario', texto: 'gracias', at: '2026-10-17T16:45:00' },
        ],
        traspaso_at: '2026-10-17T16:41:00',
        primer_clic_whatsapp_at: '2026-10-17T16:50:00',
        clics_whatsapp: 2,
        llamada_agendada_at: '2026-10-17T16:55:00',
      }),
    );
    expect(h.map((e) => (e.tipo === 'marca' ? `[${e.texto}]` : e.texto))).toEqual([
      'hola',
      'Te paso con un asesor',
      '[Traspaso a asesor]',
      'gracias',
      '[Clic en «Hablar con un asesor» (WhatsApp) (2 veces)]',
      '[Agendó una llamada (reportada por el navegador)]',
    ]);
  });
});
