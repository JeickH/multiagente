/**
 * El compositor no deja enviar un mensaje que WhatsApp va a rebotar.
 *
 * Lo que se protege es el borde: 1.600 caracteres es un mensaje válido —el
 * límite de Twilio es "más de 1.600", no "1.600"— y 1.601 no. Un `>=` de más
 * acá le bloquearía a la asesora un mensaje que sí sale.
 *
 * El número en sí lo cuida el backend:
 * `backend/tests/test_mensaje_largo.py::test_el_frontend_declara_el_mismo_limite`
 * lee este módulo y falla si los dos lados se separan.
 */
import { describe, expect, it } from 'vitest';

import {
  AVISO_TEXTO,
  MAX_TEXTO_WHATSAPP,
  contadorTexto,
  motivoTextoMuyLargo,
  textoExcedido,
} from './mensajeTexto';

const texto = (n: number) => 'a'.repeat(n);

describe('textoExcedido', () => {
  it('deja pasar justo el límite', () => {
    expect(textoExcedido(texto(MAX_TEXTO_WHATSAPP))).toBe(false);
  });

  it('rechaza uno más', () => {
    expect(textoExcedido(texto(MAX_TEXTO_WHATSAPP + 1))).toBe(true);
  });

  it('no se cae con vacío ni con nulo', () => {
    expect(textoExcedido('')).toBe(false);
    expect(textoExcedido(null as any)).toBe(false);
  });
});

describe('lo que lee la asesora', () => {
  it('dice cuántos escribió, cuántos caben y qué hacer', () => {
    expect(motivoTextoMuyLargo(1742)).toBe(
      'El mensaje es muy largo para WhatsApp: tiene 1.742 caracteres ' +
        'y el máximo son 1.600. Pártelo en dos y vuelve a enviarlo.',
    );
  });

  it('el contador usa punto de miles, como se lee en Colombia', () => {
    expect(contadorTexto(1500)).toBe('1.500/1.600 caracteres');
  });
});

describe('el aviso', () => {
  it('aparece antes del límite, no cuando ya es tarde', () => {
    expect(AVISO_TEXTO).toBeLessThan(MAX_TEXTO_WHATSAPP);
  });

  it('no molesta en un mensaje normal de la bandeja', () => {
    expect(texto(300).length).toBeLessThan(AVISO_TEXTO);
  });
});
