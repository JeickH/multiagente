import Head from 'next/head';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';

import GlomaChatWidget, { BotonAgendar, BotonAsesor } from '../components/GlomaChatWidget';
import { TEXTOS_AGENDAR } from '../lib/agendarLlamada';
import { enlaceWhatsappFooter, telefonoFooter } from '../lib/contactoGloma';
import { CHATS_MES_OPCIONES } from '../lib/leads';

/**
 * Landing page de Gloma.
 *
 * Identidad — paleta alineada al nuevo mercado objetivo (agencias de viajes),
 * la misma de la landing /automatas (Gorvek):
 *  - Deep Forest #004D40, Algorithmic Mint #4DB6AC, Soft Mint #E0F2F1,
 *    Technical Black #101817.
 *  - El acento (#4DB6AC) se reserva para CTAs, métricas y highlights.
 *  - Tipografía: Syne (títulos) + Inter (cuerpo) — sin cambios.
 */

const BRAND = {
  bgBase: '#101817',
  bgAlt: '#0B1413',
  forest: '#004D40',
  mint: '#4DB6AC',
  softMint: '#E0F2F1',
  // Destello del logo. En la landing solo marca la instalación sin costo.
  golden: '#F5C24B',
  mintSoft: 'rgba(77,182,172,0.12)',
  cardBg: 'rgba(255,255,255,0.03)',
  cardBorder: 'rgba(77,182,172,0.15)',
  cardBorderHover: 'rgba(77,182,172,0.45)',
  text: '#E6EFEE',
  textMuted: 'rgba(230,239,238,0.65)',
  textDim: 'rgba(230,239,238,0.45)',
};

// --- Íconos ---------------------------------------------------------------

/**
 * Íconos de línea (trazo mint) — el mismo lenguaje de las piezas de Instagram.
 * Reemplazan los PNG `ld_*.png`, que eran ilustraciones con otro estilo.
 */
type IconoNombre =
  | 'personaliza' | 'integraciones' | 'contexto' | 'escalamiento' | 'medicion'
  | 'soporte' | 'mensajes' | 'retorno' | 'horas' | 'reenganche' | 'flecha';

const ICONOS: Record<IconoNombre, React.ReactNode> = {
  personaliza: <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3zM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z" />,
  integraciones: <path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0V7zM12 17v5" />,
  contexto: (
    <>
      <path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  escalamiento: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20v-1a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v1M16 4.5a3.5 3.5 0 0 1 0 7M21 20v-1a5 5 0 0 0-3-4.6" />
    </>
  ),
  medicion: <path d="M3 3v18h18M8 17v-5M13 17V8M18 17v-8" />,
  soporte: <path d="M4 15v-3a8 8 0 0 1 16 0v3M4 15h3v5H5a1 1 0 0 1-1-1v-4zM20 15h-3v5h2a1 1 0 0 0 1-1v-4z" />,
  mensajes: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.6A8 8 0 1 1 21 12zM8 11h8M8 14h5" />,
  retorno: <path d="M3 17l6-6 4 4 8-8M15 7h6v6" />,
  horas: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  reenganche: <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 3v5h5M4 13a8 8 0 0 0 14.3 4.9L20 16M20 21v-5h-5" />,
  flecha: <path d="M4 12h15m-5-5 5 5-5 5" />,
};

function Icono({ nombre, size = 26 }: { nombre: IconoNombre; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={BRAND.mint}
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONOS[nombre]}
    </svg>
  );
}

// --- Datos -----------------------------------------------------------------
type PreviewSection = {
  title: string;
  text: string;
  reverse: boolean;
  /** Captura en `public/`. Sin `image`, el bloque pinta `mock`. */
  image?: string;
  /** Maqueta en JSX en lugar de una captura. */
  mock?: 'recordatorios';
  /** Muestra la imagen completa (sin recortar). */
  contain?: boolean;
};

/**
 * «Lo que cambia en tu negocio» (ajustes del CEO, 2026-10-26): cada título dice
 * qué gana el negocio; la mecánica va una sola vez, abajo. Campañas salió de aquí
 * y queda solo en Precios. «Tu equipo entra a cerrar, no a saludar» es la única
 * antítesis de la página: ningún otro título usa esa estructura.
 */
const PREVIEW_SECTIONS: PreviewSection[] = [
  {
    title: 'Quien pregunta cuánto vale recibe el precio en minutos, a cualquier hora',
    text: 'Pide fechas, cuántos viajan y qué buscan antes de cotizar con tus tarifas. Si le falta un dato, no lo inventa: se lo pasa a tu equipo.',
    image: '/gloma/preview_chat_agente.png',
    reverse: false,
  },
  {
    title: 'Tu equipo entra a cerrar, no a saludar',
    text: 'Cuando el cliente está listo o pide una persona, le pasa la conversación a tu equipo o a tu recepción con todo el historial. Nadie le vuelve a preguntar lo mismo.',
    image: '/gloma/preview6.png',
    reverse: true,
  },
  {
    // La cadena de reenganches de `bot_runner` (Sprint 27): los bots en
    // producción la tienen en 3 (15 min, 5 h y 23 h de silencio; la ventana de
    // 24 h de WhatsApp no deja más). Si no vuelve, el abandono se le asigna a
    // un asesor y, si ya había recibido información, entra a /agendamientos.
    title: 'Recupera a los interesados que dejaron de contestar',
    text: 'Les escribe hasta 3 veces en las 24 horas siguientes. Si no vuelven, quedan en la lista de llamadas de tu asesor.',
    mock: 'recordatorios',
    reverse: false,
  },
  {
    title: 'Ves cuánta venta se te queda en el aire, y en qué paso',
    text: 'Un tablero con el resultado de tus conversaciones: cuántas terminan en reserva o en manos de tu equipo, cuántas se quedan a medias y en qué paso se va la gente. Con eso decidimos juntos qué ajustar.',
    image: '/gloma/preview_dashboard_demo.png',
    reverse: true,
    // Captura del reporte, más ancha que 4:3: se muestra completa para que
    // no se corten las cifras de la derecha.
    contain: true,
  },
];

/**
 * Preguntas frecuentes. Las respuestas salen de lo que el CEO definió el
 * 2026-09-27 y del contexto del bot (`bot_contexts/gloma.md`): si cambia
 * algo aquí, se cambia allá, o Lía y la página se contradicen.
 */
const FAQ = [
  {
    // [CONFIRMAR CEO] La definición de conversación puede cambiar con los precios nuevos.
    q: '¿Qué cuenta como una conversación?',
    a: 'Un chat con un cliente dentro de una ventana de 24 horas. Si ese mismo cliente vuelve a escribir después de las 24 horas, cuenta como una conversación nueva.',
  },
  {
    // Plan P1 «Permanencia 6» (CEO, 2026-10-28). Cifras en `PRECIOS`.
    q: '¿Tengo que pagar una mensualidad?',
    a: 'Sí, pero después de la prueba: los primeros 14 días no pagas nada. Si quieres seguir, pagas una mensualidad que incluye 1.000 conversaciones al mes, el soporte y el mantenimiento, y la instalación no te cuesta nada. El plan es de mínimo 6 meses: si decides salir antes, pagas 150.000 COP por cada mes que falte.',
  },
  {
    q: '¿Qué pasa cuando termina la prueba gratis?',
    a: 'Te mostramos el reporte de los 14 días: dónde se te está yendo la plata, cuánto tardan en contestar tu equipo y el agente, y a qué horas te escriben. Con eso decides. Si sigues, arrancamos tu plan; si no, no pagas nada.',
  },
  {
    q: '¿El agente puede inventar precios o disponibilidad?',
    a: 'No. Contesta solo con la información que nos das (tarifarios, planes, políticas) y tiene prohibido inventar precios, cupos o promociones. Si le falta un dato, lo dice y le pasa la conversación a tu equipo con todo lo que el cliente ya preguntó. Si tu sistema de reservas no está conectado, contesta con tu tarifario y la confirmación del cupo la hace tu equipo.',
  },
  {
    q: '¿Qué pasa de noche, cuando un cliente quiere reservar?',
    a: 'El agente le contesta, le da el precio con tu tarifario y toma sus datos. Cuando el cliente quiere confirmar o pide hablar con alguien, la conversación queda en la bandeja de tu equipo con todo lo que ya habló. Si tienes recepción de turno, la puede tomar desde ahí. A primera hora, tu equipo encuentra la lista de quién quedó esperando.',
  },
  {
    q: '¿Reemplaza a mis asesores?',
    a: 'No. El agente responde las preguntas de siempre; cerrar la venta sigue siendo de tu asesor, que recibe al viajero con todo el historial.',
  },
  {
    // El motor todavía no transcribe audios: ante una nota de voz el agente
    // pide que se la escriban (`llm_engine`, sección «Notas de voz»).
    q: '¿Atiende llamadas?',
    a: 'No. Gloma atiende tu WhatsApp por mensaje escrito; si un viajero manda una nota de voz, el agente le pide con amabilidad que se lo escriba. Las llamadas siguen llegando a tu equipo.',
  },
  {
    q: '¿Qué tasa de cierre voy a tener?',
    a: 'No hay un porcentaje genérico que prometer. El agente arranca con una tasa parecida a la que ya tienes, porque vende con tus mismos mensajes e información; la medimos en el tablero y desde ahí trabajamos para subirla.',
  },
  {
    q: '¿Cuánto tarda en estar listo?',
    a: 'Depende de cuánta información tengamos de tu operación y de la conexión de tu número con Meta, que depende de tus accesos. Lo estimamos en la demo con tu caso. Una vez en marcha, los primeros 10 días son de ajuste.',
  },
  {
    q: '¿Tengo que entregarles mi número principal?',
    a: 'No. Puedes empezar con otro número de tu negocio, por ejemplo el de recepción. Tus datos viven en tu propia cuenta, aislada de las demás, y tus conversaciones no se usan para entrenar modelos de IA. Antes de salir en vivo pruebas tu agente en el simulador.',
  },
];

/**
 * Ruta de arranque de un cliente nuevo, con el reparto «Tú / Nosotros». Desde el
 * 2026-10-28 (CEO) todo cliente empieza con la prueba gratis de 14 días, donde
 * se mide dónde se le va la plata; la instalación completa va al comprar y no
 * tiene costo (plan P1 de `ventas/costos/PROPUESTAS_COMERCIALES.html`).
 */
const PASOS_INICIO = [
  {
    titulo: 'Nos cuentas cómo vendes',
    tu: 'Una reunión para contarnos cómo vende tu negocio, y nos compartes tus tarifas, planes y políticas.',
    nosotros: 'Preparamos tu agente con tu tarifario, tus mensajes y el tono de tu marca.',
    etiqueta: null,
  },
  {
    titulo: '14 días de prueba gratis',
    tu: 'Nos das acceso a uno de tus números comerciales. Te guiamos paso a paso.',
    nosotros: 'Lo conectamos y el agente empieza a contestarles a tus clientes.',
    etiqueta: 'Gratis',
  },
  {
    titulo: 'Te mostramos dónde se te va la plata',
    tu: 'Revisas el reporte con nosotros y decides si sigues.',
    nosotros: 'Te mostramos en qué paso se pierden las ventas, los puntos débiles de tu atención y cuánta plata se te queda en el aire cada semana.',
    etiqueta: null,
  },
  {
    titulo: 'Arranca tu plan',
    tu: 'Nos escribes por WhatsApp cuando algo cambie.',
    nosotros: 'Completamos la instalación sin costo, lo ajustamos contigo los primeros 10 días y seguimos con soporte 24/7 y mantenimiento.',
    etiqueta: 'Instalación sin costo',
  },
];

/**
 * «¿Te suena?»: paráfrasis de lo que cuentan hoteleros y empresarios (no son
 * citas textuales, por eso van sin comillas) y lo que hace Gloma con cada una.
 * Ajustes del CEO del 2026-10-26.
 */
