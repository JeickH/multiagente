/**
 * Textos de la demo pública (`/demo`, Sprint 32, tarea #609).
 *
 * - `TIPOS_EMPRESA`: el desplegable del formulario. Las `clave` son las mismas
 *   que valida el backend en `POST /demo/iniciar` (tabla del Sprint 32 en
 *   BITACORA.md): **no se cambian sin cambiar también el backend**. Las
 *   etiquetas sí se pueden pulir.
 * - `DEMO_COPY`: las 3 slides que tapan la generación del bot, el botón de la
 *   slide 3, la ayuda de la ventana de chat y el aviso del traspaso a asesor.
 *
 * Cada slide se tiene que leer en ~5 segundos en un celular: si se agrega
 * texto, se quita otro. Los beneficios salen de lo que ya promete la landing
 * (`pages/gloma.tsx`) y de lo que la plataforma hace hoy; si cambia uno de los
 * dos, se revisa aquí.
 *
 * Placeholders: `{nombre}` y `{empresa}`. Se reemplazan con `rellenarCopy`.
 */

export const TIPOS_EMPRESA = [
  { clave: 'agencia_viajes', etiqueta: 'Agencia de viajes' },
  { clave: 'operador_turistico', etiqueta: 'Operador turístico o de tours' },
  { clave: 'hotel', etiqueta: 'Hotel' },
  { clave: 'hostal', etiqueta: 'Hostal' },
  { clave: 'glamping_finca', etiqueta: 'Glamping o finca turística' },
  { clave: 'apartamentos', etiqueta: 'Apartamentos turísticos' },
  { clave: 'transporte', etiqueta: 'Transporte turístico' },
  { clave: 'alquiler_vehiculos', etiqueta: 'Alquiler de vehículos' },
  { clave: 'actividades', etiqueta: 'Actividades y aventura' },
  { clave: 'restaurante', etiqueta: 'Restaurante' },
  { clave: 'eventos', etiqueta: 'Eventos y bodas' },
  { clave: 'otro', etiqueta: 'Otro' },
] as const;

export type ClaveTipoEmpresa = (typeof TIPOS_EMPRESA)[number]['clave'];

/** El campo corto que se abre al elegir «Otro». Es opcional. */
export const TIPO_OTRO = {
  clave: 'otro' as ClaveTipoEmpresa,
  maxCaracteres: 80,
  label: '¿Qué tipo de negocio es?',
  placeholder: 'Ej.: parque temático, guía independiente',
};

export function etiquetaTipoEmpresa(clave: string | null | undefined): string | null {
  if (!clave) return null;
  return TIPOS_EMPRESA.find((t) => t.clave === clave)?.etiqueta ?? null;
}

export interface TextoDemo {
  titulo: string;
  texto: string;
}

export interface DemoCopy {
  slides: {
    /** Slide 1. Usa `{nombre}` (solo el primer nombre) y `{empresa}`. */
    bienvenida: TextoDemo;
    /** Slide 2: los 4 beneficios, en este orden. */
    beneficios: {
      titulo: string;
      items: readonly [TextoDemo, TextoDemo, TextoDemo, TextoDemo];
    };
    /** Slide 3. Usa `{empresa}`. */
    invitacion: TextoDemo & {
      /** Botón deshabilitado mientras `estado === 'generando'`. */
      botonCargando: string;
      /** Botón activo cuando `estado === 'lista'`. */
      botonListo: string;
    };
  };
  chat: {
    /** Línea fija arriba de la ventana de chat. */
    ayuda: string;
    /** Lo que muestra el front cuando la respuesta trae `handoff: true`. Usa `{empresa}`. */
    traspaso: TextoDemo;
  };
  /** Por si `estado === 'error'` (el backend tiene respaldo, debería ser raro). */
  error: TextoDemo & { boton: string };
}

