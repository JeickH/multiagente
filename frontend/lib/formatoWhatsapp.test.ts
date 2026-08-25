/**
 * Pruebas del parser de formato de WhatsApp.
 *
 * `analizarWhatsapp` es puro (string → nodos), así que no hace falta montar
 * React ni jsdom: se corre con `npm test` en Node y punto. Las pocas pruebas
 * que sí miran los nodos de React inspeccionan el objeto que devuelve
 * `createElement` (que es un objeto plano), no un DOM.
 *
 * Los casos borde de aquí no son teóricos: `2 * 3`, `$459.000`, `*30%*` y los
 * `**dobles**` salen de los mensajes reales del bot de viajes y de lo que
 * escriben los clientes. Ningún dato personal en los ejemplos: el repo es
 * público (regla 8), así que los teléfonos van enmascarados.
 */
import { createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { analizarWhatsapp, formatearWhatsapp, type NodoWhatsapp } from './formatoWhatsapp';

/** Representación compacta de los nodos, para que las pruebas se lean. */
function plano(nodos: NodoWhatsapp[]): string {
  return nodos
    .map((n) => (n.tipo === 'texto' ? n.texto : `<${n.tipo}>${plano(n.hijos)}</${n.tipo}>`))
    .join('');
}

describe('texto sin formato', () => {
  it('devuelve [] con vacío, null y undefined', () => {
    expect(analizarWhatsapp('')).toEqual([]);
    expect(analizarWhatsapp(null)).toEqual([]);
    expect(analizarWhatsapp(undefined)).toEqual([]);
    expect(formatearWhatsapp(null)).toEqual([]);
  });

  it('deja intacto un texto plano', () => {
    const texto = 'Hola, ¿en qué te ayudo?';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('no toca un texto con caracteres de HTML (los escapa React, no nosotros)', () => {
    const texto = '<img src=x onerror=alert(1)> & <b>hola</b>';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });
});

describe('negrilla', () => {
  it('convierte *palabra* en negrilla', () => {
    expect(plano(analizarWhatsapp('salida el *viernes*'))).toBe(
      'salida el <negrilla>viernes</negrilla>'
    );
  });

  it('soporta varias marcas en la misma línea', () => {
    expect(plano(analizarWhatsapp('salida el *viernes* y regreso el *lunes*'))).toBe(
      'salida el <negrilla>viernes</negrilla> y regreso el <negrilla>lunes</negrilla>'
    );
  });

  it('funciona pegado a signos de puntuación', () => {
    expect(plano(analizarWhatsapp('¡El *Plan a Tolú & Coveñas*, listo!'))).toBe(
      '¡El <negrilla>Plan a Tolú & Coveñas</negrilla>, listo!'
    );
  });

  it('marca una línea entera', () => {
    expect(plano(analizarWhatsapp('*Plan a Tolú & Coveñas*'))).toBe(
      '<negrilla>Plan a Tolú & Coveñas</negrilla>'
    );
  });
});

describe('cursiva, tachado y monoespaciado', () => {
  it('_texto_ es cursiva', () => {
    expect(plano(analizarWhatsapp('eso es _urgente_'))).toBe('eso es <cursiva>urgente</cursiva>');
  });

  it('~texto~ es tachado', () => {
    expect(plano(analizarWhatsapp('~$520.000~ $459.000'))).toBe(
      '<tachado>$520.000</tachado> $459.000'
    );
  });

  it('`texto` es monoespaciado', () => {
    expect(plano(analizarWhatsapp('el código `ABC123`'))).toBe(
      'el código <mono>ABC123</mono>'
    );
  });

  it('el bloque de ``` sí cruza saltos de línea y suelta las vallas', () => {
    expect(plano(analizarWhatsapp('mira:\n```\nlinea 1\nlinea 2\n```'))).toBe(
      'mira:\n<mono>linea 1\nlinea 2</mono>'
    );
  });

  it('dentro del monoespaciado NO se interpreta nada', () => {
    expect(plano(analizarWhatsapp('`no *toques* esto`'))).toBe(
      '<mono>no *toques* esto</mono>'
    );
  });
});

describe('asterisco suelto (nunca se lo come)', () => {
  it('una multiplicación con espacios queda igual', () => {
    const texto = '2 * 3 = 6';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('dos multiplicaciones en la misma línea no abren negrilla', () => {
    const texto = '2 * 3 * 4 = 24';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('una multiplicación sin espacios tampoco', () => {
    const texto = '3*4*5';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('un asterisco abierto se queda escrito', () => {
    const texto = 'dame *info';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('un asterisco al final se queda escrito', () => {
    const texto = 'una experiencia increíble!*';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('la negrilla no cruza el salto de línea', () => {
    const texto = '*hola\nmundo*';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('el par abierto en un renglón no se cierra en el siguiente', () => {
    expect(plano(analizarWhatsapp('*Plan Tolú\nsalida el *viernes*'))).toBe(
      '*Plan Tolú\nsalida el <negrilla>viernes</negrilla>'
    );
  });

  it('no cierra con un asterisco precedido de espacio', () => {
    const texto = '*hola *';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });
});

describe('precios y montos (lo que más manda el bot)', () => {
  it('no toca $459.000', () => {
    const texto = 'Son $459.000 por persona en acomodación múltiple';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('*30%* queda en negrilla con el símbolo adentro', () => {
    expect(plano(analizarWhatsapp('*30%* de descuento'))).toBe(
      '<negrilla>30%</negrilla> de descuento'
    );
  });

  it('*$459.000* queda en negrilla', () => {
    expect(plano(analizarWhatsapp('desde *$459.000* por persona'))).toBe(
      'desde <negrilla>$459.000</negrilla> por persona'
    );
  });
});

describe('guiones bajos que NO son cursiva', () => {
  it('no rompe un identificador con guiones bajos', () => {
    const texto = 'el archivo mi_foto_1.jpg no llegó';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('no rompe una URL con guiones bajos', () => {
    const texto = 'https://ejemplo.com/fotos/mi_foto_1.jpg';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('deja literal el __doble guión bajo__ de markdown', () => {
    const texto = '__init__';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('deja literal el ~~tachado~~ de markdown', () => {
    const texto = '~~cancelado~~';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });
});

describe('doble asterisco (markdown por costumbre)', () => {
  it('**texto** se lee como una sola negrilla, sin asteriscos sobrantes', () => {
    expect(plano(analizarWhatsapp('**Plan a Tolú**'))).toBe(
      '<negrilla>Plan a Tolú</negrilla>'
    );
  });

  it('se mezcla con la negrilla de WhatsApp en la misma línea', () => {
    expect(plano(analizarWhatsapp('**Plan** salida el *viernes*'))).toBe(
      '<negrilla>Plan</negrilla> salida el <negrilla>viernes</negrilla>'
    );
  });

  it('un ** sin cierre se queda escrito', () => {
    const texto = '**hola';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('*** no arma nada', () => {
    const texto = '***';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });
});

describe('anidamiento', () => {
  it('*negrilla con _cursiva_ adentro*', () => {
    expect(plano(analizarWhatsapp('*negrilla con _cursiva_ adentro*'))).toBe(
      '<negrilla>negrilla con <cursiva>cursiva</cursiva> adentro</negrilla>'
    );
  });

  it('devuelve los hijos anidados como árbol', () => {
    expect(analizarWhatsapp('*a _b_*')).toEqual([
      {
        tipo: 'negrilla',
        hijos: [
          { tipo: 'texto', texto: 'a ' },
          { tipo: 'cursiva', hijos: [{ tipo: 'texto', texto: 'b' }] },
        ],
      },
    ]);
  });

  it('degrada sin romperse si el anidado no cierra', () => {
    expect(plano(analizarWhatsapp('*negrilla con _cursiva a medias*'))).toBe(
      '<negrilla>negrilla con _cursiva a medias</negrilla>'
    );
  });
});

describe('saltos de línea', () => {
  it('los conserva dentro del texto (los pinta whitespace-pre-wrap)', () => {
    expect(analizarWhatsapp('*Plan a Tolú*\nSalida el *viernes*')).toEqual([
      { tipo: 'negrilla', hijos: [{ tipo: 'texto', texto: 'Plan a Tolú' }] },
      { tipo: 'texto', texto: '\nSalida el ' },
      { tipo: 'negrilla', hijos: [{ tipo: 'texto', texto: 'viernes' }] },
    ]);
  });

  it('conserva los renglones en blanco', () => {
    const texto = 'línea 1\n\nlínea 3';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });

  it('no pierde ningún carácter frente al original', () => {
    const casos = [
      'Hola *mundo*\n\n_segunda_ línea\ncon ~tachado~ y `mono`',
      '2 * 3 = 6 y dame *info',
      '**doble** y ***',
      'https://ejemplo.com/a_b_c',
    ];
    const soloTexto = (nodos: NodoWhatsapp[]): string =>
      nodos.map((n) => (n.tipo === 'texto' ? n.texto : soloTexto(n.hijos))).join('');
    for (const caso of casos) {
      // Lo que queda es el original menos los marcadores que sí se aplicaron.
      const limpio = soloTexto(analizarWhatsapp(caso));
      expect(caso.replace(/[*_~`]/g, '')).toBe(limpio.replace(/[*_~`]/g, ''));
    }
  });
});

describe('mensajes reales del bot de viajes', () => {
  it('pinta un mensaje completo', () => {
    const mensaje =
      '¡Listo! Te confirmo el *Plan a Tolú & Coveñas* 🌴\n' +
      'Salida el *viernes* y regreso el *lunes*.\n' +
      'Queda en $459.000 por persona (acomodación múltiple).';
    expect(plano(analizarWhatsapp(mensaje))).toBe(
      '¡Listo! Te confirmo el <negrilla>Plan a Tolú & Coveñas</negrilla> 🌴\n' +
        'Salida el <negrilla>viernes</negrilla> y regreso el <negrilla>lunes</negrilla>.\n' +
        'Queda en $459.000 por persona (acomodación múltiple).'
    );
  });

  it('un teléfono enmascarado no se rompe', () => {
    const texto = 'Escríbenos al 3XXXXXXXXX';
    expect(analizarWhatsapp(texto)).toEqual([{ tipo: 'texto', texto }]);
  });
});

describe('defensas', () => {
  it('un texto absurdamente largo se pinta plano en vez de colgar la pestaña', () => {
    const texto = '*'.repeat(30000);
    const nodos = analizarWhatsapp(texto);
    expect(nodos).toEqual([{ tipo: 'texto', texto }]);
  });

  it('el anidamiento profundo degrada a texto en vez de reventar la pila', () => {
    const texto = '*a _b ~c `d *e*` c~ b_ a*';
    // Lo que importa: responde, no pierde caracteres y el nivel de más queda
    // como texto plano.
    const soloTexto = (nodos: NodoWhatsapp[]): string =>
      nodos.map((n) => (n.tipo === 'texto' ? n.texto : soloTexto(n.hijos))).join('');
    expect(soloTexto(analizarWhatsapp(texto))).toContain('e');
    expect(plano(analizarWhatsapp(texto))).toContain('<negrilla>');
  });
});

describe('formatearWhatsapp (nodos de React)', () => {
  it('devuelve strings y elementos, nunca HTML', () => {
    const salida = formatearWhatsapp('hola *mundo*');
    expect(salida[0]).toBe('hola ');
    const negrilla = salida[1] as ReactElement<{ children: ReactNode[] }>;
    expect(isValidElement(negrilla)).toBe(true);
    expect(negrilla.type).toBe('strong');
    expect(negrilla.props.children).toEqual(['mundo']);
  });

  it('usa la etiqueta semántica de cada marca', () => {
    const tipos = (texto: string) =>
      formatearWhatsapp(texto)
        .filter(isValidElement)
        .map((el) => (el as ReactElement).type);
    expect(tipos('*a* _b_ ~c~ `d`')).toEqual(['strong', 'em', 'del', 'code']);
  });

  it('NUNCA emite dangerouslySetInnerHTML ni props fuera de key/children', () => {
    const revisar = (nodos: ReactNode[]) => {
      for (const nodo of nodos) {
        if (typeof nodo === 'string') continue;
        expect(isValidElement(nodo)).toBe(true);
        const el = nodo as ReactElement<Record<string, unknown>>;
        expect(Object.keys(el.props)).toEqual(['children']);
        expect(el.props).not.toHaveProperty('dangerouslySetInnerHTML');
        revisar(el.props.children as ReactNode[]);
      }
    };
    revisar(
      formatearWhatsapp(
        '*<script>alert(1)</script>* y _<img src=x onerror=alert(1)>_ y `<b>x</b>`'
      )
    );
  });

  it('el texto peligroso viaja como string, sin interpretarse', () => {
    const salida = formatearWhatsapp('*<script>alert(1)</script>*');
    const el = salida[0] as ReactElement<{ children: ReactNode[] }>;
    expect(el.type).toBe('strong');
    expect(el.props.children).toEqual(['<script>alert(1)</script>']);
  });

  it('el HTML que sale de React va escapado (prueba de fuego contra XSS)', () => {
    const html = renderToStaticMarkup(
      createElement(
        'div',
        null,
        formatearWhatsapp('*<script>alert(1)</script>* y <img src=x onerror=alert(1)>')
      )
    );
    expect(html).toContain('<strong>');
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img');
  });

  it('cada elemento lleva key (React no se queja al pintar la lista)', () => {
    const salida = formatearWhatsapp('*a* y *b*');
    const claves = salida.filter(isValidElement).map((el) => (el as ReactElement).key);
    expect(claves).toEqual(['wa.0', 'wa.2']);
    expect(new Set(claves).size).toBe(claves.length);
  });
});