const DOLORES: { icon: IconoNombre; dolor: string; solucion: string }[] = [
  {
    icon: 'horas',
    dolor: 'De noche no hay quien conteste el WhatsApp',
    solucion: 'El agente les contesta a la hora en que tus clientes planean el viaje, y lo que necesita una persona queda en la bandeja de tu equipo con todo el historial.',
  },
  {
    icon: 'mensajes',
    dolor: 'Saco una promoción y los mensajes se quedan sin contestar',
    solucion: 'El agente les contesta a todos los que llegan por tu pauta, al mismo tiempo, y a tu equipo le pasa los que quieren reservar.',
  },
  {
    icon: 'reenganche',
    dolor: 'Los interesados que abandonaron',
    solucion: 'El agente los recupera: les vuelve a escribir y, si no contestan, quedan en la lista de tu asesor para llamarlos.',
  },
  {
    icon: 'medicion',
    dolor: 'No tengo cómo ver cuántos clientes se me van',
    solucion: 'Ves cuántas conversaciones terminan en reserva y en qué paso se va la gente.',
  },
];

/**
 * «Funciona con lo que ya usas» (ajustes del CEO, 2026-10-26). Hoy no hay
 * ninguna conexión construida con channel managers ni PMS: todas son a la
 * medida. Prohibido decir «integrado con», «disponibilidad en tiempo real»,
 * «sin sobreventas» o dar plazos.
 */
const YA_USAS: { titulo: string; texto: string }[] = [
  {
    titulo: 'Listo hoy',
    // Excel: `services/contactos_excel.py`. Sheets: `services/pedidos_sheet.py`.
    texto: 'Tus contactos entran desde Excel. Los datos de cada reserva llegan a tu Google Sheets. Si vendes por Shopify, consulta tus pedidos.',
  },
  {
    titulo: 'Lo conectamos para ti',
    texto: 'Tu channel manager (el sistema que reparte tus tarifas y tu disponibilidad a las agencias en línea y a tu web), tu software de recepción (PMS), tu motor de reservas o tu CRM. Es un desarrollo a la medida: en la demo revisamos cuál usas y qué se puede conectar.',
  },
  {
    titulo: 'Desde el primer día',
    texto: 'Mientras tanto, el agente contesta con tu tarifario y, cuando el cliente quiere confirmar el cupo, se lo pasa a tu equipo o a tu recepción con toda la conversación.',
  },
];

/**
 * Sistemas que se nombraron en la reunión con hoteleros del 24-oct (voz del
 * cliente) más los channel managers más usados en LatAm. Desde el 2026-10-28 el
 * CEO decidió mostrarlos en blanco y negro, discretos, bajo «compatibles con…»
 * (Belfort recomendaba no hacerlo: un logo ajeno se puede leer como alianza).
 * Van siempre con la nota de «a la medida». Los logos salen de la web de cada
 * marca (SiteMinder de su cabecera, Oracle de Wikimedia Commons) y viven en
 * `public/gloma/integraciones/`; sin `logo` se pinta el nombre (Zeus no tiene
 * logo público). `alto` iguala el peso visual entre logos de forma distinta.
 */
const SISTEMAS: { nombre: string; logo?: string; alto?: number }[] = [
  { nombre: 'SiteMinder', logo: '/gloma/integraciones/siteminder.svg', alto: 22 },
  { nombre: 'Cloudbeds', logo: '/gloma/integraciones/cloudbeds.svg', alto: 26 },
  { nombre: 'Omnibees', logo: '/gloma/integraciones/omnibees.svg', alto: 30 },
  { nombre: 'RoomCloud', logo: '/gloma/integraciones/roomcloud.png', alto: 40 },
  { nombre: 'LobbyPMS', logo: '/gloma/integraciones/lobbypms.svg', alto: 30 },
  { nombre: 'Oracle OPERA', logo: '/gloma/integraciones/oracle.svg', alto: 18 },
  { nombre: 'Paraty Tech', logo: '/gloma/integraciones/paratytech.svg', alto: 22 },
  { nombre: 'Zeus PMS' },
];


/**
 * El 70 % es cifra autorizada por el CEO (2026-10-21) y siempre va con su base
 * (`NOTA_AHORRO`, decisión D1 del 2026-10-22). Las dos cifras de plata van juntas.
 */
const STATS = [
  {
    icon: 'mensajes' as IconoNombre,
    value: 150000,
    prefix: '+',
    suffix: '',
    label: 'mensajes de viajeros gestionados',
  },
  {
    icon: 'horas' as IconoNombre,
    value: 10000,
    prefix: '+',
    suffix: '',
    label: 'horas de asesores IA en operación',
  },
  {
    icon: 'medicion' as IconoNombre,
    value: 70,
    prefix: 'Hasta ',
    suffix: ' %',
    label: 'menos en el costo de atención*',
  },
  {
    icon: 'retorno' as IconoNombre,
    value: 4,
    prefix: '',
    suffix: ' meses',
    label: 'para recuperar la inversión, en promedio',
  },
];

const NOTA_AHORRO = '* Frente a atender el mismo volumen de chats solo con asesores.';

/**
 * Todo lo que incluye, prueba gratis contra plan mensual (CEO, 2026-10-28; texto
 * del community-manager del 2026-10-25). `true` = incluido, `false` = no, y un
 * texto = incluido con ese límite. El PDF repite esta misma tabla.
 */
type Incluido = boolean | string;
const INCLUYE: { grupo: string; filas: { texto: string; prueba: Incluido; plan: Incluido }[] }[] = [
  {
    grupo: 'Contesta cuando tu equipo no puede',
    filas: [
      { texto: 'Contesta tu WhatsApp a cualquier hora, también de noche', prueba: 'En 1 número', plan: true },
      { texto: 'Da el precio con tus tarifas y tus planes, sin inventar precios ni cupos', prueba: 'Hasta 5 productos o servicios', plan: true },
    ],
  },
  {
    grupo: 'Lleva al cliente hasta la reserva',
    filas: [
      { texto: 'Recupera a los clientes que dejaron de contestar', prueba: true, plan: true },
      { texto: 'Tu asesor recibe al cliente listo para reservar, con todo el historial', prueba: true, plan: true },
      { texto: 'El cliente recibe tus formas de pago y la reserva queda en tu Google Sheets', prueba: false, plan: true },
      { texto: 'Agenda la llamada con tu asesor cuando el cliente la pide', prueba: false, plan: true },
      { texto: 'Les llevas tus promociones por WhatsApp a tus contactos', prueba: false, plan: 'Por mensaje enviado' },
    ],
  },
  {
    // El CEO confirmó (2026-10-28) que los tiempos de respuesta se miden y se
    // entregan en el reporte de la prueba y del plan.
    grupo: 'Ves dónde se te va la plata',
    filas: [
      { texto: 'Cuánta venta se te queda en el aire, en pesos, cada semana', prueba: true, plan: true },
      { texto: 'Tiempos de respuesta del agente y de tus asesores', prueba: true, plan: true },
      { texto: 'A qué horas te escriben y cuántos mensajes llegan fuera de horario', prueba: true, plan: true },
      { texto: 'Cuáles interesados están listos para comprar', prueba: true, plan: true },
      { texto: 'Tu equipo contesta desde una sola bandeja, con el historial de cada cliente', prueba: true, plan: true },
    ],
  },
  {
    grupo: 'Lo dejamos funcionando contigo',
    filas: [
      { texto: 'Instalación hecha por nuestro equipo, sin costo', prueba: true, plan: true },
      { texto: 'Ajustes durante los primeros 10 días', prueba: false, plan: true },
      { texto: 'Soporte 24/7 y mantenimiento incluidos', prueba: true, plan: true },
    ],
  },
];

/** Lo que te llevas de la prueba gratis (plan P1, «La prueba gratis de 14 días»). */
const PRUEBA_INCLUYE = [
  'Tu agente contestando en uno de tus números comerciales, con tu tarifario',
  'Hasta 5 productos o servicios',
  'Cuánta plata se te queda en el aire cada semana, en pesos',
  'Cuánto tardan en contestar tu equipo y el agente',
  'A qué horas te escriben y cuántos mensajes llegan fuera de horario',
  'Cuáles interesados están listos para comprar',
];

/**
 * La propuesta comercial que eligió el CEO (opción A, «Ejecutiva», 2026-10-28),
 * publicada con `marketing/propuesta_comercial/exportar_pdf.sh opcion_a.html --publicar`.
 */
const PROPUESTA_PDF = '/gloma/propuesta-comercial-gloma.pdf';
const PROPUESTA_PUBLICADA = true;

/**
 * Precios públicos: plan P1 «Permanencia 6» de
 * `ventas/costos/PROPUESTAS_COMERCIALES.html`, con la hora a $50.000, elegido por
 * el CEO el 2026-10-28, con la salida anticipada a COP 150.000 por mes que falte.
 * Reemplaza a la instalación de 2.400.000 y los paquetes de 600/2.000/6.000.
 * Todo con IVA y la tarifa de Meta incluidos. Los USD salen de ~3.200 COP por
 * dólar [CONFIRMAR CEO]. El contexto de Lía (`backend/app/bot_contexts/gloma.md`)
 * y la propuesta PDF repiten estas cifras: si cambian aquí, cambian allá.
 */
type Moneda = 'COP' | 'USD';

const PRECIOS = {
  diasPrueba: 14,
  instalacion: { COP: 0, USD: 0 },
  mensualidad: { COP: 1_071_000, USD: 329 },
  /** Desde el mes 7. No se dice en la página que baja porque «la instalación ya quedó paga». */
  mensualidadDesdeMes7: { COP: 868_700, USD: 269 },
  conversacionesIncluidas: 1_000,
  conversacionAdicional: { COP: 1_190, USD: 0.37 },
  permanenciaMeses: 6,
  salidaPorMesQueFalta: { COP: 150_000, USD: 47 },
  mensajeCampana: { COP: 90, USD: 0.03 },
};

/**
 * Plan de referidos (P5 de las propuestas comerciales, CEO 2026-10-28): 20 % por
 * cada referido que entra a la prueba gratis y 50 % más si compra. Cada descuento
 * vale sobre una mensualidad, se suman, no hay tope por mes y lo que pase de
 * 100 % se corre a la siguiente.
 */
const REFERIDOS = { porPrueba: 0.2, porCompra: 0.5 };
const EJEMPLO_REFERIDOS = { prueba: 5, compran: 3 };

/** Ejemplos de los gráficos. Son ilustrativos y así se rotulan en la página. */
const EJEMPLO_CAMPANA = { enviados: 1_000, responden: 120 };
/** Salida anticipada de ejemplo: al terminar el mes 4 faltan 2 meses. */
const EJEMPLO_SALIDA_MES = 4;

/** Footer: el único enlace a WhatsApp de la página (ver `lib/contactoGloma.ts`). */
const WHATSAPP_URL = enlaceWhatsappFooter();

const INSTAGRAM_URL = 'https://www.instagram.com/gloma_app/';

/** Imagen y URL canónica para la vista previa al compartir el enlace. */
const SITE_URL = 'https://glomacx.com';
const OG_IMAGE = `${SITE_URL}/gloma/og_gloma.png`;
const SITE_TITLE = 'Gloma | Agente de IA en WhatsApp para agencias de viajes y hoteles';
const SITE_DESCRIPTION =
  'Un agente de IA contesta el WhatsApp de tu agencia de viajes o tu hotel con tus tarifas y le pasa a tu equipo al cliente listo para reservar.';

/** La plataforma vive en su propio subdominio (#303). */
const APP_URL = 'https://app.glomacx.com';

/**
 * Scroll suave hacia la sección de contacto con un easing más agradable que
 * el `scroll-behavior: smooth` nativo, que en Chrome se siente plano.
 * Animación 1s con cubic ease-in-out + un pequeño offset para que el título
 * no quede pegado al borde superior.
 */
