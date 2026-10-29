/**
 * A dónde llevan los botones de contacto (decisión del CEO, 2026-10-29).
 *
 * Con el WhatsApp del agente activo: «Hablar con un asesor» y el footer van al
 * wa.me del agente (y el número que se lee es el mismo). Si alguien apaga el
 * interruptor sin querer, este test lo grita.
 */
import { describe, expect, it } from 'vitest';

import {
  MENSAJE_ASESOR,
  WHATSAPP_DEL_AGENTE_ACTIVO,
  enlaceWhatsapp,
  enlaceWhatsappContacto,
  enlaceWhatsappFooter,
  telefonoFooter,
} from './contactoGloma';

const AGENTE = '/573239087528';

describe('contacto con Gloma con el WhatsApp del agente activo', () => {
  it('el interruptor está encendido', () => {
    expect(WHATSAPP_DEL_AGENTE_ACTIVO).toBe(true);
  });

  it('«Hablar con un asesor» va al WhatsApp del agente con el texto prellenado', () => {
    const u = new URL(enlaceWhatsappContacto(MENSAJE_ASESOR) as string);
    expect(u.host).toBe('wa.me');
    expect(u.pathname).toBe(AGENTE);
    expect(u.searchParams.get('text')).toBe(MENSAJE_ASESOR);
  });

  it('el footer va al WhatsApp del agente, el mismo número que se lee', () => {
    const u = new URL(enlaceWhatsappFooter());
    expect(u.pathname).toBe(AGENTE);
    expect('/' + telefonoFooter().replace(/\D/g, '')).toBe(AGENTE);
  });

  it('un texto con caracteres de URL no cambia el destino', () => {
    const u = new URL(enlaceWhatsapp('573239087528', 'A&B?x=1#/https://otro.example'));
    expect(u.pathname).toBe(AGENTE);
    expect([...u.searchParams.keys()]).toEqual(['text']);
  });
});
