import Head from 'next/head';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';

import GlomaChatWidget, { OPEN_CHAT_EVENT } from '../components/GlomaChatWidget';
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
  // Micro-acento del destello del logo: menos del 5 % de la página.
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
  | 'soporte' | 'mensajes' | 'retorno' | 'horas';

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
const PREVIEW_SECTIONS = [
  {
    title: 'Un agente de ventas que trabaja sin parar',
    text: 'Atiende a tus clientes 24/7 con un tono alineado a tu marca y procesos. La cercanía humana, multiplicada por la disponibilidad de la tecnología.',
    image: '/gloma/preview_chat_agente.png',
    reverse: false,
  },
  {
    title: 'Aumenta ventas con campañas por WhatsApp',
    text: 'Campañas segmentadas por destino y fecha de viaje: reactiva cotizaciones frías y vende febrero mientras todos venden diciembre.',
    image: '/gloma/preview5.png',
    reverse: true,
  },
  {
    title: 'Tu equipo entra a cerrar, no a saludar',
    text: 'Nuestros bots actúan como un primer filtro inteligente, resolviendo lo repetitivo y escalando a un humano solo cuando hace falta.',
    image: '/gloma/preview6.png',
    reverse: false,
  },
  {
    title: 'Un tablero que te muestra dónde se pierde cada venta',
    text: 'Cada cliente recibe un dashboard analítico con el resultado de sus conversaciones: cuántas terminan en venta o en manos de tu equipo, cuántas se abandonan y en qué paso del embudo se va la gente. Con esos datos decidimos qué ajustar.',
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
    q: '¿Qué cuenta como una conversación?',
    a: 'Un chat con un cliente dentro de una ventana de 24 horas. Si ese mismo cliente vuelve a escribir después de las 24 horas, cuenta como una conversación nueva.',
  },
  {
    q: '¿Los precios incluyen el IVA y lo que cobra Meta?',
    a: 'Sí. Los precios ya incluyen el IVA y el costo de WhatsApp que cobra Meta. No hay cobros adicionales por ninguno de los dos.',
  },
  {
    q: '¿Tengo que pagar una mensualidad?',
    a: 'No. Compras un paquete de conversaciones y lo recargas cuando se acaba. Si un mes no las usas todas, las que sobran pasan al mes siguiente.',
  },
  {
    q: '¿El agente puede inventar precios o disponibilidad?',
    a: 'No. Responde solo con la información que nos das (tarifarios, itinerarios, políticas) y tiene prohibido inventar precios, cupos o promociones. Si le falta un dato, pasa la conversación a tu equipo.',
  },
  {
    q: '¿Qué pasa si el agente no sabe responder algo?',
    a: 'Lo dice y pasa la conversación a una persona de tu equipo, con todo lo que el cliente ya preguntó, para que no tenga que repetirlo.',
  },
  {
    q: '¿Cuánto tarda en estar listo?',
    a: 'Depende de cuánta información tengamos de tu operación y de la conexión de tu número con Meta, que depende de tus accesos. Lo estimamos en la demo con tu caso. Una vez en marcha, los primeros 10 días son de ajuste.',
  },
  {
    q: '¿Qué pasa con los datos de mis clientes?',
    a: 'Viven en tu propia cuenta, aislada de las demás, en infraestructura de AWS. Las credenciales se guardan cifradas y las conversaciones no se usan para entrenar modelos de IA. El manejo se alinea con la Ley 1581 de protección de datos.',
  },
  {
    q: '¿Puedo probarlo antes de contratar?',
    a: 'Sí. Lía, la asistente de esta página, funciona con el mismo motor que tendría tu agente: escríbele como lo haría uno de tus clientes. Y antes de salir en vivo, pruebas tu propio agente en el simulador de la plataforma.',
  },
];