/**
 * Llamados a la acción, iguales en toda la página (#625): donde se ofrece
 * agendar, el principal es «Agendar una llamada» (`BotonAgendar`) y el
 * secundario «Hablar con un asesor» (#634, `BotonAsesor`). Desde 2026-10-28
 * los dos abren el chat de la página, donde el agente agenda la reunión;
 * cuando el WhatsApp del agente esté activo, los dos llevan a su wa.me
 * (`WHATSAPP_DEL_AGENTE_ACTIVO` en `lib/contactoGloma.ts`). El calendario de
 * Cal.com ya no se usa en la landing. Desde 2026-10-21 ningún botón dice
 * «Lía»: el visitante no sabe quién es.
 */

function smoothScrollTo(e: React.MouseEvent<HTMLAnchorElement>, id: string) {
  e.preventDefault();
  if (typeof window === 'undefined') return;
  const el = document.getElementById(id);
  if (!el) return;
  const startY = window.scrollY;
  const targetY = el.getBoundingClientRect().top + startY - 40;
  const distance = targetY - startY;
  const duration = 1000;
  const t0 = performance.now();
  const easeInOutCubic = (t: number) =>
    t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const tick = (now: number) => {
    const p = Math.min(1, (now - t0) / duration);
    window.scrollTo(0, startY + distance * easeInOutCubic(p));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// --- Hooks -----------------------------------------------------------------

/** Dispara `inView=true` cuando el elemento entra al viewport. Una sola vez. */
function useInView<T extends Element>(rootMargin = '0px 0px -10% 0px') {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            obs.disconnect();
          }
        }
      },
      { threshold: 0.15, rootMargin }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [rootMargin]);
  return { ref, inView };
}

// --- Componentes -----------------------------------------------------------