export const DEMO_COPY: DemoCopy = {
  slides: {
    bienvenida: {
      titulo: 'Hola, {nombre}',
      texto:
        'Estamos armando el agente de IA de {empresa} con 3 productos de ejemplo. Tarda unos segundos.',
    },
    beneficios: {
      titulo: 'Lo que hace en tu WhatsApp',
      items: [
        {
          titulo: 'Responde aunque no estés',
          texto: 'Atiende lo de siempre mientras tú haces otra cosa.',
        },
        {
          titulo: 'Cotiza con tus tarifas',
          texto: 'Nunca inventa un precio ni un cupo.',
        },
        {
          titulo: 'Tu asesor entra a cerrar',
          texto: 'Le pasa el cliente listo, con todo el historial.',
        },
        {
          titulo: 'Retoma a los interesados que se fueron',
          texto: 'Les vuelve a escribir cuando dejan de contestar.',
        },
      ],
    },
    invitacion: {
      titulo: 'Ahora tú eres el cliente',
      texto:
        'Escríbele como un cliente nuevo de {empresa}. Pide un precio, intenta reservar y mira cómo le pasa el chat a tu equipo.',
      botonCargando: 'Armando tu agente…',
      botonListo: 'Probar mi agente',
    },
  },
  chat: {
    ayuda: 'Tu primer mensaje ya está escrito. Solo tienes que enviarlo.',
    traspaso: {
      titulo: 'Aquí entra tu equipo',
      texto:
        'En tu cuenta, desde este punto una persona de {empresa} sigue el chat con todo el historial y cierra la reserva.',
    },
  },
  error: {
    titulo: 'No pudimos armar tu agente',
    texto: 'Inténtalo de nuevo en un momento.',
    boton: 'Intentar de nuevo',
  },
};

/**
 * Reemplaza `{nombre}` y `{empresa}` en una sola pasada, para que un nombre de
 * empresa que traiga el texto «{nombre}» no se vuelva a reemplazar. El
 * resultado se pinta como texto de React (nunca como HTML), así que lo que
 * escribió el prospecto no se interpreta.
 *
 * `nombre` debería llegar como primer nombre: «Hola, Camila», no
 * «Hola, Camila Andrea Restrepo Gómez».
 */
export function rellenarCopy(
  texto: string,
  datos: { nombre?: string | null; empresa?: string | null },
): string {
  const valores: Record<string, string> = {
    nombre: (datos.nombre ?? '').trim(),
    empresa: (datos.empresa ?? '').trim() || 'tu empresa',
  };
  return texto
    .replace(/\{(nombre|empresa)\}/g, (_, clave: string) => valores[clave])
    // «Hola, {nombre}» sin nombre queda «Hola», no «Hola, ».
    .replace(/,\s*$/, '');
}

/**
 * Microcopy de la interfaz de `/demo` (dev-plataforma, #614).
 *
 * Sale del wireframe #611 (`ventas/identidad_gloma/diseno_demo.html`, llaves
 * `data-copy`) para los textos que `DEMO_COPY` no cubre: formulario, recuadro
 * de estado del agente, ventana de chat, cierre y avisos. Vive aquí para que
 * todo el texto de la demo esté en un solo archivo; Belfort puede pulirlo sin
 * tocar los componentes. Mismos placeholders (`{nombre}`, `{empresa}`) y misma
 * regla: se pinta como texto de React, nunca como HTML.
 */