/** Ruta de arranque de un cliente nuevo (definida por el CEO el 2026-09-27). */
const PASOS_INICIO = [
  {
    titulo: 'Entrenamos a tu nuevo asesor',
    texto: 'Recogemos cómo opera tu agencia: guiones, mensajes predefinidos y el proceso de venta que ya usan. Con eso entrenamos al agente para que sea un asesor más de tu equipo, con las mismas reglas y el tono de tu marca.',
    etiqueta: null,
  },
  {
    titulo: 'Activamos tu cuenta y tu WhatsApp',
    texto: 'Activamos la cuenta y nuestro equipo instala tu WhatsApp, conectado al canal de comunicación que elija tu empresa.',
    etiqueta: null,
  },
  {
    titulo: 'Arranca la operación',
    texto: 'El agente empieza a atender a tus clientes y durante los primeros 10 días ajustamos los detalles con las conversaciones que van llegando.',
    etiqueta: '10 días de ajuste',
  },
  {
    titulo: 'Soporte y mejora continua',
    texto: 'Después de la instalación tienes soporte 24/7 y rondas constantes de mejora, a partir de los reportes de desempeño del agente.',
    etiqueta: 'Soporte 24/7',
  },
];

const FEATURES = [
  {
    icon: 'personaliza' as IconoNombre,
    title: 'Personalizado al ADN de tu marca',
    text: 'Configuramos el tono, las respuestas y los flujos para que cada mensaje sea indistinguible del de tu equipo.',
  },
  {
    icon: 'integraciones' as IconoNombre,
    title: 'Integraciones fluidas',
    text: 'Se alimenta de tus tarifarios, itinerarios y políticas para cotizar con datos correctos, nunca inventados.',
  },
  {
    icon: 'contexto' as IconoNombre,
    title: 'Conoce tus destinos antes del primer mensaje',
    text: 'Sabe qué destinos vendes, a qué precio y con qué condiciones desde el primer día.',
  },
  {
    icon: 'escalamiento' as IconoNombre,
    title: 'Escalamiento a agentes humanos',
    text: 'Cuando la conversación lo requiere, la derivamos a tu equipo con todo el contexto listo.',
  },
  {
    icon: 'medicion' as IconoNombre,
    title: 'Medición y mejora continua',
    text: 'Tableros claros de conversiones, tiempos y satisfacción para seguir afinando la operación.',
  },
  {
    icon: 'soporte' as IconoNombre,
    title: 'Equipo de soporte dedicado',
    text: 'Un equipo disponible para atender requerimientos, ajustes de flujos y nuevos casos de uso.',
  },
];

const STATS = [
  {
    icon: 'mensajes' as IconoNombre,
    value: 150000,
    prefix: '+',
    suffix: '',
    label: 'mensajes de viajeros gestionados',
  },
  {
    icon: 'retorno' as IconoNombre,
    value: 4,
    prefix: '',
    suffix: ' meses',
    label: 'de retorno de inversión promedio',
  },
  {
    icon: 'horas' as IconoNombre,
    value: 10000,
    prefix: '+',
    suffix: '',
    label: 'horas de asesores AI operando',
  },
];

/**
 * Precios públicos (definidos por el CEO el 2026-09-27). Son tres cobros:
 * instalación única, paquetes de conversaciones prepagados que se acumulan
 * mes a mes, y campañas masivas por mensaje enviado. El contexto del bot
 * (`backend/app/bot_contexts/gloma.md`) repite estas cifras: si cambian aquí,
 * cambian allá.
 */
type Moneda = 'COP' | 'USD';

const PRECIOS = {
  instalacion: { COP: 2_000_000, USD: 625 },
  paquetes: [
    { conversaciones: 600, COP: 640_000, USD: 205 },
    { conversaciones: 2_000, COP: 2_090_000, USD: 670 },
    { conversaciones: 6_000, COP: 6_000_000, USD: 1_920 },
  ],
  mensajeCampana: { COP: 75, USD: 0.025 },
};

