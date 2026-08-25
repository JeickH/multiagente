/**
 * Formato de WhatsApp → nodos de React.
 *
 * WhatsApp NO usa Markdown: usa `*negrilla*`, `_cursiva_`, `~tachado~` y
 * ` ```monoespaciado``` `. El system prompt de los bots lo pide con todas las
 * letras (ver `backend/app/bot_contexts/demo_viajes.md`, "Tono y estilo"), así
 * que los mensajes que van y vienen están llenos de `*viernes*` y
 * `*Plan a Tolú & Coveñas*`. En el celular del cliente eso se ve en negrilla;
 * en nuestras pantallas se veía el asterisco crudo porque el contenido se
 * pintaba como texto plano.
 *
 * SEGURIDAD (no negociable): este texto lo escribe el cliente final por
 * WhatsApp — es contenido de un tercero no confiable. Este módulo devuelve
 * **nodos de React**, nunca HTML. No hay `dangerouslySetInnerHTML` ni
 * concatenación de strings con tags: React escapa el texto solo y el XSS deja
 * de ser posible por construcción. Si algún día hace falta un formato nuevo,
 * se agrega un nodo más — nunca una cadena de HTML.
 *
 * Tampoco se usa una librería de Markdown: en Markdown `*x*` es CURSIVA, no
 * negrilla, así que renderizaría mal justo el caso que motivó esto.
 *
 * Reglas del parser (elegidas para que un asterisco suelto nunca dañe el
 * mensaje; ante la duda, se deja el texto tal cual):
 *
 *   1. La apertura va pegada al contenido: `* 3 *` no es negrilla. Esto es lo
 *      que salva a `2 * 3 * 4` y a cualquier multiplicación.
 *   2. La marca no arranca en mitad de una palabra ni cierra en mitad de otra:
 *      `3*4*5` y `mi_foto_1.jpg` (o una URL con guiones bajos) quedan intactos.
 *   3. La marca no cruza saltos de línea (salvo el bloque ``` ```…``` ```). Un
 *      asterisco huérfano en el renglón 1 no puede poner en negrilla medio
 *      mensaje.
 *   4. Sin cierre válido, el marcador se pinta literal. Nunca se come.
 *   5. `**doble**` se trata como negrilla simple: es el markdown que a la gente
 *      (y al modelo) se le escapa por costumbre. Es la misma decisión que ya
 *      toma el backend con la salida del LLM (`_to_whatsapp_format`).
 *
 * Los saltos de línea NO se convierten en `<br>`: se quedan dentro del texto y
 * los pinta el contenedor con `whitespace-pre-wrap`, igual que antes de este
 * cambio. Todo contenedor que use estos nodos debe conservar esa clase.
 */
import { createElement, type ReactNode } from 'react';

export type MarcaWhatsapp = 'negrilla' | 'cursiva' | 'tachado' | 'mono';

export type NodoWhatsapp =
  | { tipo: 'texto'; texto: string }
  | { tipo: MarcaWhatsapp; hijos: NodoWhatsapp[] };

/**
 * Qué cuenta como "estar dentro de una palabra". Se evita `\p{L}` a propósito:
 * el `tsconfig` apunta a ES2017 y TypeScript rechaza las propiedades Unicode
 * por debajo de ES2018. El rango Latin-1 cubre el español (á, é, í, ó, ú, ñ,
 * ü y sus mayúsculas) sin romper el build.
 */
const CARACTER_DE_PALABRA = /[0-9A-Za-zÀ-ÖØ-öø-ÿ]/;

/** Anidamiento máximo (`*negrilla con _cursiva_ adentro*` es nivel 2). */
const PROFUNDIDAD_MAXIMA = 4;

/**
 * Por encima de esto se pinta plano. La búsqueda del cierre es O(n²) en el peor
 * caso (un texto que sea puro `*`), y ningún mensaje de WhatsApp legítimo se
 * acerca a este tamaño.
 */
const LARGO_MAXIMO = 20000;

type Apertura = {
  marca: MarcaWhatsapp;
  /** El texto del marcador; el cierre es idéntico. */
  marcador: string;
  /** Si adentro pueden vivir otras marcas (el monoespaciado es literal). */
  anidable: boolean;
  /** Si puede cruzar saltos de línea (solo el bloque de ```). */
  multilinea: boolean;
};

function aperturaEn(texto: string, i: number): Apertura | null {
  switch (texto[i]) {
    case '*':
      return {
        marca: 'negrilla',
        marcador: texto[i + 1] === '*' ? '**' : '*',
        anidable: true,
        multilinea: false,
      };
    case '_':
      return { marca: 'cursiva', marcador: '_', anidable: true, multilinea: false };
    case '~':
      return { marca: 'tachado', marcador: '~', anidable: true, multilinea: false };
    case '`':
      return texto.startsWith('```', i)
        ? { marca: 'mono', marcador: '```', anidable: false, multilinea: true }
        : { marca: 'mono', marcador: '`', anidable: false, multilinea: false };
    default:
      return null;
  }
}

function esEspacio(c: string | undefined): boolean {
  return c !== undefined && /\s/.test(c);
}

function esPalabra(c: string | undefined): boolean {
  return c !== undefined && CARACTER_DE_PALABRA.test(c);
}