export const DEMO_UI = {
  nav: {
    conocer: 'Conocer Gloma',
  },
  intro: {
    titulo: 'Prueba el agente de IA',
    titulo2: 'de tu empresa.',
    subtitulo:
      'Cuéntanos de tu empresa y armamos un agente con productos de ejemplo. Después le escribes como si fueras un cliente.',
    pasos: [
      { titulo: 'Tus datos', detalle: '30 segundos' },
      { titulo: 'Armamos tu agente', detalle: 'mientras te contamos qué hace Gloma' },
      { titulo: 'Le escribes', detalle: 'como si fueras un cliente nuevo' },
    ],
  },
  form: {
    titulo: 'Empecemos',
    obligatorios: 'Todos los campos son obligatorios salvo los que dicen «opcional».',
    opcional: '(opcional)',
    nombre: 'Tu nombre',
    empresa: 'Nombre de tu empresa',
    empresaAyuda: 'Así se llamará el contacto en el chat de la demo.',
    tipo: 'Tipo de empresa',
    tipoPlaceholder: 'Elige el que más se parezca',
    telefono: 'Teléfono (WhatsApp)',
    /** Etiqueta (solo para lectores de pantalla) del selector de país. */
    telefonoPais: 'País del teléfono',
    telefonoIndicativo: 'Indicativo',
    telefonoAyudaOtro: 'Escribe el indicativo de tu país (sin el +) y el número.',
    correo: 'Correo',
    checkContacto: 'Acepto que Gloma me contacte sobre esta demo, según la',
    linkPrivacidad: 'política de tratamiento de datos',
    nuevaPestana: ' (se abre en otra pestaña)',
    checkPromos: 'Quiero recibir promociones y novedades de Gloma.',
    boton: 'Iniciar demo',
    botonEnviando: 'Preparando tu demo…',
    errorRed: 'No pudimos conectarnos. Revisa tu internet e inténtalo de nuevo; tus datos siguen aquí.',
    errorVerificacion: 'Estamos verificando que eres una persona. Espera unos segundos e inténtalo de nuevo.',
    topeTitulo: 'Por hoy no podemos abrir más demos',
    topeTexto:
      'Ya se hicieron varias demos hoy. Vuelve mañana, o agenda una con nuestro equipo y la armamos en vivo con tu empresa.',
    errores: {
      nombre: 'Escribe tu nombre.',
      empresa: 'Escribe el nombre de tu empresa: con él armamos tu agente.',
      tipo: 'Elige el tipo de empresa que más se parezca a la tuya.',
      telefonoVacio: 'Escribe tu teléfono.',
      telefonoInvalido: 'Revisa el teléfono: parece incompleto o le sobran dígitos.',
      /** `{pais}` y `{digitos}` («10» o «8 a 9»). */
      telefonoLargo: 'Revisa el número: en {pais} tiene {digitos} dígitos, sin el indicativo.',
      telefonoColombia: 'En Colombia el número tiene 10 dígitos y empieza por 3 (celular) o 60 (fijo).',
      telefonoIndicativo: 'Escribe el indicativo de tu país: de 1 a 4 dígitos.',
      correoVacio: 'Escribe tu correo.',
      correoInvalido: 'Revisa el correo: parece incompleto.',
      contacto: 'Para iniciar la demo necesitamos tu autorización.',
      /** Cuando el backend rechaza un campo (422) sin decir por qué. */
      generico: 'Revisa este dato.',
    },
  },
  estado: {
    dialogo: 'Tu demo de Gloma',
    generando: 'Armando el agente de {empresa}…',
    /** Subtítulos rotativos: cosméticos, la API solo dice generando|lista|error. */
    subtitulos: [
      'Inventando 3 productos de ejemplo',
      'Enseñándole cómo atender a tus clientes',
      'Escribiendo tu primer mensaje',
      'Últimos ajustes',
    ],
    lento: 'Está tardando un poco más de lo normal. Ya casi.',
    reconectando: 'Reconectando…',
    listo: 'Tu agente está listo',
    listoSub: 'Ya conoce 3 productos de {empresa}',
    anuncioListo: 'Tu agente está listo. Ya puedes probarlo.',
    anuncioError: 'No pudimos armar tu agente. Puedes intentarlo de nuevo.',
    probarAhora: 'Probar ahora →',
  },
  slides: {
    carrusel: 'Qué es Gloma',
    /**
     * Texto de la slide 1 cuando el agente ya está listo (en pasado), en vez
     * de `DEMO_COPY.slides.bienvenida.texto` («Estamos armando…»). Usa `{empresa}`.
     */
    bienvenidaLista:
      'Ya armamos el agente de IA de {empresa} con 3 productos de ejemplo. Puedes probarlo cuando quieras.',
    pistaMovil: 'Desliza para seguir →',
    pistaEscritorio: 'Usa las flechas o el teclado (← →) para seguir.',
    siguiente: 'Siguiente',
    anterior: 'Slide anterior',
    irA: 'Ir a la slide {n} de 3',
    botonCargandoAyuda: 'Suele tardar menos de 20 segundos.',
    productosCargando: 'Tu agente está aprendiendo sus productos…',
    productosListos: 'Tu agente ya conoce:',
    nuevaDemo: 'Hacer una demo nueva',
  },
  chat: {
    enLinea: 'en línea',
    escribiendo: 'escribiendo…',
    anuncioEscribiendo: '{empresa} está escribiendo',
    etiquetaDemo: 'Demo',
    /** Aviso fijo de la cabecera (#608, M4). No se puede cerrar. */
    avisoIA: 'Demostración generada con IA · productos y precios ficticios',
    ayudaLinea: 'Eres un cliente nuevo de {empresa}. Pregunta lo que quieras.',
    ideasBoton: 'Ideas',
    ideasTitulo: 'Toca una idea y se escribe en tu mensaje:',
    panelEyebrow: 'Tu demo',
    panelTitulo: 'Estás probando el agente de',
    panelProductos: 'Lo que sabe tu agente',
    panelIdeas: 'Ideas para probarlo',
    ideas: [
      '¿Cuánto cuesta {producto}?',
      // Sin preguntar por disponibilidad: el bot de demo no la afirma (la
      // confirma el equipo al reservar), y la respuesta luciría evasiva.
      '¿Cuánto sale para 2 personas este fin de semana?',
      'Quiero hablar con un asesor',
    ],
    hoy: 'Hoy',
    /** Chip de sistema al inicio del hilo (#608, M5). ≤140 caracteres. */
    avisoSistema:
      'Guardamos esta conversación para mejorar la demo. No compartas datos personales reales: documentos, tarjetas ni contraseñas.',
    etiquetaMensaje: 'Mensaje para {empresa}',
    placeholder: 'Escribe un mensaje',
    sugeridoSr: 'Mensaje sugerido ya escrito. Puedes enviarlo tal cual o cambiarlo.',
    enviar: 'Enviar mensaje',
    noEnviado: 'No se envió.',
    reintentar: 'Toca para reintentar',
    anuncioNoEnviado: 'El mensaje no se envió. Botón para reintentar disponible.',
    checkEnviado: 'Enviado',
    checkEntregado: 'Entregado',
    checkLeido: 'Leído',
    /** `finished=true` sin `handoff` (fin natural o tope de turnos). */
    finTitulo: 'Esta demo llegó a su fin',
    finTexto: 'Gracias por probarla. Si quieres seguir, lo vemos juntos.',
    finBarra: 'La demo terminó.',
    anuncioHandoff: 'Un asesor de {empresa} tomaría la conversación. La demo terminó.',
    anuncioFin: 'La demo terminó.',
  },
  /** Los botones «Agendar una llamada» / «Hablar con un asesor» están en `lib/agendarLlamada.ts`. */
  cta: {
    panelTitulo: '¿Te lo imaginas en tu WhatsApp?',
    panelTexto: 'Lo armamos con tus productos y precios reales.',
    finTitulo: '¿Lo quieres en tu WhatsApp?',
    finTexto: 'Agenda 20 minutos con Gloma y lo armamos con tus productos y precios reales.',
  },
  noDisponible: {
    titulo: 'Esta demo ya no está disponible',
    texto: 'Puede que haya vencido o que se haya abierto en otro navegador.',
    boton: 'Hacer una demo nueva',
  },
  cargando: 'Recuperando tu demo…',
  /**
   * Pantalla de premio entre el formulario y las slides (#643, solo local
   * hasta que el CEO la apruebe). Los montos se cambian aquí. El monto de
   * Colombia aplica si el teléfono registrado es +57; si no, el de USD. No
   * agregar condiciones, vigencias ni letra pequeña que el CEO no haya dado.
   */
  premio: {
    /** Usa `{nombre}` (primer nombre). */
    eyebrow: '¡Felicitaciones, {nombre}!',
    titulo: 'Ganaste una promoción especial',
    prefijoMonto: 'hasta',
    montoColombia: '$1.285.200 COP',
    montoExterior: 'USD 402',
    sufijoMonto: 'en servicios de Gloma',
    /** Qué es la promoción (2026-10-28). Lo repiten el correo y el WhatsApp del panel /demos. */
    detalle: '50\u00a0% de descuento en tu primer mes y 35\u00a0% en el segundo y el tercero del plan mensual.',
    /** Que se note que se suma a lo que ya trae el plan. */
    seSuma: 'Y se suma a tus 14 días de prueba gratis y a la instalación, que no te cuesta nada.',
    envio: 'Te la enviamos a tu correo y a tu WhatsApp:',
    correo: 'Correo',
    whatsapp: 'WhatsApp',
    mientras: 'Mientras tanto, seguimos armando tu agente de IA.',
    boton: 'Continuar con la demo',
  },
  /** Texto prellenado del WhatsApp de Gloma («Hablar con un asesor»). */
  agendar: {
    despuesDeLaDemo: 'Hola, acabo de probar la demo de {empresa} y quiero agendar una llamada',
    sinDemo: 'Hola, quiero agendar una demo de Gloma',
  },
} as const;