/** Ejemplos de los gráficos. Son ilustrativos y así se rotulan en la página. */
const EJEMPLO_CAMPANA = { enviados: 1_000, responden: 120 };
const EJEMPLO_ACUMULADO = { paquete: 600, usadas: 450 };

const WHATSAPP_URL =
  'https://wa.me/573150764000?text=Hola%20Gloma%2C%20tengo%20una%20agencia%20de%20viajes%20y%20quiero%20ver%20una%20demo';

const INSTAGRAM_URL = 'https://www.instagram.com/gloma_app/';

/** Imagen y URL canónica para la vista previa al compartir el enlace. */
const SITE_URL = 'https://glomacx.com';
const OG_IMAGE = `${SITE_URL}/gloma/og_gloma.png`;
const SITE_TITLE = 'Gloma — IA que vende viajes por WhatsApp';
const SITE_DESCRIPTION =
  'Un asesor con IA que cotiza con tus tarifas, responde por WhatsApp a cualquier hora y le pasa a tu equipo los clientes listos para cerrar.';

/** La plataforma vive en su propio subdominio (#303). */
const APP_URL = 'https://app.glomacx.com';

/**
 * Scroll suave hacia la sección de contacto con un easing más agradable que
 * el `scroll-behavior: smooth` nativo, que en Chrome se siente plano.
 * Animación 1s con cubic ease-in-out + un pequeño offset para que el título
 * no quede pegado al borde superior.
 */
/**
 * Abre el chat con el bot institucional que vive en `GlomaChatWidget` (#299).
 * El visitante prueba el agente en la misma página: no necesita tener el
 * WhatsApp de Gloma ni salir de la landing.
 *
 * Con `mensaje`, la conversación arranca con esa intención ya dicha (#302):
 * el bot responde a eso de una — p. ej. con las franjas disponibles para la
 * demo — en lugar de empezar por el saludo.
 */
function abrirChatDelBot(mensaje?: string) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(OPEN_CHAT_EVENT, {
      detail: mensaje ? { message: mensaje } : undefined,
    })
  );
}

/** Textos de los dos llamados a la acción, iguales en toda la página. */
const CTA_DEMO = 'Agenda una demo';
const CTA_LIA = 'Habla con Lía ahora';

