/**
 * Controles de #629 para el modal de Cal.com (#625) y los eventos de la demo.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CAL_ORIGIN, CAL_SANDBOX, esReservaDeCal, urlCal } from './agendarLlamada';
import { registrarEvento } from './demoApi';

describe('urlCal', () => {
  it('apunta al evento de Gloma en vista mensual, en el origen fijo', () => {
    const u = new URL(urlCal());
    expect(u.origin).toBe(CAL_ORIGIN);
    expect(u.pathname).toBe('/gloma/hablemos-de-gloma');
    expect(u.searchParams.get('layout')).toBe('month_view');
    expect(u.searchParams.get('theme')).toBe('dark');
    expect(u.searchParams.get('useSlotsViewOnSmallScreen')).toBe('true');
    expect([...u.searchParams.keys()]).toEqual(['layout', 'theme', 'useSlotsViewOnSmallScreen']);
  });

  it('solo agrega name y email, codificados', () => {
    const u = new URL(urlCal({ nombre: 'Ana & Co #1?x=y', correo: 'ana@example.com' }));
    expect(u.origin).toBe(CAL_ORIGIN);
    expect([...u.searchParams.keys()].sort()).toEqual(['email', 'layout', 'name', 'theme', 'useSlotsViewOnSmallScreen']);
    expect(u.searchParams.get('name')).toBe('Ana & Co #1?x=y');
    expect(u.searchParams.get('email')).toBe('ana@example.com');
    expect(u.hash).toBe('');
  });

  it('descarta un correo inválido y recorta el nombre', () => {
    const u = new URL(urlCal({ nombre: 'x'.repeat(200), correo: 'no-es-correo' }));
    expect(u.searchParams.get('email')).toBeNull();
    expect(u.searchParams.get('name')).toHaveLength(80);
  });
});

describe('esReservaDeCal', () => {
  const iframe = { soy: 'el iframe' };
  const ok = { origin: CAL_ORIGIN, source: iframe, data: { originator: 'CAL', type: 'bookingSuccessfulV2' } };

  it('acepta bookingSuccessful y bookingSuccessfulV2 de nuestro iframe', () => {
    expect(esReservaDeCal(ok, iframe)).toBe(true);
    expect(esReservaDeCal({ ...ok, data: { originator: 'CAL', type: 'bookingSuccessful' } }, iframe)).toBe(true);
  });

  it('rechaza otro origen, otra ventana, otro tipo o datos raros', () => {
    expect(esReservaDeCal({ ...ok, origin: 'https://cal.com' }, iframe)).toBe(false);
    expect(esReservaDeCal({ ...ok, origin: 'https://evil.example' }, iframe)).toBe(false);
    expect(esReservaDeCal({ ...ok, source: {} }, iframe)).toBe(false);
    expect(esReservaDeCal(ok, null)).toBe(false);
    expect(esReservaDeCal({ ...ok, data: { originator: 'X', type: 'bookingSuccessful' } }, iframe)).toBe(false);
    expect(esReservaDeCal({ ...ok, data: { originator: 'CAL', type: 'navigatedToBooker' } }, iframe)).toBe(false);
    expect(esReservaDeCal({ ...ok, data: 'CAL:bookingSuccessful' }, iframe)).toBe(false);
    expect(esReservaDeCal({ ...ok, data: null }, iframe)).toBe(false);
  });

  it('el sandbox nunca deja navegar la página de arriba', () => {
    expect(CAL_SANDBOX).not.toMatch(/top-navigation/);
  });
});

describe('registrarEvento', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('POST con keepalive, sin cookies y con el token solo en el header', () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    registrarEvento({ id: 'pub-1', token: 'tok-secreto' }, 'whatsapp');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/demo/pub-1/evento');
    expect(url).not.toContain('tok-secreto');
    expect(init.method).toBe('POST');
    expect(init.keepalive).toBe(true);
    expect(init.credentials).toBe('omit');
    expect(init.headers['X-Demo-Token']).toBe('tok-secreto');
    expect(JSON.parse(init.body)).toEqual({ tipo: 'whatsapp' });
  });

  it('sin demo no hace nada, y una falla de red no lanza', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('red'));
    vi.stubGlobal('fetch', fetchMock);
    registrarEvento(null, 'llamada_abierta');
    expect(fetchMock).not.toHaveBeenCalled();
    expect(() => registrarEvento({ id: 'x', token: 't' }, 'llamada_agendada')).not.toThrow();
    await new Promise((r) => setTimeout(r, 0));
  });
});