function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: inView ? 1 : 0,
        transform: inView ? 'translateY(0)' : 'translateY(24px)',
        transition: `opacity 700ms ease ${delay}ms, transform 700ms cubic-bezier(.22,.61,.36,1) ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}

function formatNumber(n: number): string {
  return new Intl.NumberFormat('es-CO').format(Math.round(n));
}

function AnimatedNumber({
  target,
  prefix = '',
  suffix = '',
  durationMs = 1800,
  start,
}: {
  target: number;
  prefix?: string;
  suffix?: string;
  durationMs?: number;
  start: boolean;
}) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!start) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / durationMs);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(target * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [start, target, durationMs]);
  return (
    <span>
      {prefix}
      {formatNumber(value)}
      {suffix}
    </span>
  );
}

/**
 * Header con parallax sutil: la ventanilla del fondo sigue un poco el cursor.
 */
function InteractiveHeader() {
  const { ref: heroRef, inView } = useInView<HTMLDivElement>('0px');
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const headerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    let raf = 0;
    const handle = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      // Centro del header como (0,0); valores entre -0.5 y 0.5
      const nx = (e.clientX - rect.left) / rect.width - 0.5;
      const ny = (e.clientY - rect.top) / rect.height - 0.5;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setOffset({ x: nx, y: ny }));
    };
    el.addEventListener('mousemove', handle);
    return () => {
      el.removeEventListener('mousemove', handle);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <header
      ref={headerRef}
      className="relative w-full overflow-hidden"
      style={{ minHeight: '92vh' }}
    >
      {/* Fondo (opción 05 "Ventanilla", elegida por el CEO el 2026-09-28).
          Antes era `banner.png` —una imagen blanca pura— bajo un velo oscuro,
          y de ahí salía el gris apagado. */}
      <div
        className="absolute inset-0 z-0"
        style={{ background: 'linear-gradient(120deg, #101817 40%, #00362E 100%)' }}
      />

      {/* La ventanilla del logo, gigante y en contorno ("Window Seat" del
          brand book). Se mueve apenas con el cursor. */}
      <svg
        className="absolute inset-0 z-0 pointer-events-none w-full h-full"
        aria-hidden="true"
        viewBox="0 0 100 60"
        preserveAspectRatio="xMaxYMid slice"
        style={{
          transform: `translate3d(${offset.x * -18}px, ${offset.y * -12}px, 0)`,
          transition: 'transform 500ms cubic-bezier(.22,.61,.36,1)',
        }}
      >
        <rect x="66" y="-4" width="40" height="68" rx="20" fill="none" stroke={BRAND.mint} strokeOpacity="0.28" strokeWidth="0.45" />
        <rect x="70" y="2" width="32" height="56" rx="16" fill="none" stroke={BRAND.mint} strokeOpacity="0.16" strokeWidth="0.38" />
      </svg>

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between max-w-6xl mx-auto px-6 md:px-10 pt-6">
        <div className="flex items-center" aria-label="Gloma">
          <Image
            src="/gloma/logo_blancotrans.png"
            alt="Gloma"
            width={320}
            height={192}
            priority
            className="object-contain h-28 md:h-40 w-auto"
          />
        </div>
        <div className="hidden md:flex items-center gap-3">
          <a
            href="#precios"
            onClick={(e) => smoothScrollTo(e, 'precios')}
            className="px-4 py-2 text-sm font-medium text-white/85 hover:text-white transition-colors"
          >
            Precios
          </a>
          {/* #625: «Agendar una llamada» abre el chat de la página, donde el
              agente agenda (2026-10-28). El asesor está en el hero, justo debajo. */}
          <BotonAgendar
            className="px-5 py-2 rounded-full text-sm font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            {TEXTOS_AGENDAR.agendar}
          </BotonAgendar>
          {/* #303: acceso de clientes actuales. La plataforma vive en otro
              subdominio — bajo el apex, `/login` cae en el 404 brandeado del
              middleware — así que el enlace es absoluto. */}
          <a
            href={`${APP_URL}/login`}
            className="px-5 py-2 rounded-full text-sm font-medium border border-white text-white transition-colors hover:bg-white/10"
          >
            Entrar a la app
          </a>
        </div>
        {/* En móvil el CTA de demo va en la barra fija de abajo; aquí solo
            queda el acceso de clientes. */}
        <a
          href={`${APP_URL}/login`}
          className="md:hidden px-4 py-2 rounded-full text-xs font-medium border border-white/70 text-white"
        >
          Entrar a la app
        </a>
      </nav>

      {/* Contenido principal (título + subtítulo + CTAs) */}
      <div
        ref={heroRef}
        className="relative z-10 max-w-6xl mx-auto px-6 md:px-10 py-24 md:py-36"
      >
        <h1
          className="text-white text-4xl md:text-6xl leading-tight max-w-3xl"
          style={{
            fontFamily: 'Syne, system-ui, sans-serif',
            fontWeight: 800,
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease, transform 900ms cubic-bezier(.22,.61,.36,1)',
          }}
        >
          {/* Opción 01 de la segunda ronda de titulares, elegida por el CEO (2026-09-27).
              El 2026-10-28 el CEO decidió dejarlo así frente a los candidatos de Belfort. */}
          Un asesor más en tu equipo.{' '}
          <span className="block" style={{ color: BRAND.mint }}>Uno que no duerme.</span>
        </h1>
        <p
          className="text-white/90 mt-6 text-base md:text-xl max-w-xl font-light"
          style={{
            fontFamily: 'Inter, system-ui, sans-serif',
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 150ms, transform 900ms cubic-bezier(.22,.61,.36,1) 150ms',
          }}
        >
          Un agente de IA contesta tu WhatsApp con tus tarifas y le pasa a tu equipo, o a tu
          recepción, al cliente listo para reservar. Para agencias de viajes y hoteles.
        </p>
        <div
          className="mt-10 flex flex-col sm:flex-row gap-3"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 300ms, transform 900ms cubic-bezier(.22,.61,.36,1) 300ms',
          }}
        >
          {/* #625: las dos formas de contacto. Principal: «Agendar una
              llamada» (BotonAgendar); secundaria: «Hablar con un asesor»
              (BotonAsesor). Las dos abren el chat (2026-10-28). */}
          <BotonAgendar
            className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center transition-opacity hover:opacity-90"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            {TEXTOS_AGENDAR.agendar}
          </BotonAgendar>
          <BotonAsesor className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center border-2 border-white/80 text-white hover:bg-white/10 transition-colors">
            {TEXTOS_AGENDAR.whatsapp}
          </BotonAsesor>
        </div>
      </div>
    </header>
  );
}

type FormStatus = 'idle' | 'sending' | 'ok' | 'error';

/** Datos del form "Quiero que me contacten" (#299). */
type ContactFormValues = {
  nombre: string;
  email: string;
  telefono: string;
  agencia: string;
  chats_mes: string;
  acepta_privacidad: boolean;
};

const FORM_VACIO: ContactFormValues = {
  nombre: '',
  email: '',
  telefono: '',
  agencia: '',
  chats_mes: '',
  acepta_privacidad: false,
};

function ContactForm({
  form,
  setForm,
  status,
  message,
  onSubmit,
}: {
  form: ContactFormValues;
  setForm: (f: ContactFormValues) => void;
  status: FormStatus;
  message: string;
  onSubmit: (e: React.FormEvent) => void;
}) {
  const isSending = status === 'sending';
  const isDone = status === 'ok';
  const isError = status === 'error';

  // Microinteracción: el recuadro hace un pulso de aro + leve scale al presionar.
  // Cuando llega el OK: el contenido hace fade-out + collapse, y aparece un
  // estado "thanks" con un check brandeado dibujándose.
  const ringStyle: React.CSSProperties = isSending
    ? {
        boxShadow: `0 0 0 0 ${BRAND.mint}`,
        animation: 'glomaRing 1.4s ease-out infinite',
      }
    : isError
    ? { boxShadow: `0 0 0 3px ${BRAND.mint}` }
    : {};

  return (
    <>
      <style jsx global>{`
        @keyframes glomaRing {
          0%   { box-shadow: 0 0 0 0 rgba(77,182,172,0.95); }
          70%  { box-shadow: 0 0 0 14px rgba(77,182,172,0); }
          100% { box-shadow: 0 0 0 0 rgba(77,182,172,0); }
        }
        @keyframes glomaCheckDraw {
          to { stroke-dashoffset: 0; }
        }
        @keyframes glomaThanksFloat {
          0%   { opacity: 0; transform: translateY(8px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        .gloma-input::placeholder {
          color: rgba(230,239,238,0.35);
        }
        .gloma-input:focus {
          border-color: ${BRAND.mint} !important;
          box-shadow: 0 0 0 3px rgba(77,182,172,0.18);
        }
      `}</style>

      <div
        className="relative rounded-3xl shadow-md overflow-hidden transition-transform duration-500"
        style={{
          backgroundColor: BRAND.cardBg,
          border: `1px solid ${BRAND.cardBorder}`,
          backdropFilter: 'blur(8px)',
          ...ringStyle,
          transform: isSending ? 'scale(0.985)' : 'scale(1)',
        }}
      >
        {/* Estado normal / sending / error: el form */}
        <form
          onSubmit={onSubmit}
          aria-hidden={isDone}
          className="p-6 md:p-8 transition-all duration-500"
          style={{
            opacity: isDone ? 0 : 1,
            transform: isDone ? 'translateY(-8px)' : 'translateY(0)',
            pointerEvents: isDone ? 'none' : 'auto',
          }}
        >
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.textMuted }}>
            Nombre
          </label>
          <input
            type="text"
            required
            maxLength={120}
            value={form.nombre}
            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
            placeholder="¿Cómo te llamas?"
            disabled={isSending}
            className="gloma-input w-full px-4 py-3 border rounded-xl text-sm mb-5 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              borderColor: BRAND.cardBorder,
              color: BRAND.text,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          />
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.textMuted }}>
            Correo electrónico
          </label>
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            placeholder="tu@agenciadeviajes.com"
            disabled={isSending}
            className="gloma-input w-full px-4 py-3 border rounded-xl text-sm mb-5 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              borderColor: BRAND.cardBorder,
              color: BRAND.text,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          />
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.textMuted }}>
            Teléfono
          </label>
          <input
            type="tel"
            required
            value={form.telefono}
            onChange={(e) => setForm({ ...form, telefono: e.target.value })}
            placeholder="+57 300 000 0000"
            disabled={isSending}
            className="gloma-input w-full px-4 py-3 border rounded-xl text-sm mb-5 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              borderColor: BRAND.cardBorder,
              color: BRAND.text,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          />
          {/* Calificación: con la agencia y el volumen de chats se llega a la
              llamada sabiendo cuánto le cabe en el plan. */}
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.textMuted }}>
            Agencia u hotel
          </label>
          <input
            type="text"
            required
            maxLength={120}
            value={form.agencia}
            onChange={(e) => setForm({ ...form, agencia: e.target.value })}
            placeholder="Nombre de tu agencia u hotel"
            disabled={isSending}
            className="gloma-input w-full px-4 py-3 border rounded-xl text-sm mb-5 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              borderColor: BRAND.cardBorder,
              color: BRAND.text,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          />
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.textMuted }}>
            ¿Cuántos chats reciben al mes?
          </label>
          <select
            required
            value={form.chats_mes}
            onChange={(e) => setForm({ ...form, chats_mes: e.target.value })}
            disabled={isSending}
            className="gloma-input w-full px-4 py-3 border rounded-xl text-sm mb-6 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              backgroundColor: BRAND.bgAlt,
              borderColor: BRAND.cardBorder,
              color: form.chats_mes ? BRAND.text : 'rgba(230,239,238,0.35)',
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          >
            <option value="" disabled>
              Elige un rango
            </option>
            {CHATS_MES_OPCIONES.map((o) => (
              <option key={o.value} value={o.value} style={{ color: BRAND.text }}>
                {o.label}
              </option>
            ))}
          </select>
          {/* Autorización de tratamiento de datos (Ley 1581): obligatoria. El
              backend la vuelve a exigir y guarda cuándo se dio. */}
          <label className="flex items-start gap-3 text-xs leading-relaxed mb-6 cursor-pointer" style={{ color: BRAND.textMuted }}>
            <input
              type="checkbox"
              required
              checked={form.acepta_privacidad}
              onChange={(e) => setForm({ ...form, acepta_privacidad: e.target.checked })}
              disabled={isSending}
              className="mt-0.5 w-4 h-4 shrink-0"
              style={{ accentColor: BRAND.mint }}
            />
            <span>
              Autorizo el tratamiento de mis datos personales, conforme a la Ley 1581 de 2012,
              para ser contactado y recibir información comercial, promociones y novedades. Ver
              la{' '}
              <a
                href="/privacidad"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
                style={{ color: BRAND.mint }}
              >
                política de tratamiento de datos
              </a>
              .
            </span>
          </label>
          <button
            type="submit"
            disabled={isSending}
            className="w-full py-3 rounded-full font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-70 disabled:cursor-not-allowed"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            {isSending ? 'Enviando…' : 'Quiero que me contacten'}
          </button>
          {isError && message && (
            <p
              className="mt-4 text-sm text-center"
              style={{
                color: BRAND.textMuted,
                fontFamily: 'Inter, system-ui, sans-serif',
                animation: 'glomaThanksFloat 400ms ease-out both',
              }}
            >
              {message}
            </p>
          )}
        </form>

        {/* Estado thanks: aparece encima cuando isDone */}
        {isDone && (
          <div
            className="absolute inset-0 flex flex-col items-center justify-center px-6 md:px-8 text-center"
            style={{ backgroundColor: BRAND.bgAlt }}
            role="status"
            aria-live="polite"
          >
            <div
              className="w-20 h-20 rounded-full flex items-center justify-center mb-5"
              style={{
                backgroundColor: BRAND.mintSoft,
                animation: 'glomaThanksFloat 500ms ease-out both',
              }}
            >
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                <circle
                  cx="20"
                  cy="20"
                  r="18"
                  stroke={BRAND.cardBorderHover}
                  strokeWidth="2"
                  fill="none"
                />
                <path
                  d="M12 20.5 L18 26.5 L29 14.5"
                  stroke={BRAND.mint}
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                  style={{
                    strokeDasharray: 40,
                    strokeDashoffset: 40,
                    animation: 'glomaCheckDraw 600ms ease-out 200ms forwards',
                  }}
                />
              </svg>
            </div>
            <h3
              className="text-xl md:text-2xl mb-2"
              style={{
                fontFamily: 'Syne, system-ui, sans-serif',
                fontWeight: 700,
                color: BRAND.text,
                animation: 'glomaThanksFloat 500ms ease-out 250ms both',
              }}
            >
              Mensaje recibido
            </h3>
            <p
              className="text-sm md:text-base"
              style={{
                fontFamily: 'Inter, system-ui, sans-serif',
                color: BRAND.textMuted,
                animation: 'glomaThanksFloat 500ms ease-out 380ms both',
              }}
            >
              {message || 'Te contactaremos muy pronto.'}
            </p>
          </div>
        )}
      </div>
    </>
  );
}

/**
 * Maqueta del bloque de recordatorios: un chat de WhatsApp de una agencia
 * ficticia (la misma «Wayra Viajes» de la captura del primer bloque) con la
 * cadena de reenganches. Sin nombres ni teléfonos de personas reales.
 * Los tiempos (15 min, 5 h, 23 h) son los que usan los bots en producción.
 */
const RECORDATORIOS_MOCK = [
  { espera: '15 min sin respuesta', texto: '¿Pudiste ver el plan? Si quieres, te lo ajusto a tu presupuesto.' },
  { espera: '5 h sin respuesta', texto: 'Sigo pendiente por si te animas para noviembre.' },
  { espera: '23 h sin respuesta', texto: 'Te escribo por última vez. Aquí estoy cuando quieras retomarlo.' },
];

function MockRecordatorios({ titulo }: { titulo: string }) {
  const burbuja = 'rounded-lg px-2.5 py-1.5 md:py-1 shadow-sm max-w-[85%] leading-snug';
  return (
    <div
      role="img"
      aria-label={`${titulo}: chat de ejemplo con tres recordatorios y el paso al asesor`}
      className="absolute inset-0 flex items-center justify-center p-4 sm:p-5 md:p-6"
      style={{ background: 'linear-gradient(140deg, #003A31 0%, #101817 70%)' }}
    >
      <div
        aria-hidden="true"
        className="w-full max-w-[420px] h-full rounded-2xl overflow-hidden flex flex-col text-[11px] sm:text-xs md:text-[11px] lg:text-xs"
        style={{ backgroundColor: '#ECE5DD', fontFamily: 'Inter, system-ui, sans-serif', color: '#111B21' }}
      >
        {/* Cabecera del chat */}
        <div className="flex items-center gap-2.5 px-3 py-2 shrink-0" style={{ backgroundColor: '#F5F5F3' }}>
          <span
            className="w-7 h-7 md:w-8 md:h-8 rounded-full flex items-center justify-center text-white font-bold"
            style={{ backgroundColor: '#E2603F' }}
          >
            W
          </span>
          <div className="leading-tight">
            <p className="font-semibold">Wayra Viajes</p>
            <p className="text-[10px] md:text-[11px]" style={{ color: '#667781' }}>en línea</p>
          </div>
        </div>
        {/* Mensajes */}
        <div className="relative flex-1 flex flex-col justify-end gap-1.5 sm:gap-2 md:gap-1 lg:gap-1.5 px-3 py-2.5 md:py-2 overflow-hidden">
          {/* Desvanece lo que no cabe arriba, como un chat con historial. */}
          <div
            className="absolute inset-x-0 top-0 h-8 pointer-events-none z-10"
            style={{ background: 'linear-gradient(#ECE5DD, rgba(236,229,221,0))' }}
          />
          <div className={`${burbuja} self-start bg-white`}>
            Te dejo el plan a San Andrés para 4, con vuelos y hotel. ¿Qué fechas te sirven?
          </div>
          {RECORDATORIOS_MOCK.map((r) => (
            <div key={r.espera} className="flex flex-col gap-1 md:gap-0.5 lg:gap-1">
              <span
                className="self-center rounded-full px-2.5 py-0.5 text-[10px] font-medium"
                style={{ backgroundColor: 'rgba(255,255,255,0.75)', color: '#54656F' }}
              >
                {r.espera}
              </span>
              <div className={`${burbuja} self-start bg-white`}>{r.texto}</div>
            </div>
          ))}
          <div
            className="mt-1 self-center flex items-center gap-1.5 rounded-full px-3 py-1 font-semibold text-[10px] sm:text-[11px] md:text-xs"
            style={{ backgroundColor: BRAND.forest, color: '#FFFFFF' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
            </svg>
            Pasa a tu asesor para que lo llame
          </div>
        </div>
      </div>
    </div>
  );
}

function StatsSection() {
  const { ref, inView } = useInView<HTMLDivElement>('0px 0px -20% 0px');
  return (
    <section
      ref={ref}
      className="py-20 md:py-24 relative overflow-hidden"
      style={{
        background: `linear-gradient(180deg, ${BRAND.bgAlt} 0%, ${BRAND.bgBase} 100%)`,
        color: BRAND.text,
      }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage:
            'radial-gradient(circle at 50% 0%, rgba(77,182,172,0.10), transparent 60%)',
        }}
      />
      <div className="relative max-w-6xl mx-auto px-6 md:px-10">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-10 md:gap-6 text-center">
          {STATS.map((s, i) => (
            <div
              key={s.label}
              className="flex flex-col items-center"
              style={{
                opacity: inView ? 1 : 0,
                transform: inView ? 'translateY(0)' : 'translateY(20px)',
                transition: `opacity 700ms ease ${i * 150}ms, transform 700ms cubic-bezier(.22,.61,.36,1) ${i * 150}ms`,
              }}
            >
              <div
                className="w-20 h-20 rounded-full flex items-center justify-center mb-4 overflow-hidden"
                style={{
                  backgroundColor: BRAND.mintSoft,
                  border: `1px solid ${BRAND.cardBorderHover}`,
                }}
              >
                <Icono nombre={s.icon} size={34} />
              </div>
              <div
                className="text-4xl sm:text-3xl md:text-4xl xl:text-[1.9rem] mb-2 tabular-nums whitespace-nowrap"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 800,
                  color: BRAND.mint,
                }}
              >
                <AnimatedNumber
                  target={s.value}
                  prefix={s.prefix}
                  suffix={s.suffix}
                  start={inView}
                  durationMs={1800 + i * 200}
                />
              </div>
              <div
                className="text-sm md:text-base opacity-80"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>
        <p
          className="mt-10 text-xs text-center"
          style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.textDim }}
        >
          {NOTA_AHORRO}
        </p>
      </div>
    </section>
  );
}

// --- Cómo empezar ---------------------------------------------------------

/** Texto secundario sobre Soft Mint: Technical Black al 72 % (contraste AA). */
const TEXTO_CLARO_MUTED = 'rgba(16,24,23,0.72)';

/**
 * «Cómo empezar», con el reparto tú / nosotros (ajustes del CEO, 2026-10-26). El
 * 2026-10-28 el CEO pidió conservar el título «¿Cómo empiezas a usar Gloma?» y
 * contar que todo arranca con la prueba gratis. Ruta de 4 pasos: horizontal en
 * escritorio (una línea une los nodos) y vertical en móvil.
 */
function ComoEmpezarSection() {
  return (
    <section
      id="como-empezar"
      aria-labelledby="como-empezar-titulo"
      className="py-20 md:py-28"
      style={{ backgroundColor: BRAND.softMint, fontFamily: 'Inter, system-ui, sans-serif' }}
    >
      <div className="max-w-6xl mx-auto px-6 md:px-10">
        <Reveal className="text-center max-w-2xl mx-auto mb-14 md:mb-20">
          <p
            className="text-sm font-semibold tracking-wide uppercase mb-4"
            style={{ color: BRAND.forest }}
          >
            Cómo empezar
          </p>
          <h2
            id="como-empezar-titulo"
            className="text-3xl md:text-5xl leading-tight mb-5"
            style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.bgBase }}
          >
            ¿Cómo empiezas a usar Gloma?
          </h2>
          <p className="text-base md:text-lg" style={{ color: TEXTO_CLARO_MUTED }}>
            Empezamos con una prueba gratis de 14 días. Ahí encontramos dónde se te está yendo
            la plata y los puntos débiles de tu atención. No necesitas saber de tecnología: del
            resto nos encargamos nosotros.
          </p>
        </Reveal>

        <ol className="relative grid grid-cols-1 md:grid-cols-4 gap-10 md:gap-6">
          {/* Línea de la ruta: vertical en móvil, horizontal en escritorio */}
          <div
            aria-hidden="true"
            className="absolute left-6 top-6 bottom-6 w-px md:hidden"
            style={{ background: `linear-gradient(${BRAND.forest}, rgba(0,77,64,0.2))` }}
          />
          <div
            aria-hidden="true"
            className="hidden md:block absolute top-6 left-[12.5%] right-[12.5%] h-px"
            style={{ background: `linear-gradient(90deg, ${BRAND.forest}, rgba(0,77,64,0.2))` }}
          />
          {PASOS_INICIO.map((paso, i) => (
            <li key={paso.titulo} className="relative">
              <Reveal delay={i * 120} className="flex md:flex-col md:items-center gap-5 md:gap-0">
                <span
                  className="relative z-10 w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-base tabular-nums md:mb-6"
                  style={{
                    fontFamily: 'Inter, system-ui, sans-serif',
                    fontWeight: 700,
                    color: '#FFFFFF',
                    backgroundColor: BRAND.forest,
                    boxShadow: `0 0 0 6px ${BRAND.softMint}`,
                  }}
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <div className="w-full">
                  <h3
                    className="text-lg md:text-xl mb-3 leading-snug md:text-center"
                    style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.bgBase }}
                  >
                    {paso.titulo}
                  </h3>
                  <div
                    className="rounded-2xl p-4 text-sm leading-relaxed space-y-3"
                    style={{ backgroundColor: '#FFFFFF', border: '1px solid rgba(0,77,64,0.15)' }}
                  >
                    <p style={{ color: BRAND.bgBase }}>
                      <span className="block text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: BRAND.forest }}>
                        Tú
                      </span>
                      {paso.tu}
                    </p>
                    <p className="pt-3" style={{ color: TEXTO_CLARO_MUTED, borderTop: '1px solid rgba(0,77,64,0.12)' }}>
                      <span className="block text-xs font-semibold uppercase tracking-wide mb-1" style={{ color: BRAND.forest }}>
                        Nosotros
                      </span>
                      {paso.nosotros}
                    </p>
                  </div>
                  {paso.etiqueta && (
                    <div className="md:text-center">
                      <span
                        className="inline-block mt-4 px-3 py-1 rounded-full text-xs font-semibold"
                        style={{ backgroundColor: 'rgba(0,77,64,0.08)', color: BRAND.forest, border: '1px solid rgba(0,77,64,0.2)' }}
                      >
                        {paso.etiqueta}
                      </span>
                    </div>
                  )}
                </div>
              </Reveal>
            </li>
          ))}
        </ol>

        <Reveal className="text-center mt-12">
          <BotonAgendar
            className="px-6 py-3 rounded-full text-sm font-semibold transition-opacity hover:opacity-90"
            style={{ backgroundColor: BRAND.forest, color: '#FFFFFF' }}
          >
            {TEXTOS_AGENDAR.agendar}
          </BotonAgendar>
        </Reveal>
      </div>
    </section>
  );
}

// --- Funciona con lo que ya usas -------------------------------------------

function YaUsasSection() {
  return (
    <section
      id="ya-usas"
      aria-labelledby="ya-usas-titulo"
      className="py-20 md:py-28"
      style={{ backgroundColor: BRAND.bgAlt, fontFamily: 'Inter, system-ui, sans-serif' }}
    >
      <div className="max-w-6xl mx-auto px-6 md:px-10">
        <Reveal className="text-center max-w-2xl mx-auto mb-12 md:mb-16">
          <h2
            id="ya-usas-titulo"
            className="text-3xl md:text-5xl leading-tight mb-5"
            style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
          >
            Funciona con lo que ya usas
          </h2>
          <p className="text-base md:text-lg" style={{ color: BRAND.textMuted }}>
            Tu agente trabaja con tus tarifas desde el primer día, y lo conectamos con el sistema
            donde ya llevas tus reservas.
          </p>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-6">
          {YA_USAS.map((c, i) => (
            <Reveal key={c.titulo} delay={i * 80}>
              <div
                className="gloma-card p-6 md:p-8 rounded-3xl h-full transition-all"
                style={{ backgroundColor: BRAND.cardBg, border: `1px solid ${BRAND.cardBorder}` }}
              >
                <p
                  className="text-xl mb-3"
                  style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.mint }}
                >
                  {c.titulo}
                </p>
                <p className="text-base leading-relaxed" style={{ color: BRAND.textMuted }}>
                  {c.texto}
                </p>
              </div>
            </Reveal>
          ))}
        </div>

        {/* Sistemas que usan los hoteles (CEO, 2026-10-28), en blanco y negro. */}
        <Reveal className="mt-14 md:mt-16">
          <p className="text-sm font-semibold tracking-wide uppercase text-center mb-8" style={{ color: BRAND.mint }}>
            Compatibles con el sistema que ya usas, y con muchos más
          </p>
          <ul
            className="flex flex-wrap justify-center items-center gap-x-10 gap-y-7 md:gap-x-14"
            aria-label="Sistemas de reservas con los que somos compatibles"
          >
            {SISTEMAS.map((sis) => (
              <li key={sis.nombre} className="flex items-center h-11">
                {sis.logo ? (
                  // Logos ajenos en blanco y gris para que no le quiten protagonismo a la página.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={sis.logo}
                    alt={sis.nombre}
                    title={sis.nombre}
                    className="w-auto object-contain"
                    style={{
                      height: sis.alto ?? 26,
                      maxWidth: 170,
                      filter: 'grayscale(1) brightness(0) invert(1)',
                      opacity: 0.55,
                    }}
                    loading="lazy"
                  />
                ) : (
                  <span
                    className="text-lg md:text-xl whitespace-nowrap"
                    style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: 'rgba(230,239,238,0.55)' }}
                  >
                    {sis.nombre}
                  </span>
                )}
              </li>
            ))}
            <li className="flex items-center h-11">
              <span className="text-sm whitespace-nowrap" style={{ color: 'rgba(230,239,238,0.55)' }}>
                y muchos más
              </span>
            </li>
          </ul>
          <p className="text-xs text-center mt-6 max-w-2xl mx-auto" style={{ color: BRAND.textDim }}>
            La conexión con tu channel manager o tu PMS se hace a la medida para tu negocio. Las
            marcas son de sus dueños.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

// --- Preguntas frecuentes ---------------------------------------------------

function FaqSection() {
  return (
    <section
      id="preguntas"
      aria-labelledby="preguntas-titulo"
      className="py-20 md:py-28"
      style={{ backgroundColor: BRAND.bgBase, fontFamily: 'Inter, system-ui, sans-serif' }}
    >
      <style jsx global>{`
        .gloma-faq summary::-webkit-details-marker {
          display: none;
        }
        .gloma-faq[open] .gloma-faq-signo {
          transform: rotate(45deg);
        }
      `}</style>
      <div className="max-w-3xl mx-auto px-6 md:px-10">
        <Reveal className="text-center mb-10 md:mb-14">
          <h2
            id="preguntas-titulo"
            className="text-3xl md:text-5xl leading-tight"
            style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
          >
            Preguntas frecuentes
          </h2>
        </Reveal>
        <div className="space-y-3">
          {FAQ.map((f) => (
            <details
              key={f.q}
              className="gloma-faq rounded-2xl px-5 md:px-6"
              style={{ backgroundColor: BRAND.cardBg, border: `1px solid ${BRAND.cardBorder}` }}
            >
              <summary className="flex items-center justify-between gap-4 py-5 cursor-pointer list-none">
                <span className="text-base md:text-lg font-medium" style={{ color: BRAND.text }}>
                  {f.q}
                </span>
                <span
                  aria-hidden="true"
                  className="gloma-faq-signo text-2xl leading-none transition-transform"
                  style={{ color: BRAND.mint }}
                >
                  +
                </span>
              </summary>
              <p className="pb-5 -mt-1 text-sm md:text-base leading-relaxed" style={{ color: BRAND.textMuted }}>
                {f.a}
              </p>
            </details>
          ))}
        </div>
        <Reveal className="text-center mt-10">
          <p className="text-base mb-4" style={{ color: BRAND.textMuted }}>
            ¿Tienes otra pregunta?
          </p>
          <BotonAsesor className="px-6 py-3 rounded-full text-sm font-semibold border-2 border-white/80 text-white hover:bg-white/10 transition-colors">
            {TEXTOS_AGENDAR.whatsapp}
          </BotonAsesor>
        </Reveal>
      </div>
    </section>
  );
}

// --- Precios ---------------------------------------------------------------

/**
 * `2.000.000` / `0,025`: separadores de Colombia en las dos monedas y sin el
 * signo `$` (decisión del CEO): la moneda va escrita al lado (COP / USD).
 */
function formatMonto(valor: number, decimales = 0): string {
  return new Intl.NumberFormat('es-CO', {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  }).format(valor);
}

/** Precio grande en Syne con la moneda en pequeño al lado. */
function Precio({
  valor,
  moneda,
  decimales = 0,
  size = 'text-[2rem] sm:text-4xl md:text-5xl',
  apilado = false,
}: {
  valor: number;
  moneda: Moneda;
  decimales?: number;
  size?: string;
  /** Moneda siempre debajo: para que tarjetas vecinas queden parejas. */
  apilado?: boolean;
}) {
  return (
    <span
      className={`${apilado ? 'flex flex-col' : 'inline-flex flex-wrap items-baseline gap-x-2'} tabular-nums`}
    >
      <span
        className={size}
        style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800, color: BRAND.text }}
      >
        {formatMonto(valor, decimales)}
      </span>
      <span className="text-sm font-semibold" style={{ color: BRAND.mint }}>
        {moneda}
      </span>
    </span>
  );
}

/** Encabezado de cada uno de los tres cobros: número, nombre y cuándo se paga. */
function CobroHeader({ numero, titulo, cuando }: { numero: string; titulo: string; cuando: string }) {
  return (
    <div className="flex items-center gap-4 mb-6">
      <span
        className="w-12 h-12 shrink-0 rounded-full flex items-center justify-center text-base tabular-nums"
        style={{
          fontFamily: 'Inter, system-ui, sans-serif',
          fontWeight: 700,
          color: BRAND.bgBase,
          backgroundColor: BRAND.mint,
        }}
      >
        {numero}
      </span>
      <div>
        <h3
          className="text-xl md:text-2xl leading-tight"
          style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
        >
          {titulo}
        </h3>
        <p className="text-sm" style={{ color: BRAND.textMuted }}>
          {cuando}
        </p>
      </div>
    </div>
  );
}

/** Flecha entre nodos de los diagramas: hacia abajo en móvil, a la derecha en escritorio. */
function Flecha() {
  return (
    <div className="flex items-center justify-center py-1 md:py-0 md:px-1" aria-hidden="true">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" className="rotate-90 md:rotate-0">
        <path
          d="M4 12h15m-5-5 5 5-5 5"
          stroke={BRAND.mint}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

/** Marca de la tabla: ✓, — o el límite escrito. */
function CeldaIncluido({ valor, destacado = false }: { valor: Incluido; destacado?: boolean }) {
  if (valor === true) {
    return (
      <span style={{ color: destacado ? BRAND.golden : BRAND.mint }} aria-label="Incluido">
        ✓
      </span>
    );
  }
  if (valor === false) {
    return (
      <span style={{ color: BRAND.textDim }} aria-label="No incluido">
        —
      </span>
    );
  }
  return (
    <span className="text-xs leading-snug" style={{ color: BRAND.textMuted }}>
      {valor}
    </span>
  );
}

/**
 * Todo lo que incluye: prueba gratis contra plan mensual. En escritorio es una
 * tabla de 3 columnas; en móvil cada fila lleva sus dos marcas debajo.
 */
function TablaIncluye() {
  return (
    <div className="rounded-3xl p-6 md:p-10" style={{ backgroundColor: BRAND.cardBg, border: `1px solid ${BRAND.cardBorder}` }}>
      <h3
        className="text-2xl md:text-3xl leading-tight mb-2"
        style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
      >
        Todo lo que incluye
      </h3>
      <p className="text-sm md:text-base mb-6" style={{ color: BRAND.textMuted }}>
        En la prueba gratis ves cómo trabaja tu agente y dónde se te va la plata. Con el plan
        mensual tienes todo, sin pagar instalación.
      </p>

      {/* Encabezado de columnas (solo escritorio) */}
      <div
        className="hidden md:grid grid-cols-[1fr_9rem_9rem] gap-4 pb-3 text-sm font-semibold"
        style={{ borderBottom: `1px solid ${BRAND.cardBorder}` }}
      >
        <span />
        <span className="text-center" style={{ color: BRAND.text }}>
          Prueba gratis
          <span className="block text-xs font-normal" style={{ color: BRAND.textDim }}>
            {PRECIOS.diasPrueba} días
          </span>
        </span>
        <span className="text-center" style={{ color: BRAND.golden }}>
          Plan mensual
          <span className="block text-xs font-normal" style={{ color: BRAND.textDim }}>
            Instalación sin costo
          </span>
        </span>
      </div>

      {INCLUYE.map((g) => (
        <div key={g.grupo} className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: BRAND.mint }}>
            {g.grupo}
          </p>
          <ul>
            {g.filas.map((f) => (
              <li
                key={f.texto}
                className="py-3 md:grid md:grid-cols-[1fr_9rem_9rem] md:gap-4 md:items-center"
                style={{ borderBottom: '1px solid rgba(77,182,172,0.08)' }}
              >
                <span className="block text-sm md:text-base leading-snug" style={{ color: BRAND.text }}>
                  {f.texto}
                </span>
                <span className="hidden md:block text-center">
                  <CeldaIncluido valor={f.prueba} />
                </span>
                <span className="hidden md:block text-center">
                  <CeldaIncluido valor={f.plan} destacado />
                </span>
                {/* Móvil: las dos marcas debajo del texto */}
                <span className="md:hidden mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
                  <span style={{ color: BRAND.textDim }}>
                    Prueba: <CeldaIncluido valor={f.prueba} />
                  </span>
                  <span style={{ color: BRAND.textDim }}>
                    Plan: <CeldaIncluido valor={f.plan} destacado />
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Botón − / + de la calculadora de referidos. */
function Contador({
  etiqueta,
  valor,
  min,
  max,
  onCambio,
}: {
  etiqueta: string;
  valor: number;
  min: number;
  max: number;
  onCambio: (v: number) => void;
}) {
  const boton =
    'w-10 h-10 rounded-full text-lg font-bold flex items-center justify-center transition-opacity disabled:opacity-30';
  return (
    <div>
      <p className="text-sm mb-2" style={{ color: BRAND.textMuted }}>
        {etiqueta}
      </p>
      <div className="flex items-center gap-4">
        <button
          type="button"
          className={boton}
          style={{ border: `1px solid ${BRAND.cardBorderHover}`, color: BRAND.mint }}
          onClick={() => onCambio(Math.max(min, valor - 1))}
          disabled={valor <= min}
          aria-label={`Restar uno: ${etiqueta}`}
        >
          −
        </button>
        <span
          className="text-3xl w-10 text-center tabular-nums"
          style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800, color: BRAND.text }}
          aria-live="polite"
        >
          {valor}
        </span>
        <button
          type="button"
          className={boton}
          style={{ border: `1px solid ${BRAND.cardBorderHover}`, color: BRAND.mint }}
          onClick={() => onCambio(Math.min(max, valor + 1))}
          disabled={valor >= max}
          aria-label={`Sumar uno: ${etiqueta}`}
        >
          +
        </button>
      </div>
    </div>
  );
}

/**
 * Plan de referidos con su calculadora. Quien compra también hizo la prueba, así
 * que cada referido que compra suma los dos descuentos (20 % + 50 %).
 */
function BloqueReferidos({ moneda }: { moneda: Moneda }) {
  const [prueba, setPrueba] = useState(EJEMPLO_REFERIDOS.prueba);
  const [compran, setCompran] = useState(EJEMPLO_REFERIDOS.compran);
  const mensualidades = prueba * REFERIDOS.porPrueba + compran * REFERIDOS.porCompra;
  const ahorro = mensualidades * PRECIOS.mensualidad[moneda];
  const pct = (x: number) => `${Math.round(x * 100)} %`;

  return (
    <div className="rounded-3xl p-6 md:p-10" style={{ backgroundColor: BRAND.cardBg, border: `1px solid ${BRAND.cardBorder}` }}>
      <p className="text-sm font-semibold tracking-wide uppercase mb-3" style={{ color: BRAND.mint }}>
        Plan de referidos
      </p>
      <h3
        className="text-2xl md:text-3xl leading-tight mb-3"
        style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
      >
        Recomienda Gloma y paga menos
      </h3>
      <p className="text-base leading-relaxed max-w-3xl" style={{ color: BRAND.textMuted }}>
        Cada negocio que nos refieras te da un descuento en tu mensualidad. Los descuentos se
        suman, no tienen tope y lo que pase de una mensualidad completa se aplica en la siguiente.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
        {[
          { valor: pct(REFERIDOS.porPrueba), texto: 'de descuento por cada negocio que refieras y entre a la prueba gratis' },
          { valor: pct(REFERIDOS.porCompra), texto: 'más por cada negocio que refieras y compre el plan' },
        ].map((r) => (
          <div
            key={r.valor}
            className="rounded-2xl p-5"
            style={{ backgroundColor: BRAND.mintSoft, border: `1px solid ${BRAND.cardBorderHover}` }}
          >
            <p
              className="text-4xl tabular-nums"
              style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800, color: BRAND.mint }}
            >
              {r.valor}
            </p>
            <p className="text-sm mt-1" style={{ color: BRAND.text }}>
              {r.texto}
            </p>
          </div>
        ))}
      </div>

      {/* Calculadora */}
      <div className="mt-8 rounded-2xl p-5 md:p-6" style={{ border: `1px solid ${BRAND.cardBorder}` }}>
        <p className="text-xs font-semibold uppercase tracking-wide mb-5" style={{ color: BRAND.textDim }}>
          Haz la cuenta
        </p>
        <div className="grid grid-cols-1 md:grid-cols-[auto_auto_1fr] gap-6 md:gap-10 md:items-end">
          <Contador
            etiqueta="Negocios que refieres y entran a la prueba"
            valor={prueba}
            min={0}
            max={20}
            onCambio={(v) => {
              setPrueba(v);
              if (compran > v) setCompran(v);
            }}
          />
          <Contador
            etiqueta="De esos, cuántos compran"
            valor={compran}
            min={0}
            max={prueba}
            onCambio={setCompran}
          />
          <div className="md:text-right" aria-live="polite">
            <p className="text-sm" style={{ color: BRAND.textMuted }}>
              Te ahorras
            </p>
            <Precio valor={ahorro} moneda={moneda} size="text-3xl md:text-4xl" />
            <p className="text-sm mt-1" style={{ color: BRAND.mint }}>
              {formatMonto(mensualidades, Number.isInteger(mensualidades) ? 0 : 1)}{' '}
              {mensualidades === 1 ? 'mensualidad gratis' : 'mensualidades gratis'}
            </p>
          </div>
        </div>
        <p className="text-xs mt-5" style={{ color: BRAND.textDim }}>
          Ejemplo: refieres a {EJEMPLO_REFERIDOS.prueba} negocios, los {EJEMPLO_REFERIDOS.prueba} hacen
          la prueba y {EJEMPLO_REFERIDOS.compran} compran: {EJEMPLO_REFERIDOS.prueba} × 20 % +{' '}
          {EJEMPLO_REFERIDOS.compran} × 50 % = 250 %, dos mensualidades y media. Calculado sobre la
          mensualidad de los meses 1 a {PRECIOS.permanenciaMeses}.
        </p>
      </div>
    </div>
  );
}

/** Garantía, soporte y mantenimiento (COPY_LANDING.md, 1d). Cuadra con `PASOS_INICIO`. */
function BloqueGarantia() {
  return (
    <div
      className="rounded-3xl p-6 md:p-10"
      style={{ backgroundColor: BRAND.forest, border: `1px solid ${BRAND.cardBorderHover}` }}
    >
      <h3
        className="text-2xl md:text-3xl leading-tight mb-3"
        style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: '#FFFFFF' }}
      >
        Queda funcionando como tú quieres.
      </h3>
      <p className="text-base leading-relaxed max-w-3xl" style={{ color: 'rgba(255,255,255,0.85)' }}>
        Esa es nuestra garantía. Instalamos el agente, lo probamos contigo y durante los primeros
        10 días lo ajustamos con las conversaciones que van llegando. Después sigues con soporte
        24/7 y mantenimiento incluido: si algo no responde como esperas, nos escribes por WhatsApp
        y lo ajustamos.
      </p>
      <ul className="flex flex-wrap gap-2 mt-6">
        {['Garantía de funcionamiento', 'Soporte 24/7', 'Mantenimiento incluido'].map((t) => (
          <li
            key={t}
            className="px-3 py-1 rounded-full text-xs font-semibold"
            style={{ backgroundColor: 'rgba(16,24,23,0.35)', color: BRAND.mint, border: `1px solid ${BRAND.cardBorderHover}` }}
          >
            ✓ {t}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PreciosSection() {
  const [moneda, setMoneda] = useState<Moneda>('COP');
  const usd = moneda === 'USD';
  const dec = (v: number) => (usd && !Number.isInteger(v) ? 2 : 0);

  const { enviados, responden } = EJEMPLO_CAMPANA;
  const costoEnvio = enviados * PRECIOS.mensajeCampana[moneda];
  const mesesQueFaltan = PRECIOS.permanenciaMeses - EJEMPLO_SALIDA_MES;
  const salidaEjemplo = mesesQueFaltan * PRECIOS.salidaPorMesQueFalta[moneda];

  const card: React.CSSProperties = {
    backgroundColor: BRAND.cardBg,
    border: `1px solid ${BRAND.cardBorder}`,
  };
  const nodo: React.CSSProperties = {
    backgroundColor: 'rgba(255,255,255,0.03)',
    border: `1px solid ${BRAND.cardBorder}`,
  };

  return (
    <section
      id="precios"
      aria-labelledby="precios-titulo"
      className="py-20 md:py-28 relative overflow-hidden"
      style={{ backgroundColor: BRAND.bgAlt, fontFamily: 'Inter, system-ui, sans-serif' }}
    >
      <div className="relative max-w-6xl mx-auto px-6 md:px-10">
        <Reveal className="text-center max-w-3xl mx-auto mb-10 md:mb-14">
          <p
            className="text-sm font-semibold tracking-wide uppercase mb-4"
            style={{ color: BRAND.mint }}
          >
            Precios
          </p>
          <h2
            id="precios-titulo"
            className="text-3xl md:text-5xl leading-tight mb-5"
            style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
          >
            Tu inversión en Gloma
          </h2>
          <p className="text-base md:text-lg" style={{ color: BRAND.textMuted }}>
            Empiezas con {PRECIOS.diasPrueba} días gratis. Si te sirve, sigues con una mensualidad
            que lo incluye todo, y la instalación no te cuesta nada.
          </p>
          <p className="text-base md:text-lg mt-4" style={{ color: BRAND.text }}>
            <strong style={{ color: BRAND.mint }}>Hasta un 70 % menos en el costo de atención*</strong>, y tu
            inversión se recupera en 4 meses, en promedio.
          </p>
          <p className="text-xs mt-1" style={{ color: BRAND.textDim }}>
            {NOTA_AHORRO}
          </p>

          <ul className="flex flex-wrap justify-center gap-2 mt-6" aria-label="Lo que incluyen los precios">
            {[`${PRECIOS.diasPrueba} días gratis`, 'Instalación sin costo', 'IVA incluido', 'Tarifa de Meta incluida'].map((t) => (
              <li
                key={t}
                className="px-3 py-1 rounded-full text-xs font-semibold"
                style={{ backgroundColor: BRAND.mintSoft, color: BRAND.mint, border: `1px solid ${BRAND.cardBorder}` }}
              >
                ✓ {t}
              </li>
            ))}
          </ul>

          {/* Selector de moneda */}
          <div
            role="group"
            aria-label="Moneda de los precios"
            className="inline-flex mt-8 p-1 rounded-full"
            style={{ border: `1px solid ${BRAND.cardBorder}`, backgroundColor: BRAND.cardBg }}
          >
            {(['COP', 'USD'] as Moneda[]).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={moneda === m}
                onClick={() => setMoneda(m)}
                className="px-5 py-2 rounded-full text-sm font-semibold transition-colors"
                style={
                  moneda === m
                    ? { backgroundColor: BRAND.mint, color: BRAND.bgBase }
                    : { color: BRAND.textMuted }
                }
              >
                {m === 'COP' ? 'Pesos (COP)' : 'Dólares (USD)'}
              </button>
            ))}
          </div>
        </Reveal>

        <div className="space-y-8">
          {/* ===== 01 · Prueba gratis ===== */}
          <Reveal>
            <div className="rounded-3xl p-6 md:p-10" style={card}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-10 items-center">
                <div>
                  <CobroHeader
                    numero="01"
                    titulo={`Prueba gratis de ${PRECIOS.diasPrueba} días`}
                    cuando="Para empezar, sin pagar nada"
                  />
                  <p className="text-base leading-relaxed" style={{ color: BRAND.textMuted }}>
                    Ponemos tu agente a contestar en uno de tus números comerciales, con tu tarifario.
                    Al final te mostramos dónde se te está yendo la plata y los puntos débiles de tu
                    atención, con cifras.
                  </p>
                </div>
                <div className="md:text-right">
                  <Precio valor={0} moneda={moneda} />
                  <p className="text-sm mt-2" style={{ color: BRAND.textDim }}>
                    Durante {PRECIOS.diasPrueba} días
                  </p>
                </div>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3 mt-8">
                {PRUEBA_INCLUYE.map((t) => (
                  <li key={t} className="flex gap-3 text-sm md:text-base leading-snug" style={{ color: BRAND.text }}>
                    <span aria-hidden="true" style={{ color: BRAND.mint }}>
                      ✓
                    </span>
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>

          {/* ===== 02 · Plan mensual ===== */}
          <Reveal>
            <div
              className="rounded-3xl p-6 md:p-10"
              style={{
                ...card,
                border: `2px solid ${BRAND.golden}`,
                boxShadow: '0 0 60px -20px rgba(245,194,75,0.4)',
              }}
            >
              <CobroHeader
                numero="02"
                titulo="Plan mensual"
                cuando="Si después de la prueba quieres seguir"
              />

              {/* Instalación en cero: el dato que más pesa (CEO, 2026-10-28) */}
              <div
                className="rounded-2xl p-5 md:p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                style={{ backgroundColor: 'rgba(245,194,75,0.08)', border: `1px solid ${BRAND.golden}` }}
              >
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide" style={{ color: BRAND.golden }}>
                    ★ Instalación
                  </p>
                  <p className="text-sm mt-1" style={{ color: BRAND.text }}>
                    Configuramos tu agente, conectamos tu número y lo ajustamos contigo. No te cuesta nada.
                  </p>
                </div>
                <span className="inline-flex items-baseline gap-2 tabular-nums">
                  <span
                    className="text-4xl md:text-5xl"
                    style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800, color: BRAND.golden }}
                  >
                    {formatMonto(PRECIOS.instalacion[moneda])}
                  </span>
                  <span className="text-sm font-semibold" style={{ color: BRAND.golden }}>
                    {moneda}
                  </span>
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 md:gap-6 mt-6">
                <div className="rounded-2xl p-6" style={nodo}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: BRAND.textDim }}>
                    Meses 1 a {PRECIOS.permanenciaMeses}
                  </p>
                  <Precio valor={PRECIOS.mensualidad[moneda]} moneda={moneda} size="text-3xl md:text-4xl" apilado />
                  <p className="text-sm mt-2" style={{ color: BRAND.textMuted }}>
                    al mes
                  </p>
                </div>
                <div className="rounded-2xl p-6" style={{ ...nodo, borderColor: BRAND.cardBorderHover }}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: BRAND.textDim }}>
                    Desde el mes {PRECIOS.permanenciaMeses + 1}
                  </p>
                  <Precio valor={PRECIOS.mensualidadDesdeMes7[moneda]} moneda={moneda} size="text-3xl md:text-4xl" apilado />
                  <p className="text-sm mt-2" style={{ color: BRAND.mint }}>
                    al mes: tu mensualidad baja
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6 mt-6">
                <p className="text-sm leading-relaxed" style={{ color: BRAND.textMuted }}>
                  <strong style={{ color: BRAND.text }}>
                    Cada mes incluye {formatNumber(PRECIOS.conversacionesIncluidas)} conversaciones.
                  </strong>{' '}
                  Una conversación es un chat con un cliente dentro de una ventana de 24 horas. Si un
                  mes pasas de {formatNumber(PRECIOS.conversacionesIncluidas)}, cada conversación
                  adicional vale {formatMonto(PRECIOS.conversacionAdicional[moneda], dec(PRECIOS.conversacionAdicional[moneda]))}{' '}
                  {moneda}.
                </p>
                <p className="text-sm leading-relaxed" style={{ color: BRAND.textMuted }}>
                  <strong style={{ color: BRAND.text }}>
                    El plan es de mínimo {PRECIOS.permanenciaMeses} meses.
                  </strong>{' '}
                  Si decides salir antes, pagas {formatMonto(PRECIOS.salidaPorMesQueFalta[moneda])} {moneda} por
                  cada mes que falte. Por ejemplo, si sales al terminar el mes {EJEMPLO_SALIDA_MES}, faltan{' '}
                  {mesesQueFaltan}: pagas {formatMonto(salidaEjemplo)} {moneda}.
                </p>
              </div>
            </div>
          </Reveal>

          {/* ===== 03 · Recuperación de conversaciones abandonadas (CEO, 2026-10-28) =====
              Pasadas 24 h sin interacción, WhatsApp solo deja escribir con un
              mensaje de plantilla aprobado, que se cobra por envío (sale por Campañas). */}
          <Reveal>
            <div className="rounded-3xl p-6 md:p-10" style={card}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-10 items-center mb-8">
                <div>
                  <CobroHeader
                    numero="03"
                    titulo="Recuperación de conversaciones abandonadas"
                    cuando="Solo cuando le vuelves a escribir a quien dejó de contestar"
                  />
                  <p className="text-base leading-relaxed" style={{ color: BRAND.textMuted }}>
                    Una conversación queda abandonada cuando pasan más de 24 horas sin que el
                    cliente escriba. Desde ese momento WhatsApp solo deja volver a escribirle con un
                    mensaje aprobado, y ese mensaje se cobra. Si el cliente responde, la conversación
                    sigue con el agente y cuenta dentro de las{' '}
                    {formatNumber(PRECIOS.conversacionesIncluidas)} de tu mes.
                  </p>
                </div>
                <div className="md:text-right">
                  <Precio
                    valor={PRECIOS.mensajeCampana[moneda]}
                    moneda={moneda}
                    decimales={usd ? 3 : 0}
                  />
                  <p className="text-sm mt-2" style={{ color: BRAND.textDim }}>
                    por mensaje enviado
                  </p>
                </div>
              </div>

              {/* Diagrama: envío → responde / no responde */}
              <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: BRAND.textDim }}>
                Ejemplo: le vuelves a escribir a {formatNumber(enviados)} clientes que llevan más de 24 horas sin contestar
              </p>
              <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1.15fr] gap-2 md:gap-4 items-center">
                <div className="rounded-2xl p-5 h-full flex flex-col justify-center" style={nodo}>
                  <p className="text-sm mb-2" style={{ color: BRAND.textMuted }}>
                    Les escribes a {formatNumber(enviados)} clientes
                  </p>
                  <p className="text-sm tabular-nums" style={{ color: BRAND.textDim }}>
                    {formatNumber(enviados)} × {formatMonto(PRECIOS.mensajeCampana[moneda], usd ? 3 : 0)} {moneda}
                  </p>
                  <Precio valor={costoEnvio} moneda={moneda} size="text-2xl md:text-3xl" />
                  <p className="text-xs mt-1" style={{ color: BRAND.mint }}>
                    Inversión de la recuperación
                  </p>
                </div>
                <Flecha />
                <div className="space-y-3">
                  <div
                    className="rounded-2xl p-5"
                    style={{ ...nodo, borderColor: BRAND.cardBorderHover, backgroundColor: BRAND.mintSoft }}
                  >
                    <p className="text-base" style={{ color: BRAND.text }}>
                      <strong style={{ color: BRAND.mint }}>{formatNumber(responden)} responden</strong>
                    </p>
                    <p className="text-sm mt-1" style={{ color: BRAND.textMuted }}>
                      Son {formatNumber(responden)} conversaciones y cuentan dentro de las de tu mes.
                      No se cobran otra vez a {formatMonto(PRECIOS.mensajeCampana[moneda], usd ? 3 : 0)} {moneda}.
                    </p>
                  </div>
                  <div className="rounded-2xl p-5" style={nodo}>
                    <p className="text-base" style={{ color: BRAND.text }}>
                      <strong>{formatNumber(enviados - responden)} no responden</strong>
                    </p>
                    <p className="text-sm mt-1" style={{ color: BRAND.textMuted }}>
                      No generan ningún cobro adicional.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>

          <Reveal>
            <TablaIncluye />
          </Reveal>

          <Reveal>
            <BloqueGarantia />
          </Reveal>

          <Reveal>
            <BloqueReferidos moneda={moneda} />
          </Reveal>
        </div>

        {/* CTA */}
        <Reveal className="mt-12 md:mt-16 text-center">
          <p className="text-lg md:text-xl mb-6" style={{ color: BRAND.text }}>
            Empieza con {PRECIOS.diasPrueba} días gratis y te mostramos cuánta venta se te queda en el aire.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <BotonAgendar
              className="px-6 py-3 rounded-full text-sm font-semibold transition-opacity hover:opacity-90"
              style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
            >
              Quiero mi prueba gratis
            </BotonAgendar>
            <BotonAsesor className="px-6 py-3 rounded-full text-sm font-semibold border-2 border-white/80 text-white hover:bg-white/10 transition-colors">
              {TEXTOS_AGENDAR.whatsapp}
            </BotonAsesor>
          </div>
          {PROPUESTA_PUBLICADA && (
          <div className="mt-8">
            <a
              href={PROPUESTA_PDF}
              download
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-semibold transition-colors hover:bg-white/5"
              style={{ color: BRAND.mint, border: `1px solid ${BRAND.cardBorderHover}` }}
            >
              Descargar propuesta comercial (PDF)
            </a>
            <p className="text-xs mt-2" style={{ color: BRAND.textDim }}>
              Para compartirla con tu socio o tu equipo.
            </p>
          </div>
          )}
        </Reveal>
      </div>
    </section>
  );
}

// --- Página ----------------------------------------------------------------

export default function GlomaLanding() {
  const [form, setForm] = useState<ContactFormValues>(FORM_VACIO);
  const [status, setStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('sending');
    setMessage('');
    try {
      const res = await fetch('/api/landing/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, source: 'gloma_landing' }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        // `detail` es string en los errores de negocio (429) y una lista de
        // objetos en los 422 de Pydantic: solo mostramos el string.
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'Revisa los datos e intenta de nuevo.'
        );
      }
      setStatus('ok');
      setMessage('¡Gracias! Te contactaremos muy pronto.');
      setForm(FORM_VACIO);
    } catch (err: any) {
      setStatus('error');
      setMessage(err.message || 'No pudimos enviar tu mensaje. Intenta de nuevo.');
    }
  };

  return (
    <>
      <Head>
        <title>{SITE_TITLE}</title>
        <meta name="description" content={SITE_DESCRIPTION} />
        {/* Vista previa al compartir el enlace (WhatsApp, LinkedIn, Facebook, X). */}
        <link rel="canonical" href={SITE_URL} />
        <meta property="og:type" content="website" />
        <meta property="og:locale" content="es_CO" />
        <meta property="og:site_name" content="Gloma" />
        <meta property="og:url" content={SITE_URL} />
        <meta property="og:title" content={SITE_TITLE} />
        <meta property="og:description" content={SITE_DESCRIPTION} />
        <meta property="og:image" content={OG_IMAGE} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta property="og:image:alt" content="Tu negocio de turismo contesta su WhatsApp a cualquier hora" />
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={SITE_TITLE} />
        <meta name="twitter:description" content={SITE_DESCRIPTION} />
        <meta name="twitter:image" content={OG_IMAGE} />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </Head>

      <style jsx global>{`
        html,
        body {
          background-color: ${BRAND.bgBase};
        }
        .gloma-root ::selection {
          background: ${BRAND.mint};
          color: ${BRAND.bgBase};
        }
        .gloma-card:hover {
          border-color: ${BRAND.cardBorderHover} !important;
          box-shadow: 0 24px 60px -20px rgba(0, 0, 0, 0.55),
            0 0 50px -20px rgba(77, 182, 172, 0.35);
        }
      `}</style>

      <div
        className="gloma-root min-h-screen pb-20 md:pb-0"
        style={{ backgroundColor: BRAND.bgBase, color: BRAND.text }}
      >
        <InteractiveHeader />

        {/* ===== ¿TE SUENA? (dolores → solución) ===== */}
        <section
          aria-labelledby="te-suena-titulo"
          className="py-20 md:py-28"
          style={{ backgroundColor: BRAND.bgAlt }}
        >
          <div className="max-w-6xl mx-auto px-6 md:px-10">
            <Reveal className="text-center max-w-2xl mx-auto mb-12 md:mb-16">
              <h2
                id="te-suena-titulo"
                className="text-3xl md:text-5xl leading-tight mb-5"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 700,
                  color: BRAND.text,
                }}
              >
                ¿Te suena?
              </h2>
              <p
                className="text-base md:text-lg"
                style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.textMuted }}
              >
                Lo que nos cuentan hoteleros y empresarios, y lo que hace Gloma con eso.
              </p>
            </Reveal>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 md:gap-6">
              {DOLORES.map((d, i) => (
                <Reveal key={d.dolor} delay={i * 80}>
                  <div
                    className="gloma-card p-6 md:p-8 rounded-2xl transition-all hover:-translate-y-1 h-full"
                    style={{
                      backgroundColor: BRAND.cardBg,
                      border: `1px solid ${BRAND.cardBorder}`,
                    }}
                  >
                    <div className="flex items-start gap-4">
                      <div
                        className="w-12 h-12 shrink-0 rounded-full flex items-center justify-center"
                        style={{
                          backgroundColor: BRAND.mintSoft,
                          border: `1px solid ${BRAND.cardBorder}`,
                        }}
                      >
                        <Icono nombre={d.icon} size={22} />
                      </div>
                      <h3
                        className="text-xl md:text-2xl leading-snug pt-1.5"
                        style={{
                          fontFamily: 'Syne, system-ui, sans-serif',
                          fontWeight: 700,
                          color: BRAND.text,
                        }}
                      >
                        {d.dolor}
                      </h3>
                    </div>
                    <div
                      className="mt-5 pt-5 flex items-start gap-3"
                      style={{ borderTop: `1px solid ${BRAND.cardBorder}` }}
                    >
                      <span className="shrink-0 mt-0.5">
                        <Icono nombre="flecha" size={20} />
                      </span>
                      <p
                        className="text-base leading-relaxed"
                        style={{
                          fontFamily: 'Inter, system-ui, sans-serif',
                          color: BRAND.textMuted,
                        }}
                      >
                        {d.solucion}
                      </p>
                    </div>
                  </div>
                </Reveal>
              ))}
            </div>

          </div>
        </section>

        {/* ===== LO QUE CAMBIA EN TU NEGOCIO ===== */}
        <section
          aria-labelledby="cambia-titulo"
          className="max-w-6xl mx-auto px-6 md:px-10 py-20 md:py-28 space-y-24"
        >
          <Reveal className="text-center max-w-2xl mx-auto">
            <h2
              id="cambia-titulo"
              className="text-3xl md:text-5xl leading-tight"
              style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.text }}
            >
              Lo que cambia en tu negocio
            </h2>
          </Reveal>
          {PREVIEW_SECTIONS.map((s, i) => (
            <Reveal key={i}>
              <div
                className={`grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center ${
                  s.reverse ? 'md:[direction:rtl]' : ''
                }`}
              >
                <div className="md:[direction:ltr]">
                  <h3
                    className="text-2xl md:text-4xl mb-5 leading-tight"
                    style={{
                      fontFamily: 'Syne, system-ui, sans-serif',
                      fontWeight: 700,
                      color: BRAND.text,
                    }}
                  >
                    {s.title}
                  </h3>
                  <p
                    className="text-base md:text-lg leading-relaxed"
                    style={{
                      fontFamily: 'Inter, system-ui, sans-serif',
                      color: BRAND.textMuted,
                    }}
                  >
                    {s.text}
                  </p>
                </div>
                <div className="md:[direction:ltr]">
                  <div
                    className={`relative rounded-3xl overflow-hidden shadow-lg ${
                      s.mock ? 'aspect-[4/5] sm:aspect-[4/3]' : 'aspect-[4/3]'
                    }`}
                    style={{ border: `1px solid ${BRAND.cardBorder}` }}
                  >
                    {s.mock === 'recordatorios' ? (
                      <MockRecordatorios titulo={s.title} />
                    ) : s.image ? (
                      <Image
                        src={s.image}
                        alt={s.title}
                        fill
                        className={s.contain ? 'object-contain' : 'object-cover'}
                        style={s.contain ? { backgroundColor: '#0F0F0F' } : undefined}
                      />
                    ) : null}
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </section>

        {/* ===== FUNCIONA CON LO QUE YA USAS ===== */}
        <YaUsasSection />

        {/* ===== CÓMO EMPEZAR ===== */}
        <ComoEmpezarSection />

        {/* ===== STATS con contador animado ===== */}
        <StatsSection />

        {/* ===== PRECIOS ===== */}
        <PreciosSection />

        {/* ===== PREGUNTAS FRECUENTES ===== */}
        <FaqSection />

        {/* ===== CONTACTO ===== */}
        <section
          id="contacto"
          className="py-20 md:py-28 relative overflow-hidden"
          style={{ backgroundColor: BRAND.bgBase }}
        >
          <div
            aria-hidden="true"
            className="absolute inset-0 pointer-events-none"
            style={{
              backgroundImage:
                'radial-gradient(ellipse at 50% 100%, rgba(0,77,64,0.30), transparent 60%)',
            }}
          />
          <div className="relative max-w-5xl mx-auto px-6 md:px-10 grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-16 items-start">
            <Reveal>
              <h2
                className="text-3xl md:text-5xl mb-6 leading-tight"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 700,
                  color: BRAND.text,
                }}
              >
                Tú vendes vacaciones. Tómate las tuyas.
              </h2>
              <p
                className="text-base md:text-lg mb-8"
                style={{
                  fontFamily: 'Inter, system-ui, sans-serif',
                  color: BRAND.textMuted,
                }}
              >
                Cuéntanos de tu negocio y te mostramos cómo se vería el agente con tus destinos y tarifas reales.
              </p>
              {/* Un solo paso principal en el cierre (2026-10-20): el formulario
                  de al lado. Sin enlace a Lía (2026-10-21, CEO). */}
            </Reveal>

            <Reveal delay={120}>
              <ContactForm
                form={form}
                setForm={setForm}
                status={status}
                message={message}
                onSubmit={handleSubmit}
              />
            </Reveal>
          </div>
        </section>

        {/* ===== FOOTER ===== */}
        <footer
          style={{
            backgroundColor: BRAND.bgAlt,
            color: BRAND.text,
            borderTop: `1px solid ${BRAND.cardBorder}`,
          }}
        >
          <div className="max-w-6xl mx-auto px-6 md:px-10 py-14 grid grid-cols-1 md:grid-cols-3 gap-10">
            <div>
              <div className="flex items-center mb-4">
                <Image
                  src="/gloma/logo_blancotrans.png"
                  alt="Gloma"
                  width={320}
                  height={192}
                  className="object-contain h-28 md:h-40 w-auto"
                />
              </div>
            </div>
            <div>
              <h4
                className="text-sm font-semibold mb-4 tracking-wide uppercase"
                style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.mint }}
              >
                Contacto
              </h4>
              <ul
                className="space-y-2 text-sm opacity-80"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                <li>contacto@glomacx.com</li>
                <li>
                  <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="hover:opacity-100">
                    {telefonoFooter()}
                  </a>
                </li>
                <li>Calle 36, Vía Jamundí #128-321, Cali, Valle del Cauca</li>
              </ul>
            </div>
            <div>
              <h4
                className="text-sm font-semibold mb-4 tracking-wide uppercase"
                style={{ fontFamily: 'Inter, system-ui, sans-serif', color: BRAND.mint }}
              >
                Conecta
              </h4>
              <ul
                className="space-y-2 text-sm"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                <li>
                  <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="opacity-80 hover:opacity-100">
                    WhatsApp →
                  </a>
                </li>
                <li>
                  <a href={INSTAGRAM_URL} target="_blank" rel="noopener noreferrer" className="opacity-80 hover:opacity-100">
                    Instagram · @gloma_app →
                  </a>
                </li>
                {PROPUESTA_PUBLICADA && (
                  <li>
                    <a href={PROPUESTA_PDF} download className="opacity-80 hover:opacity-100">
                      Propuesta comercial (PDF) →
                    </a>
                  </li>
                )}
                <li>
                  <a href="/privacidad" className="opacity-80 hover:opacity-100">
                    Política de tratamiento de datos
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div
            className="border-t border-white/10 py-5 text-center text-xs opacity-60"
            style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
          >
            © 2026 Gloma.
          </div>
        </footer>

        {/* Botón flotante de WhatsApp → conversa con el bot institucional
            (Sprint 20 #270): el visitante prueba el agente sin salir de la
            landing y sin necesidad de tener WhatsApp. */}
        {/* Barra fija de móvil: en pantallas chicas el menú no muestra el CTA,
            y el tráfico de Instagram llega por aquí. Deja libre la esquina
            derecha, donde flota el botón del chat. */}
        <div
          className="md:hidden fixed inset-x-0 bottom-0 z-50 pl-4 pr-[5.5rem] pt-3"
          style={{
            paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom))',
            backgroundColor: 'rgba(16,24,23,0.94)',
            borderTop: `1px solid ${BRAND.cardBorder}`,
            backdropFilter: 'blur(8px)',
          }}
        >
          {/* #625: las dos formas de contacto; agendar manda. */}
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <BotonAgendar
              className="w-full py-3 rounded-full text-sm font-semibold"
              style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
            >
              {TEXTOS_AGENDAR.agendar}
            </BotonAgendar>
            <BotonAsesor className="px-4 py-3 rounded-full text-sm font-semibold border border-white/70 text-white">
              {TEXTOS_AGENDAR.whatsappCorto}
            </BotonAsesor>
          </div>
        </div>

        <GlomaChatWidget />
      </div>
    </>
  );
}
