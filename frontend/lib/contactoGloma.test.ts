/**
 * A dónde llevan los botones de contacto (decisión del CEO, 2026-10-28).
 *
 * Mientras el WhatsApp del agente no esté activo: ningún botón de contacto
 * tiene enlace (abren el chat de la página) y el footer va al número de
 * siempre. Si alguien enciende el interruptor sin querer, este test lo grita.
 */
import { describe, expect, it } from 'vitest';

import {
  WHATSAPP_DEL_AGENTE_ACTIVO,
  enlaceWhatsappContacto,
  enlaceWhatsappFooter,
  telefonoFooter,
} from './contactoGloma';

describe('contacto con Gloma mientras el WhatsApp del agente no está activo', () => {
  it('el interruptor está apagado', () => {
    expect(WHATSAPP_DEL_AGENTE_ACTIVO).toBe(false);
  });

  it('los botones de contacto no llevan a WhatsApp: abren el chat', () => {
    expect(enlaceWhatsappContacto()).toBeNull();
    expect(enlaceWhatsappContacto('Quiero agendar una llamada')).toBeNull();
  });

  it('el footer sigue yendo al número de siempre, el mismo que se lee', () => {
    const u = new URL(enlaceWhatsappFooter());
    expect(u.host).toBe('wa.me');
    expect(u.pathname).toBe('/573150764000');
    expect(telefonoFooter().replace(/\D/g, '')).toBe('573150764000');
  });
});
