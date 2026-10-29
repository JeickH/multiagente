/**
 * A dónde llevan los botones de contacto con Gloma (landing, demo y 404).
 *
 * Decisión del CEO (2026-10-28): mientras la cuenta de Twilio del WhatsApp de
 * Gloma no esté aprobada, TODO botón de contacto ("Agendar una llamada",
 * "Hablar con un asesor") abre el chat de la misma página, donde contesta el
 * agente y agenda la reunión. El único enlace a WhatsApp es el del footer de
 * la landing, que sigue yendo al número de siempre.
 *
 * El día que Twilio apruebe la cuenta, el cambio es UNA línea:
 * `WHATSAPP_DEL_AGENTE_ACTIVO = true`. Con eso todos los botones (y el footer)
 * pasan al WhatsApp atendido por el agente. Nada más cambia.
 */

/** Interruptor único. `true` = el WhatsApp del agente ya envía y recibe. */
export const WHATSAPP_DEL_AGENTE_ACTIVO = false;

/** WhatsApp atendido por el agente (cuenta de Twilio de Gloma). */
const NUMERO_AGENTE = '573239087528';

/** WhatsApp de siempre, el que muestra el footer mientras el agente no está activo. */
const NUMERO_FOOTER = '573150764000';

/** Texto prellenado del footer: el mismo que tenía la landing. */
export const TEXTO_FOOTER = 'Hola Gloma, tengo una agencia de viajes y quiero ver una demo';

/** Lo que el visitante "dice" al tocar «Agendar una llamada»: el agente responde con las franjas. */
export const MENSAJE_AGENDAR = 'Quiero agendar una llamada';

export function enlaceWhatsapp(numero: string, texto?: string): string {
  const base = `https://wa.me/${numero}`;
  return texto ? `${base}?text=${encodeURIComponent(texto)}` : base;
}

/** Número que se lee en el footer, el mismo al que lleva su enlace. */
export function telefonoFooter(): string {
  return WHATSAPP_DEL_AGENTE_ACTIVO ? '+57 323 908 7528' : '+57 315 076 4000';
}

/** Enlace del footer: hoy el número de siempre; con el agente activo, el del agente. */
export function enlaceWhatsappFooter(): string {
  return enlaceWhatsapp(WHATSAPP_DEL_AGENTE_ACTIVO ? NUMERO_AGENTE : NUMERO_FOOTER, TEXTO_FOOTER);
}

/**
 * Enlace de los botones de contacto. `null` mientras el agente no esté activo:
 * quien lo use abre el chat de la página en lugar de un enlace.
 */
export function enlaceWhatsappContacto(texto?: string): string | null {
  return WHATSAPP_DEL_AGENTE_ACTIVO ? enlaceWhatsapp(NUMERO_AGENTE, texto) : null;
}
