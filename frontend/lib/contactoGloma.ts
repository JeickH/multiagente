/**
 * A dónde llevan los botones de contacto con Gloma (landing, demo y 404).
 *
 * Decisiones del CEO:
 *  - 2026-10-28: mientras la cuenta de Twilio de Gloma no estaba aprobada, todo
 *    botón de contacto abría el chat de la página; el footer iba al número de
 *    siempre.
 *  - 2026-10-29: Twilio aprobó la cuenta (perfil personal en Trust Hub).
 *    «Hablar con un asesor» y el footer van al WhatsApp del agente, que
 *    responde por ahí. «Agendar una llamada» sigue en el chat de la página (en
 *    la demo, el calendario de Cal.com). Todo lo que dice el agente, por la web
 *    y por WhatsApp, queda en la bandeja de Gloma en la app.
 *
 *  - 2026-10-29: el WhatsApp viejo (315) sale de todos lados; el único número
 *    de Gloma es el del agente, también en el footer.
 *
 * Si el WhatsApp del agente se cae, el interruptor vuelve a `false` y los
 * botones regresan al chat de la página; el footer sigue mostrando el número.
 */

/** Interruptor único. `true` = el WhatsApp del agente envía y recibe. */
export const WHATSAPP_DEL_AGENTE_ACTIVO = true;

/** WhatsApp atendido por el agente (cuenta de Twilio de Gloma). */
const NUMERO_AGENTE = '573239087528';

/** Texto prellenado del footer: el mismo que tenía la landing. */
export const TEXTO_FOOTER = 'Hola Gloma, tengo una agencia de viajes y quiero ver una demo';

/** Texto prellenado de «Hablar con un asesor» en el WhatsApp del agente. */
export const MENSAJE_ASESOR = 'Hola Gloma, quiero hablar con un asesor';

/** Lo que el visitante "dice" al tocar «Agendar una llamada»: el agente responde con las franjas. */
export const MENSAJE_AGENDAR = 'Quiero agendar una llamada';

export function enlaceWhatsapp(numero: string, texto?: string): string {
  const base = `https://wa.me/${numero}`;
  return texto ? `${base}?text=${encodeURIComponent(texto)}` : base;
}

/** Número que se lee en el footer, el mismo al que lleva su enlace. */
export function telefonoFooter(): string {
  return '+57 323 908 7528';
}

/** Enlace del footer: el WhatsApp de Gloma, que atiende el agente. */
export function enlaceWhatsappFooter(): string {
  return enlaceWhatsapp(NUMERO_AGENTE, TEXTO_FOOTER);
}

/**
 * Enlace de los botones de contacto. `null` mientras el agente no esté activo:
 * quien lo use abre el chat de la página en lugar de un enlace.
 */
export function enlaceWhatsappContacto(texto?: string): string | null {
  return WHATSAPP_DEL_AGENTE_ACTIVO ? enlaceWhatsapp(NUMERO_AGENTE, texto) : null;
}