/** Lo que "escribe" el visitante al pulsar "Agenda una demo" (#302). */
const MENSAJE_AGENDAR_DEMO =
  'Quiero agendar una demostración. ¿Qué horarios tienen disponibles?';

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
 * Header con parallax sutil: un par de orbes pasteles que siguen el cursor
 * (1-2% del movimiento) y evocan las "conexiones" del logo Gloma.
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

  // Círculos decorativos — sus posiciones se modifican con el cursor (parallax distinto para cada uno)
  const orbs = [
    { size: 260, top: '10%', left: '8%', bg: BRAND.mint, factor: 40, opacity: 0.35 },
    { size: 160, top: '60%', left: '18%', bg: BRAND.forest, factor: 30, opacity: 0.55 },
    { size: 320, top: '20%', right: '6%', bg: BRAND.mint, factor: 55, opacity: 0.22 },
    { size: 120, top: '70%', right: '24%', bg: BRAND.forest, factor: 22, opacity: 0.6 },
  ];

  return (
    <header
      ref={headerRef}
      className="relative w-full overflow-hidden"
      style={{ minHeight: '92vh' }}
    >
      {/* Imagen de fondo */}
      <div className="absolute inset-0 z-0">
        <Image
          src="/gloma/banner.png"
          alt="Gloma banner"
          fill
          priority
          className="object-cover"
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              'linear-gradient(to right, rgba(16,24,23,0.88), rgba(16,24,23,0.45))',
          }}
        />
      </div>

      {/* Orbes parallax */}
      <div className="absolute inset-0 z-0 pointer-events-none" aria-hidden="true">
        {orbs.map((orb, i) => {
          const base: React.CSSProperties = {
            position: 'absolute',
            width: orb.size,
            height: orb.size,
            top: orb.top,
            ...(orb.left ? { left: orb.left } : {}),
            ...(orb.right ? { right: orb.right } : {}),
            backgroundColor: orb.bg,
            opacity: orb.opacity,
            borderRadius: '9999px',
            filter: 'blur(60px)',
            transform: `translate3d(${offset.x * orb.factor}px, ${offset.y * orb.factor}px, 0)`,
            transition: 'transform 400ms cubic-bezier(.22,.61,.36,1)',
          };
          return <div key={i} style={base} />;
        })}
      </div>

      {/* SVG con líneas + nodos que evocan el logo, también parallaxea */}
      <svg
        className="absolute inset-0 z-0 pointer-events-none w-full h-full"
        aria-hidden="true"
        viewBox="0 0 1200 800"
        preserveAspectRatio="xMidYMid slice"
        style={{
          transform: `translate3d(${offset.x * -15}px, ${offset.y * -15}px, 0)`,
          transition: 'transform 500ms cubic-bezier(.22,.61,.36,1)',
        }}
      >
        <defs>
          <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={BRAND.mint} stopOpacity="0.7" />
            <stop offset="100%" stopColor={BRAND.mint} stopOpacity="0" />
          </linearGradient>
        </defs>
        <g fill="none" stroke="url(#lineGrad)" strokeWidth="1.3">
          <path d="M 80,160 C 240,120 380,280 520,220" />
          <path d="M 160,620 C 360,520 520,680 760,560" />
          <path d="M 900,140 C 1020,220 1120,380 1040,540" />
        </g>
        <g fill={BRAND.mint}>
          <circle cx="80" cy="160" r="5" opacity="0.9" />
          <circle cx="240" cy="120" r="3.5" opacity="0.75" />
          <circle cx="520" cy="220" r="4.5" opacity="0.8" />
          <circle cx="760" cy="560" r="4" opacity="0.7" />
          <circle cx="1040" cy="540" r="4.5" opacity="0.85" />
          <circle cx="900" cy="140" r="4" opacity="0.8" />
        </g>
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
          {/* #302: en vez de bajar al formulario, le pide la demo al agente —
              que responde con las franjas disponibles y la registra. */}
          <button
            type="button"
            onClick={() => abrirChatDelBot(MENSAJE_AGENDAR_DEMO)}
            className="px-5 py-2 rounded-full text-sm font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            {CTA_DEMO}
          </button>
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
        <p
          className="flex items-center gap-2 text-sm md:text-base font-medium mb-5"
          style={{
            color: BRAND.softMint,
            fontFamily: 'Inter, system-ui, sans-serif',
            opacity: inView ? 1 : 0,
            transition: 'opacity 900ms ease',
          }}
        >
          <span
            aria-hidden="true"
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: BRAND.golden }}
          />
          Cada viaje empieza con una conversación
        </p>
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
          Tu agencia vende viajes por WhatsApp,{' '}
          <span className="whitespace-nowrap" style={{ color: BRAND.mint }}>las 24 horas</span>
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
          Un asesor con IA que cotiza con tus tarifas, responde a cualquier hora y le pasa a
          tu equipo los clientes listos para cerrar.
        </p>
        <div
          className="mt-10 flex flex-col sm:flex-row gap-3"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 300ms, transform 900ms cubic-bezier(.22,.61,.36,1) 300ms',
          }}
        >
          {/* CTAs unificados en toda la página: el principal siempre es
              "Agenda una demo" (#302: se lo pide al agente, que ofrece las
              franjas) y el secundario, conversar con Lía aquí mismo. */}
          <button
            type="button"
            onClick={() => abrirChatDelBot(MENSAJE_AGENDAR_DEMO)}
            className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center transition-opacity hover:opacity-90"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            {CTA_DEMO}
          </button>
          <button
            type="button"
            onClick={() => abrirChatDelBot()}
            className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center border-2 border-white/80 text-white hover:bg-white/10 transition-colors"
          >
            {CTA_LIA}
          </button>
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
              demo con el paquete ya calculado. */}
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.textMuted }}>
            Agencia
          </label>
          <input
            type="text"
            required
            maxLength={120}
            value={form.agencia}
            onChange={(e) => setForm({ ...form, agencia: e.target.value })}
            placeholder="Nombre de tu agencia"
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
              Autorizo a Gloma a tratar mis datos para contactarme, según la{' '}
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
      <div className="relative max-w-5xl mx-auto px-6 md:px-10">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-6 text-center">
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
                className="text-4xl lg:text-[2.6rem] mb-2 tabular-nums whitespace-nowrap"
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
      </div>
    </section>
  );
}

