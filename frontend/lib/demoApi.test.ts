/**
 * Pruebas de las piezas puras de la demo pública (`/demo`, #614).
 *
 * Lo que se protege:
 * 1. El enlace «Agendar con Gloma»: el nombre de la empresa lo escribe un
 *    tercero y viaja dentro del `text` de wa.me; no puede cambiar el destino.
 * 2. `sessionStorage['gloma_demo']`: lo que se lee de ahí puede venir dañado o
 *    manipulado; si no tiene la forma esperada se descarta, y si el
 *    almacenamiento está bloqueado nada revienta. Nunca se usa la clave
 *    `token` de la sesión de la plataforma (regla #7).
 * 3. La validación del formulario (teléfono de 7 a 15 dígitos, sin forzar +57).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { inicialesEmpresa, telefonoE164, validarCampo, FORMULARIO_VACIO } from './demoFormulario';
import { esTelefonoColombia, formatearE164, normalizarTelefono } from './telefonoPais';
import { DEMO_UI } from './demo_copy';
import { CLAVE_DEMO, borrarDemo, enlaceWhatsapp, guardarDemo, leerDemoGuardada, type DemoGuardada } from './demoApi';

function almacenEnMemoria(): Storage {
  const datos = new Map<string, string>();
  return {
    get length() {
      return datos.size;
    },
    clear: () => datos.clear(),
    getItem: (k) => (datos.has(k) ? (datos.get(k) as string) : null),
    key: (i) => Array.from(datos.keys())[i] ?? null,
    removeItem: (k) => void datos.delete(k),
    setItem: (k, v) => void datos.set(k, String(v)),
  };
}

const DEMO: DemoGuardada = {
  v: 1,
  id: 'demo-ficticia',
  token: 'tok-ficticio',
  nombre: 'Camila',
  empresa: 'Viajes Alcaraván Azul',
  creadoMs: 1_700_000_000_000,
  etapa: 'slides',
};

describe('enlaceWhatsapp', () => {
  it('lleva al WhatsApp de Gloma con la empresa en el texto', () => {
    const url = enlaceWhatsapp('Viajes Alcaraván Azul', DEMO_UI.agendar);
    expect(url.startsWith('https://wa.me/573150764000?text=')).toBe(true);
    expect(decodeURIComponent(url.split('text=')[1])).toBe(
      'Hola, acabo de probar la demo de Viajes Alcaraván Azul y quiero agendar una llamada',
    );
  });

  it('una empresa con caracteres de URL no cambia el destino', () => {
    const url = enlaceWhatsapp('A&B?x=1#/https://otro.example', DEMO_UI.agendar);
    const u = new URL(url);
    expect(u.host).toBe('wa.me');
    expect(u.pathname).toBe('/573150764000');
    expect([...u.searchParams.keys()]).toEqual(['text']);
  });

  it('sin empresa usa el texto genérico', () => {
    expect(decodeURIComponent(enlaceWhatsapp('  ', DEMO_UI.agendar).split('text=')[1])).toBe(DEMO_UI.agendar.sinDemo);
  });
});

describe('sessionStorage gloma_demo', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { sessionStorage: almacenEnMemoria() });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('guarda y recupera la demo bajo su propia clave', () => {
    guardarDemo(DEMO);
    expect(window.sessionStorage.getItem('token')).toBeNull();
    expect(JSON.parse(window.sessionStorage.getItem(CLAVE_DEMO) as string).id).toBe('demo-ficticia');
    expect(leerDemoGuardada()).toEqual({ ...DEMO, chat: undefined });
  });

  it('descarta lo que no tiene la forma esperada', () => {
    window.sessionStorage.setItem(CLAVE_DEMO, '{no es json');
    expect(leerDemoGuardada()).toBeNull();
    window.sessionStorage.setItem(CLAVE_DEMO, JSON.stringify({ ...DEMO, v: 2 }));
    expect(leerDemoGuardada()).toBeNull();
    window.sessionStorage.setItem(CLAVE_DEMO, JSON.stringify({ ...DEMO, token: 123 }));
    expect(leerDemoGuardada()).toBeNull();
  });

  it('limpia mensajes dañados y acota el hilo guardado', () => {
    const mensajes = Array.from({ length: 60 }, (_, i) => ({ id: i + 1, de: 'yo', texto: `m${i}`, hora: '' }));
    window.sessionStorage.setItem(
      CLAVE_DEMO,
      JSON.stringify({ ...DEMO, etapa: 'chat', chat: { fin: 'raro', mensajes: [...mensajes, { de: 'x' }] } }),
    );
    const d = leerDemoGuardada();
    expect(d?.chat?.fin).toBeNull();
    expect(d?.chat?.mensajes.length).toBe(40);
    expect(d?.chat?.mensajes.at(-1)?.texto).toBe('m59');
  });

  it('borrarDemo la quita', () => {
    guardarDemo(DEMO);
    borrarDemo();
    expect(leerDemoGuardada()).toBeNull();
  });

  it('con el almacenamiento bloqueado no revienta', () => {
    vi.stubGlobal('window', {
      get sessionStorage(): Storage {
        throw new Error('SecurityError');
      },
    });
    expect(() => guardarDemo(DEMO)).not.toThrow();
    expect(leerDemoGuardada()).toBeNull();
    expect(() => borrarDemo()).not.toThrow();
  });
});

describe('validarCampo', () => {
  const con = (cambios: Partial<typeof FORMULARIO_VACIO>) => ({ ...FORMULARIO_VACIO, ...cambios });

  it('teléfono: Colombia por defecto, 10 dígitos que empiezan por 3 o 60', () => {
    expect(validarCampo('telefono', con({ telefono: '300 000 0000' }))).toBe('');
    expect(validarCampo('telefono', con({ telefono: '601 234 5678' }))).toBe('');
    expect(validarCampo('telefono', con({ telefono: '300 12' }))).toMatch(/Colombia tiene 10 dígitos/);
    expect(validarCampo('telefono', con({ telefono: '700 000 0000' }))).toBe(DEMO_UI.form.errores.telefonoColombia);
    expect(validarCampo('telefono', con({ telefono: '  ' }))).toBe(DEMO_UI.form.errores.telefonoVacio);
  });

  it('teléfono de otro país: largo del país y «Otro» con indicativo', () => {
    expect(validarCampo('telefono', con({ telefono_pais: 'MX', telefono: '55 1234 5678' }))).toBe('');
    expect(validarCampo('telefono', con({ telefono_pais: 'PE', telefono: '12345' }))).toMatch(/Perú tiene 8 a 9 dígitos/);
    expect(validarCampo('telefono', con({ telefono_pais: 'OTRO', telefono: '612345678', telefono_indicativo: '' }))).toBe(
      DEMO_UI.form.errores.telefonoIndicativo,
    );
    expect(validarCampo('telefono', con({ telefono_pais: 'OTRO', telefono: '612345678', telefono_indicativo: '351' }))).toBe('');
  });

  it('tipo de empresa: solo claves de la lista', () => {
    expect(validarCampo('tipo_empresa', con({ tipo_empresa: 'hotel' }))).toBe('');
    expect(validarCampo('tipo_empresa', con({ tipo_empresa: 'banco' }))).toBe(DEMO_UI.form.errores.tipo);
  });

  it('correo y autorización de contacto', () => {
    expect(validarCampo('correo', con({ correo: 'camila@example' }))).toBe(DEMO_UI.form.errores.correoInvalido);
    expect(validarCampo('correo', con({ correo: 'camila@example.com' }))).toBe('');
    expect(validarCampo('acepta_contacto', con({}))).toBe(DEMO_UI.form.errores.contacto);
  });
});

describe('inicialesEmpresa', () => {
  it('ignora artículos, preposiciones y sufijos societarios', () => {
    expect(inicialesEmpresa('Posada El Colibrí')).toBe('PC');
    expect(inicialesEmpresa('Viajes del Sol S.A.S.')).toBe('VS');
    expect(inicialesEmpresa('Tours & Aventuras Ltda')).toBe('TA');
    expect(inicialesEmpresa('La Casa de los Abuelos SAS')).toBe('CA');
    expect(inicialesEmpresa('Hotel Mirador S.A.')).toBe('HM');
  });

  it('casos límite', () => {
    expect(inicialesEmpresa('Ébano')).toBe('É');
    expect(inicialesEmpresa('El Del')).toBe('ED');
    expect(inicialesEmpresa('   ')).toBe('G');
  });
});

describe('normalizarTelefono (E.164)', () => {
  it('Colombia: número nacional → +57', () => {
    expect(normalizarTelefono('CO', '', '300 123 4567').e164).toBe('+573001234567');
    expect(normalizarTelefono('CO', '', '(300) 123-4567').e164).toBe('+573001234567');
  });

  it('pegado con indicativo no queda duplicado', () => {
    expect(normalizarTelefono('CO', '', '+57 300 123 4567').e164).toBe('+573001234567');
    expect(normalizarTelefono('CO', '', '573001234567').e164).toBe('+573001234567');
    expect(normalizarTelefono('CO', '', '0057 300 123 4567').e164).toBe('+573001234567');
    expect(normalizarTelefono('US', '', '1 201 555 0123').e164).toBe('+12015550123');
  });

  it('con «+» de otro país se respeta ese país', () => {
    expect(normalizarTelefono('CO', '', '+52 55 1234 5678').e164).toBe('+525512345678');
    expect(normalizarTelefono('CO', '', '+57 700 000 0000').error).toBe('colombia');
  });

  it('otros países, 0 de larga distancia y «Otro»', () => {
    expect(normalizarTelefono('BR', '', '11 91234 5678').e164).toBe('+5511912345678');
    expect(normalizarTelefono('AR', '', '011 2345 6789').e164).toBe('+541123456789');
    expect(normalizarTelefono('ES', '', '612 34 56 78').e164).toBe('+34612345678');
    expect(normalizarTelefono('OTRO', '351', '912 345 678').e164).toBe('+351912345678');
    expect(normalizarTelefono('OTRO', '0', '912 345 678').error).toBe('indicativo');
  });

  it('errores: vacío, largo y el techo de 15 dígitos', () => {
    expect(normalizarTelefono('CO', '', '').error).toBe('vacio');
    expect(normalizarTelefono('MX', '', '55 1234').error).toBe('largo');
    expect(normalizarTelefono('CO', '', '+1234567890123456').error).toBe('total');
  });

  it('telefonoE164 usa los campos del formulario', () => {
    expect(telefonoE164({ telefono: '300 123 4567', telefono_pais: 'CO', telefono_indicativo: '' })).toBe('+573001234567');
    expect(telefonoE164({ telefono: '123', telefono_pais: 'CO', telefono_indicativo: '' })).toBeNull();
  });
});

describe('premio (#643): formato del teléfono y monto por país', () => {
  it('formatea E.164 con el indicativo separado', () => {
    expect(formatearE164('+573001234567', 'CO')).toBe('+57 300 123 4567');
    expect(formatearE164('+525512345678', 'MX')).toBe('+52 551 234 5678');
    expect(formatearE164('+5511912345678', 'BR')).toBe('+55 11 91234 5678');
    expect(formatearE164('+34612345678', 'ES')).toBe('+34 612 345 678');
    expect(formatearE164('+351912345678', 'OTRO', '351')).toBe('+351 912 345 678');
    // Con Colombia elegida pero un «+52» pegado: se reconoce el indicativo de México.
    expect(formatearE164('+525512345678', 'CO')).toBe('+52 551 234 5678');
  });

  it('el monto en pesos solo si el teléfono es +57', () => {
    expect(esTelefonoColombia('+573001234567')).toBe(true);
    expect(esTelefonoColombia('+525512345678')).toBe(false);
    expect(esTelefonoColombia(null)).toBe(false);
  });
});