/**
 * Índice donde arranca el cierre de la marca abierta en `inicio`, o `null` si
 * no hay uno válido (y entonces el marcador es texto y punto).
 */
function buscarCierre(texto: string, inicio: number, ap: Apertura): number | null {
  const desde = inicio + ap.marcador.length;
  const primero = texto[desde];
  if (primero === undefined) return null;
  // Regla 1: `* 3 *`, `*\n` y compañía no abren nada.
  if (!ap.multilinea && esEspacio(primero)) return null;

  for (let j = desde + 1; j < texto.length; j += 1) {
    if (!ap.multilinea && texto[j] === '\n') return null; // regla 3
    if (!texto.startsWith(ap.marcador, j)) continue;
    // El cierre va pegado al contenido: `*hola *` no cierra nada.
    if (!ap.multilinea && esEspacio(texto[j - 1])) continue;
    // Regla 2: `mi_foto_1.jpg` no cierra en mitad de la palabra.
    if (esPalabra(texto[j + ap.marcador.length])) continue;
    return j;
  }
  return null;
}

function analizar(texto: string, profundidad: number): NodoWhatsapp[] {
  if (!texto) return [];
  if (profundidad >= PROFUNDIDAD_MAXIMA || texto.length > LARGO_MAXIMO) {
    return [{ tipo: 'texto', texto }];
  }

  const nodos: NodoWhatsapp[] = [];
  let pendiente = '';
  let i = 0;

  const soltarTexto = () => {
    if (pendiente) {
      nodos.push({ tipo: 'texto', texto: pendiente });
      pendiente = '';
    }
  };

  while (i < texto.length) {
    const ap = aperturaEn(texto, i);
    // Regla 2 del lado de la apertura: en `3*4*5` el `*` viene pegado a un
    // número, así que no abre negrilla.
    if (!ap || esPalabra(texto[i - 1])) {
      pendiente += texto[i];
      i += 1;
      continue;
    }

    // Marcador repetido que NO es `**`: `__init__`, `~~cancelado~~`, `***`. Se
    // pinta literal la racha completa. Si se dejara pasar, el segundo carácter
    // abriría por su cuenta y saldría medio formateado (`_` + cursiva(init) +
    // `_`), que se ve peor que el texto original. `**negrilla**` no llega
    // aquí: ya se leyó como un marcador de dos.
    if (!ap.multilinea && texto[i + ap.marcador.length] === ap.marcador[0]) {
      let fin = i;
      while (texto[fin] === ap.marcador[0]) fin += 1;
      pendiente += texto.slice(i, fin);
      i = fin;
      continue;
    }

    const cierre = buscarCierre(texto, i, ap);
    if (cierre === null) {
      // Regla 4: el marcador se pinta tal cual. Se avanza UN carácter (no el
      // largo del marcador) para que el segundo `*` de un `**` sin pareja
      // todavía tenga su oportunidad de abrir.
      pendiente += texto[i];
      i += 1;
      continue;
    }

    let contenido = texto.slice(i + ap.marcador.length, cierre);
    if (ap.multilinea) {
      // ```\ncódigo\n``` es como lo escribe casi siempre un modelo: el salto
      // pegado a la valla es parte de la valla, no del contenido.
      contenido = contenido.replace(/^\n/, '').replace(/\n$/, '');
      if (!contenido.trim()) {
        pendiente += texto[i];
        i += 1;
        continue;
      }
    }

    soltarTexto();
    nodos.push({
      tipo: ap.marca,
      hijos: ap.anidable
        ? analizar(contenido, profundidad + 1)
        : [{ tipo: 'texto', texto: contenido }],
    });
    i = cierre + ap.marcador.length;
  }

  soltarTexto();
  return nodos;
}

/**
 * Parte un mensaje de WhatsApp en nodos. Función pura y sin React: es la que
 * cubren las pruebas (`formatoWhatsapp.test.ts`).
 *
 * Texto vacío, `null` o `undefined` devuelven `[]`.
 */
export function analizarWhatsapp(texto: string | null | undefined): NodoWhatsapp[] {
  if (!texto) return [];
  return analizar(texto, 0);
}

const ETIQUETA: Record<MarcaWhatsapp, string> = {
  negrilla: 'strong',
  cursiva: 'em',
  tachado: 'del',
  mono: 'code',
};

function aReact(nodos: NodoWhatsapp[], prefijo: string): ReactNode[] {
  return nodos.map((nodo, indice) => {
    if (nodo.tipo === 'texto') return nodo.texto;
    const clave = `${prefijo}.${indice}`;
    // `createElement` con los hijos en un array: React escapa cada string y
    // jamás interpreta HTML. Es el punto exacto donde muere el XSS.
    return createElement(ETIQUETA[nodo.tipo], { key: clave }, aReact(nodo.hijos, clave));
  });
}

/**
 * Lo que se pinta en la burbuja: `{formatearWhatsapp(mensaje.content)}`.
 *
 * El contenedor debe conservar `whitespace-pre-wrap` — los saltos de línea
 * siguen viviendo dentro del texto.
 */
export function formatearWhatsapp(texto: string | null | undefined): ReactNode[] {
  return aReact(analizarWhatsapp(texto), 'wa');
}
