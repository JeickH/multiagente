/**
 * Cuánto texto cabe en un mensaje de WhatsApp, y qué decir cuando no cabe.
 *
 * El número no es nuestro: es de Twilio, que corta el `Body` de cualquier canal
 * en 1.600 caracteres y responde 400 con el código 21617 ("The concatenated
 * message body exceeds the 1600 character limit",
 * https://www.twilio.com/docs/api/errors/21617). WhatsApp solo aceptaría 4.096,
 * pero todo sale por Twilio, así que manda el más chico.
 *
 * Mismo trato que `lib/adjuntos.ts` con el tamaño de los archivos: acá se
 * valida para ahorrarle el viaje a la asesora —y para que vea venir el tope
 * mientras escribe, en vez de enterarse al pulsar Enviar—, pero **el que manda
 * es el backend**, que mide lo mismo en `POST /mensajes/conversaciones/{id}/enviar`
 * y responde 400 con este mismo texto.
 *
 * ⚠ El límite está declarado en dos lados: acá y en
 * `backend/app/services/messaging/base.py` (`MAX_TEXTO_WHATSAPP`). Que no se
 * separen lo cuida `backend/tests/test_mensaje_largo.py::test_el_frontend_declara_el_mismo_limite`,
 * que lee ESTE archivo y compara el número. Si cambias uno, el test te para
 * hasta que cambies el otro. (El caption de un adjunto es otro cuento y tiene
 * su propio tope: `MAX_CAPTION`, 900, en `lib/adjuntos.ts`.)
 */

/** Tope de caracteres de un mensaje de texto (Twilio 21617). */
export const MAX_TEXTO_WHATSAPP = 1600;

/**
 * Desde dónde se muestra el contador. Avisar desde el primer carácter sería
 * ruido: los mensajes normales de la bandeja no llegan ni a 300. El mismo
 * criterio que ya usa el contador del caption (avisa en los últimos 100).
 */
export const AVISO_TEXTO = MAX_TEXTO_WHATSAPP - 200;

/** 1742 → "1.742". Punto de miles, como se lee en Colombia. */
function miles(n: number): string {
  return n.toLocaleString('es-CO');
}

/** El contador del compositor: "1.742/1.600 caracteres". */
export function contadorTexto(largo: number): string {
  return `${miles(largo)}/${miles(MAX_TEXTO_WHATSAPP)} caracteres`;
}

/**
 * Lo que se le dice a la asesora cuando se pasó. Es palabra por palabra lo que
 * responde el backend si el mensaje igual llega allá, para que no lea dos
 * explicaciones distintas del mismo problema.
 */
export function motivoTextoMuyLargo(largo: number): string {
  return (
    `El mensaje es muy largo para WhatsApp: tiene ${miles(largo)} caracteres ` +
    `y el máximo son ${miles(MAX_TEXTO_WHATSAPP)}. Pártelo en dos y vuelve a enviarlo.`
  );
}

/** ¿Se puede enviar este texto? Justo en el límite sí; uno más, no. */
export function textoExcedido(texto: string): boolean {
  return (texto || '').length > MAX_TEXTO_WHATSAPP;
}