// --- Cómo empezar ---------------------------------------------------------

/** Texto secundario sobre Soft Mint: Technical Black al 72 % (contraste AA). */
const TEXTO_CLARO_MUTED = 'rgba(16,24,23,0.72)';

/**
 * Ruta de 4 pasos: horizontal en escritorio (una línea une los nodos) y
 * vertical en móvil (la línea baja por la izquierda).
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
            Tu equipo nos cuenta cómo vende. Del resto nos encargamos nosotros.
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
              <Reveal delay={i * 120} className="flex md:flex-col md:items-center gap-5 md:gap-0 md:text-center">
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
                <div>
                  <h3
                    className="text-lg md:text-xl mb-2 leading-snug"
                    style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 700, color: BRAND.bgBase }}
                  >
                    {paso.titulo}
                  </h3>
                  <p className="text-sm leading-relaxed" style={{ color: TEXTO_CLARO_MUTED }}>
                    {paso.texto}
                  </p>
                  {paso.etiqueta && (
                    <span
                      className="inline-block mt-4 px-3 py-1 rounded-full text-xs font-semibold"
                      style={{ backgroundColor: 'rgba(0,77,64,0.08)', color: BRAND.forest, border: '1px solid rgba(0,77,64,0.2)' }}
                    >
                      {paso.etiqueta}
                    </span>
                  )}
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
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
            ¿Tienes otra pregunta? Lía te responde ahora mismo.
          </p>
          <button
            type="button"
            onClick={() => abrirChatDelBot()}
            className="px-6 py-3 rounded-full text-sm font-semibold border-2 border-white/80 text-white hover:bg-white/10 transition-colors"
          >
            {CTA_LIA}
          </button>
        </Reveal>
      </div>
    </section>
  );
}

// --- Precios ---------------------------------------------------------------

/** `$2.000.000` / `$0,025`: separadores de Colombia en las dos monedas. */
function formatMonto(valor: number, decimales = 0): string {
  return (
    '$' +
    new Intl.NumberFormat('es-CO', {
      minimumFractionDigits: decimales,
      maximumFractionDigits: decimales,
    }).format(valor)
  );
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

function PreciosSection() {
  const [moneda, setMoneda] = useState<Moneda>('COP');
  const usd = moneda === 'USD';

  const { enviados, responden } = EJEMPLO_CAMPANA;
  const costoEnvio = enviados * PRECIOS.mensajeCampana[moneda];
  const sobran = EJEMPLO_ACUMULADO.paquete - EJEMPLO_ACUMULADO.usadas;
  const pctUsadas = (EJEMPLO_ACUMULADO.usadas / EJEMPLO_ACUMULADO.paquete) * 100;

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
            Cuánto cuesta Gloma
          </h2>
          <p className="text-base md:text-lg" style={{ color: BRAND.textMuted }}>
            Pagas la instalación una sola vez. Después, el agente funciona con un paquete de
            conversaciones que recargas cuando se acaba, y las campañas se pagan por mensaje
            enviado.
          </p>

          <ul className="flex flex-wrap justify-center gap-2 mt-6" aria-label="Lo que incluyen los precios">
            {['IVA incluido', 'Costo de Meta incluido', 'Sin mensualidad'].map((t) => (
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
          {/* ===== 01 · Instalación ===== */}
          <Reveal>
            <div className="rounded-3xl p-6 md:p-10 grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-10 items-center" style={card}>
              <div>
                <CobroHeader numero="01" titulo="Instalación" cuando="Pago único, al empezar" />
                <p className="text-base leading-relaxed" style={{ color: BRAND.textMuted }}>
                  Configuramos el agente con tus destinos, tarifas y el tono de tu marca,
                  conectamos tu número de WhatsApp y lo probamos contigo antes de que hable con
                  el primer cliente.
                </p>
              </div>
              <div className="md:text-right">
                <Precio valor={PRECIOS.instalacion[moneda]} moneda={moneda} />
                <p className="text-sm mt-2" style={{ color: BRAND.textDim }}>
                  Se paga una vez
                </p>
              </div>
            </div>
          </Reveal>

          {/* ===== 02 · Paquetes de conversaciones ===== */}
          <Reveal>
            <div className="rounded-3xl p-6 md:p-10" style={card}>
              <CobroHeader
                numero="02"
                titulo="Agente de servicio al cliente y ventas"
                cuando="Funciona con paquetes de conversaciones que recargas"
              />
              <p className="text-sm mb-6 -mt-2" style={{ color: BRAND.textMuted }}>
                <strong style={{ color: BRAND.text }}>Una conversación</strong> es un chat con un
                cliente dentro de una ventana de 24 horas. Compras un paquete y lo recargas cuando
                se acaba: no es una mensualidad.
              </p>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
                {PRECIOS.paquetes.map((p) => {
                  const porConversacion = p[moneda] / p.conversaciones;
                  return (
                    <div
                      key={p.conversaciones}
                      className="gloma-card rounded-2xl p-6 transition-all"
                      style={nodo}
                    >
                      <p
                        className="text-3xl md:text-4xl tabular-nums"
                        style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800, color: BRAND.mint }}
                      >
                        {formatNumber(p.conversaciones)}
                      </p>
                      <p className="text-sm mb-5" style={{ color: BRAND.textMuted }}>
                        conversaciones
                      </p>
                      <Precio valor={p[moneda]} moneda={moneda} size="text-2xl lg:text-[1.7rem]" apilado />
                      <p className="text-xs mt-3" style={{ color: BRAND.textDim }}>
                        {formatMonto(porConversacion, usd ? 3 : 0)} {moneda} por conversación
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Gráfico: lo que no se usa pasa al mes siguiente */}
              <div className="mt-8 grid grid-cols-1 md:grid-cols-[1fr_auto_1fr] gap-2 md:gap-4 items-stretch">
                <div className="rounded-2xl p-5" style={nodo}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: BRAND.textDim }}>
                    Mes 1 · paquete de {formatNumber(EJEMPLO_ACUMULADO.paquete)}
                  </p>
                  <div
                    className="h-4 rounded-full overflow-hidden flex"
                    style={{ backgroundColor: BRAND.mintSoft }}
                    role="img"
                    aria-label={`Se usan ${EJEMPLO_ACUMULADO.usadas} de ${EJEMPLO_ACUMULADO.paquete} conversaciones y sobran ${sobran}`}
                  >
                    <div style={{ width: `${pctUsadas}%`, backgroundColor: 'rgba(230,239,238,0.25)' }} />
                    <div style={{ width: `${100 - pctUsadas}%`, backgroundColor: BRAND.mint }} />
                  </div>
                  <div className="flex justify-between text-xs mt-2" style={{ color: BRAND.textMuted }}>
                    <span>{formatNumber(EJEMPLO_ACUMULADO.usadas)} usadas</span>
                    <span style={{ color: BRAND.mint }}>{formatNumber(sobran)} sin usar</span>
                  </div>
                </div>
                <Flecha />
                <div className="rounded-2xl p-5" style={{ ...nodo, borderColor: BRAND.cardBorderHover }}>
                  <p className="text-xs font-semibold uppercase tracking-wide mb-3" style={{ color: BRAND.textDim }}>
                    Mes 2
                  </p>
                  <p className="text-base" style={{ color: BRAND.text }}>
                    Arrancas con{' '}
                    <strong style={{ color: BRAND.mint }}>{formatNumber(sobran)} conversaciones</strong>{' '}
                    que no pagas de nuevo. Cuando se acaben, recargas.
                  </p>
                </div>
              </div>
              <p className="text-xs mt-3" style={{ color: BRAND.textDim }}>
                Ejemplo ilustrativo. Las conversaciones que no usas no se pierden: se acumulan
                para el mes siguiente.
              </p>
            </div>
          </Reveal>

          {/* ===== 03 · Campañas masivas ===== */}
          <Reveal>
            <div className="rounded-3xl p-6 md:p-10" style={card}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-10 items-center mb-8">
                <div>
                  <CobroHeader
                    numero="03"
                    titulo="Campañas masivas por WhatsApp"
                    cuando="Solo cuando envías una campaña"
                  />
                  <p className="text-base leading-relaxed" style={{ color: BRAND.textMuted }}>
                    El cobro es por el primer mensaje, el del envío masivo. Si el cliente te
                    responde, desde ahí es una conversación del agente y se descuenta de tu
                    paquete.
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
                Ejemplo: una campaña a {formatNumber(enviados)} contactos
              </p>
              <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1.15fr] gap-2 md:gap-4 items-center">
                <div className="rounded-2xl p-5 h-full flex flex-col justify-center" style={nodo}>
                  <p className="text-sm mb-2" style={{ color: BRAND.textMuted }}>
                    Envías {formatNumber(enviados)} mensajes
                  </p>
                  <p className="text-sm tabular-nums" style={{ color: BRAND.textDim }}>
                    {formatNumber(enviados)} × {formatMonto(PRECIOS.mensajeCampana[moneda], usd ? 3 : 0)}
                  </p>
                  <Precio valor={costoEnvio} moneda={moneda} size="text-2xl md:text-3xl" />
                  <p className="text-xs mt-1" style={{ color: BRAND.mint }}>
                    Cobro de la campaña
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
                      Son {formatNumber(responden)} conversaciones y se descuentan de tu paquete.
                      No se cobran otra vez a {formatMonto(PRECIOS.mensajeCampana[moneda], usd ? 3 : 0)}.
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
        </div>

        {/* CTA */}
        <Reveal className="mt-12 md:mt-16 text-center">
          <p className="text-lg md:text-xl mb-6" style={{ color: BRAND.text }}>
            ¿No sabes qué paquete te conviene? Lo calculamos con el volumen de chats de tu agencia.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button
              type="button"
              onClick={() => abrirChatDelBot(MENSAJE_AGENDAR_DEMO)}
              className="px-6 py-3 rounded-full text-sm font-semibold transition-opacity hover:opacity-90"
              style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
            >
              {CTA_DEMO}
            </button>
            <a
              href={WHATSAPP_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-3 rounded-full text-sm font-semibold border-2 border-white/80 text-white hover:bg-white/10 transition-colors"
            >
              Escríbenos por WhatsApp
            </a>
          </div>
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
        <meta property="og:image:alt" content="Tu agencia vende viajes por WhatsApp, las 24 horas" />
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

        {/* ===== PREVIEW ===== */}
        <section className="max-w-6xl mx-auto px-6 md:px-10 py-20 md:py-28 space-y-24">
          {PREVIEW_SECTIONS.map((s, i) => (
            <Reveal key={i}>
              <div
                className={`grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center ${
                  s.reverse ? 'md:[direction:rtl]' : ''
                }`}
              >
                <div className="md:[direction:ltr]">
                  <h2
                    className="text-2xl md:text-4xl mb-5 leading-tight"
                    style={{
                      fontFamily: 'Syne, system-ui, sans-serif',
                      fontWeight: 700,
                      color: BRAND.text,
                    }}
                  >
                    {s.title}
                  </h2>
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
                    className="relative aspect-[4/3] rounded-3xl overflow-hidden shadow-lg"
                    style={{ border: `1px solid ${BRAND.cardBorder}` }}
                  >
                    <Image
                      src={s.image}
                      alt={s.title}
                      fill
                      className={s.contain ? 'object-contain' : 'object-cover'}
                      style={s.contain ? { backgroundColor: '#0F0F0F' } : undefined}
                    />
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </section>

        {/* ===== FEATURES ===== */}
        <section className="py-20 md:py-28" style={{ backgroundColor: BRAND.bgAlt }}>
          <div className="max-w-6xl mx-auto px-6 md:px-10">
            <Reveal className="text-center max-w-2xl mx-auto mb-14 md:mb-20">
              <h2
                className="text-3xl md:text-5xl leading-tight"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 700,
                  color: BRAND.text,
                }}
              >
                Todo lo que necesitas, sin fricciones
              </h2>
            </Reveal>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8 md:gap-10">
              {FEATURES.map((f, i) => (
                <Reveal key={f.title} delay={i * 80}>
                  <div
                    className="gloma-card p-6 md:p-7 rounded-2xl transition-all hover:-translate-y-1 h-full"
                    style={{
                      backgroundColor: BRAND.cardBg,
                      border: `1px solid ${BRAND.cardBorder}`,
                    }}
                  >
                    <div
                      className="w-14 h-14 rounded-full flex items-center justify-center mb-4 overflow-hidden"
                      style={{
                        backgroundColor: BRAND.mintSoft,
                        border: `1px solid ${BRAND.cardBorder}`,
                      }}
                    >
                      <Icono nombre={f.icon} />
                    </div>
                    <h3
                      className="text-lg md:text-xl mb-2"
                      style={{
                        fontFamily: 'Syne, system-ui, sans-serif',
                        fontWeight: 600,
                        color: BRAND.text,
                      }}
                    >
                      {f.title}
                    </h3>
                    <p
                      className="text-sm leading-relaxed"
                      style={{
                        fontFamily: 'Inter, system-ui, sans-serif',
                        color: BRAND.textMuted,
                      }}
                    >
                      {f.text}
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

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
                ¿Listo para vender más sin ampliar tu equipo?
              </h2>
              <p
                className="text-base md:text-lg mb-8"
                style={{
                  fontFamily: 'Inter, system-ui, sans-serif',
                  color: BRAND.textMuted,
                }}
              >
                Cuéntanos de tu agencia y te mostramos cómo se vería el agente con tus destinos y tarifas reales.
              </p>
              {/* #299: abre la conversación con el bot de la landing en vez de
                  mandar a wa.me — el visitante prueba el agente aquí mismo. */}
              <button
                type="button"
                onClick={() => abrirChatDelBot()}
                className="inline-flex items-center px-5 py-3 rounded-full text-sm font-semibold transition-transform hover:-translate-y-0.5"
                style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
              >
                {CTA_LIA}
              </button>
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
                    +57 315 076 4000
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
          <button
            type="button"
            onClick={() => abrirChatDelBot(MENSAJE_AGENDAR_DEMO)}
            className="w-full py-3 rounded-full text-sm font-semibold"
            style={{ backgroundColor: BRAND.mint, color: BRAND.bgBase }}
          >
            {CTA_DEMO}
          </button>
        </div>

        <GlomaChatWidget />
      </div>
    </>
  );
}
