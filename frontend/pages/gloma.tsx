import Head from 'next/head';
import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';

/**
 * Landing page de Gloma.
 *
 * Identidad (identidad_gloma/branding_gloma_v2.html):
 *  - Paleta: Rosa empolvado #F7D1CD, Marrón tierra #5E503F, Crema #FDFBF7.
 *  - Tipografía: Syne (títulos) + Inter (cuerpo).
 *  - Concepto "Soft Cyber": mucho aire, limpio, cálido.
 */

const BRAND = {
  rose: '#F7D1CD',
  brown: '#5E503F',
  cream: '#FDFBF7',
  roseSoft: '#FBE9E7',
  brownLight: '#8B7A67',
};

// --- Datos -----------------------------------------------------------------
const PREVIEW_SECTIONS = [
  {
    title: 'Un agente de ventas personalizado',
    text: 'Atiende a tus clientes 24/7 con un tono alineado a tu marca y procesos. La cercanía humana, multiplicada por la disponibilidad de la tecnología.',
    image: '/gloma/preview1.png',
    reverse: false,
  },
  {
    title: 'Aumenta ventas con campañas por WhatsApp',
    text: 'Envía campañas segmentadas, con plantillas aprobadas y seguimiento automático. Convierte conversaciones en pedidos confirmados.',
    image: '/gloma/preview2.png',
    reverse: true,
  },
  {
    title: 'Reduce 80% del tiempo en servicio al cliente',
    text: 'Nuestros bots actúan como un primer filtro inteligente, resolviendo lo repetitivo y escalando a un humano solo cuando hace falta.',
    image: '/gloma/preview3.png',
    reverse: false,
  },
];

const FEATURES = [
  {
    icon: '/gloma/ld_personaliza.png',
    title: 'Personalizado al ADN de tu marca',
    text: 'Configuramos el tono, las respuestas y los flujos para que cada mensaje sea indistinguible del de tu equipo.',
  },
  {
    icon: '/gloma/ld_inegraciones.png',
    title: 'Integraciones fluidas',
    text: 'Se conecta con tus fuentes de información y tu operación para que el sistema y tu equipo trabajen en sintonía.',
  },
  {
    icon: '/gloma/ld_contexto.png',
    title: 'Contexto a priori de tu empresa',
    text: 'El agente conoce tu catálogo, políticas y procesos antes de hablar con el primer cliente.',
  },
  {
    icon: '/gloma/ld_escalamiento.png',
    title: 'Escalamiento a agentes humanos',
    text: 'Cuando la conversación lo requiere, la derivamos a tu equipo con todo el contexto listo.',
  },
  {
    icon: '/gloma/ld_medicion.png',
    title: 'Medición y mejora continua',
    text: 'Tableros claros de conversiones, tiempos y satisfacción para seguir afinando la operación.',
  },
  {
    icon: '/gloma/ld_soporte.png',
    title: 'Equipo de soporte dedicado',
    text: 'Un equipo disponible para atender requerimientos, ajustes de flujos y nuevos casos de uso.',
  },
];

const STATS = [
  {
    icon: '/gloma/ld_mensajes_enviados.png',
    value: 150000,
    prefix: '+',
    suffix: '',
    label: 'mensajes enviados',
  },
  {
    icon: '/gloma/ld_4meses.png',
    value: 4,
    prefix: '',
    suffix: ' meses',
    label: 'retorno de inversión promedio',
  },
  {
    icon: '/gloma/ld_horasai.png',
    value: 10000,
    prefix: '+',
    suffix: '',
    label: 'horas de asesores AI operando',
  },
];

const WHATSAPP_URL =
  'https://wa.me/573003187871?text=Hola%20Gloma%2C%20quiero%20más%20información';

/**
 * Scroll suave hacia la sección de contacto con un easing más agradable que
 * el `scroll-behavior: smooth` nativo, que en Chrome se siente plano.
 * Animación 1s con cubic ease-in-out + un pequeño offset para que el título
 * no quede pegado al borde superior.
 */
function smoothScrollToContacto(e: React.MouseEvent<HTMLAnchorElement>) {
  e.preventDefault();
  if (typeof window === 'undefined') return;
  const el = document.getElementById('contacto');
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
    { size: 260, top: '10%', left: '8%', bg: BRAND.rose, factor: 40, opacity: 0.6 },
    { size: 160, top: '60%', left: '18%', bg: BRAND.roseSoft, factor: 30, opacity: 0.5 },
    { size: 320, top: '20%', right: '6%', bg: BRAND.rose, factor: 55, opacity: 0.35 },
    { size: 120, top: '70%', right: '24%', bg: BRAND.roseSoft, factor: 22, opacity: 0.55 },
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
              'linear-gradient(to right, rgba(94,80,63,0.62), rgba(94,80,63,0.15))',
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
            <stop offset="0%" stopColor={BRAND.rose} stopOpacity="0.7" />
            <stop offset="100%" stopColor={BRAND.rose} stopOpacity="0" />
          </linearGradient>
        </defs>
        <g fill="none" stroke="url(#lineGrad)" strokeWidth="1.3">
          <path d="M 80,160 C 240,120 380,280 520,220" />
          <path d="M 160,620 C 360,520 520,680 760,560" />
          <path d="M 900,140 C 1020,220 1120,380 1040,540" />
        </g>
        <g fill={BRAND.rose}>
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
        <a
          href="#contacto"
          onClick={smoothScrollToContacto}
          className="hidden md:inline-block px-5 py-2 rounded-full text-sm font-medium transition-opacity hover:opacity-90"
          style={{ backgroundColor: BRAND.rose, color: BRAND.brown }}
        >
          Agenda una demo
        </a>
      </nav>

      {/* Contenido principal (título + subtítulo + CTAs) */}
      <div
        ref={heroRef}
        className="relative z-10 max-w-6xl mx-auto px-6 md:px-10 py-24 md:py-36"
      >
        <h1
          className="text-white text-4xl md:text-6xl lg:text-7xl leading-tight max-w-3xl"
          style={{
            fontFamily: 'Syne, system-ui, sans-serif',
            fontWeight: 800,
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease, transform 900ms cubic-bezier(.22,.61,.36,1)',
          }}
        >
          Tecnología que resalta tu catálogo
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
          La forma elegante de automatizar ventas sin perder el trato humano.
        </p>
        <div
          className="mt-10 flex flex-col sm:flex-row gap-3"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 300ms, transform 900ms cubic-bezier(.22,.61,.36,1) 300ms',
          }}
        >
          <a
            href={WHATSAPP_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center transition-opacity hover:opacity-90"
            style={{ backgroundColor: BRAND.rose, color: BRAND.brown }}
          >
            Escríbenos por WhatsApp
          </a>
          <a
            href="#contacto"
            onClick={smoothScrollToContacto}
            className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center border-2 border-white/80 text-white hover:bg-white/10 transition-colors"
          >
            Que te contactemos
          </a>
        </div>
      </div>
    </header>
  );
}

type FormStatus = 'idle' | 'sending' | 'ok' | 'error';

function ContactForm({
  form,
  setForm,
  status,
  message,
  onSubmit,
}: {
  form: { email: string; telefono: string };
  setForm: (f: { email: string; telefono: string }) => void;
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
        boxShadow: `0 0 0 0 ${BRAND.rose}`,
        animation: 'glomaRing 1.4s ease-out infinite',
      }
    : isError
    ? { boxShadow: `0 0 0 3px ${BRAND.rose}` }
    : {};

  return (
    <>
      <style jsx global>{`
        @keyframes glomaRing {
          0%   { box-shadow: 0 0 0 0 rgba(247,209,205,0.95); }
          70%  { box-shadow: 0 0 0 14px rgba(247,209,205,0); }
          100% { box-shadow: 0 0 0 0 rgba(247,209,205,0); }
        }
        @keyframes glomaCheckDraw {
          to { stroke-dashoffset: 0; }
        }
        @keyframes glomaThanksFloat {
          0%   { opacity: 0; transform: translateY(8px); }
          100% { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div
        className="relative bg-white rounded-3xl shadow-md overflow-hidden transition-transform duration-500"
        style={{
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
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.brown }}>
            Correo electrónico
          </label>
          <input
            type="email"
            required
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            placeholder="tu@empresa.com"
            disabled={isSending}
            className="w-full px-4 py-3 border rounded-xl text-sm mb-5 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              borderColor: BRAND.roseSoft,
              color: BRAND.brown,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          />
          <label className="block text-sm font-medium mb-2" style={{ color: BRAND.brown }}>
            Teléfono
          </label>
          <input
            type="tel"
            required
            value={form.telefono}
            onChange={(e) => setForm({ ...form, telefono: e.target.value })}
            placeholder="+57 300 000 0000"
            disabled={isSending}
            className="w-full px-4 py-3 border rounded-xl text-sm mb-6 focus:outline-none transition-colors disabled:opacity-60"
            style={{
              borderColor: BRAND.roseSoft,
              color: BRAND.brown,
              fontFamily: 'Inter, system-ui, sans-serif',
            }}
          />
          <button
            type="submit"
            disabled={isSending}
            className="w-full py-3 rounded-full font-semibold text-sm transition-all hover:opacity-90 disabled:opacity-70 disabled:cursor-not-allowed"
            style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
          >
            {isSending ? 'Enviando…' : 'Hablar con un especialista'}
          </button>
          {isError && message && (
            <p
              className="mt-4 text-sm text-center"
              style={{
                color: BRAND.brown,
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
            style={{ backgroundColor: '#FFFFFF' }}
            role="status"
            aria-live="polite"
          >
            <div
              className="w-20 h-20 rounded-full flex items-center justify-center mb-5"
              style={{
                backgroundColor: BRAND.roseSoft,
                animation: 'glomaThanksFloat 500ms ease-out both',
              }}
            >
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                <circle
                  cx="20"
                  cy="20"
                  r="18"
                  stroke={BRAND.rose}
                  strokeWidth="2"
                  fill="none"
                />
                <path
                  d="M12 20.5 L18 26.5 L29 14.5"
                  stroke={BRAND.brown}
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
                color: BRAND.brown,
                animation: 'glomaThanksFloat 500ms ease-out 250ms both',
              }}
            >
              Mensaje recibido
            </h3>
            <p
              className="text-sm md:text-base"
              style={{
                fontFamily: 'Inter, system-ui, sans-serif',
                color: BRAND.brownLight,
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
      className="py-20 md:py-24"
      style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
    >
      <div className="max-w-5xl mx-auto px-6 md:px-10">
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
                style={{ backgroundColor: BRAND.rose }}
              >
                <Image
                  src={s.icon}
                  alt=""
                  width={80}
                  height={80}
                  className="object-contain"
                />
              </div>
              <div
                className="text-4xl md:text-5xl mb-2 tabular-nums"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 800,
                  color: BRAND.rose,
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

// --- Página ----------------------------------------------------------------

export default function GlomaLanding() {
  const [form, setForm] = useState({ email: '', telefono: '' });
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
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      setStatus('ok');
      setMessage('¡Gracias! Te contactaremos muy pronto.');
      setForm({ email: '', telefono: '' });
    } catch (err: any) {
      setStatus('error');
      setMessage(err.message || 'No pudimos enviar tu mensaje. Intenta de nuevo.');
    }
  };

  return (
    <>
      <Head>
        <title>Gloma — Tecnología que resalta tu catálogo</title>
        <meta
          name="description"
          content="Gloma: la forma elegante de automatizar ventas por WhatsApp sin perder el trato humano."
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </Head>

      <div
        className="gloma-root min-h-screen"
        style={{ backgroundColor: BRAND.cream, color: BRAND.brown }}
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
                      color: BRAND.brown,
                    }}
                  >
                    {s.title}
                  </h2>
                  <p
                    className="text-base md:text-lg leading-relaxed"
                    style={{
                      fontFamily: 'Inter, system-ui, sans-serif',
                      color: BRAND.brownLight,
                    }}
                  >
                    {s.text}
                  </p>
                </div>
                <div className="md:[direction:ltr]">
                  <div className="relative aspect-[4/3] rounded-3xl overflow-hidden shadow-lg">
                    <Image src={s.image} alt={s.title} fill className="object-cover" />
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </section>

        {/* ===== FEATURES ===== */}
        <section className="py-20 md:py-28" style={{ backgroundColor: '#FFFFFF' }}>
          <div className="max-w-6xl mx-auto px-6 md:px-10">
            <Reveal className="text-center max-w-2xl mx-auto mb-14 md:mb-20">
              <h2
                className="text-3xl md:text-5xl leading-tight"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 700,
                  color: BRAND.brown,
                }}
              >
                Todo lo que necesitas, sin fricciones
              </h2>
            </Reveal>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8 md:gap-10">
              {FEATURES.map((f, i) => (
                <Reveal key={f.title} delay={i * 80}>
                  <div
                    className="p-6 md:p-7 rounded-2xl transition-transform hover:-translate-y-1 h-full"
                    style={{ backgroundColor: BRAND.cream }}
                  >
                    <div
                      className="w-14 h-14 rounded-full flex items-center justify-center mb-4 overflow-hidden"
                      style={{ backgroundColor: BRAND.roseSoft }}
                    >
                      <Image
                        src={f.icon}
                        alt=""
                        width={56}
                        height={56}
                        className="object-contain"
                      />
                    </div>
                    <h3
                      className="text-lg md:text-xl mb-2"
                      style={{
                        fontFamily: 'Syne, system-ui, sans-serif',
                        fontWeight: 600,
                        color: BRAND.brown,
                      }}
                    >
                      {f.title}
                    </h3>
                    <p
                      className="text-sm leading-relaxed"
                      style={{
                        fontFamily: 'Inter, system-ui, sans-serif',
                        color: BRAND.brownLight,
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

        {/* ===== STATS con contador animado ===== */}
        <StatsSection />

        {/* ===== CONTACTO ===== */}
        <section id="contacto" className="py-20 md:py-28" style={{ backgroundColor: BRAND.cream }}>
          <div className="max-w-5xl mx-auto px-6 md:px-10 grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-16 items-start">
            <Reveal>
              <h2
                className="text-3xl md:text-5xl mb-6 leading-tight"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 700,
                  color: BRAND.brown,
                }}
              >
                ¿Listo para escalar tus ventas sin ampliar tu equipo?
              </h2>
              <p
                className="text-base md:text-lg mb-8"
                style={{
                  fontFamily: 'Inter, system-ui, sans-serif',
                  color: BRAND.brownLight,
                }}
              >
                Cuéntanos un poco de tu negocio y te contactamos para mostrarte cómo Gloma puede funcionar para ti.
              </p>
              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center px-5 py-3 rounded-full text-sm font-semibold transition-transform hover:-translate-y-0.5"
                style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
              >
                Escríbenos por WhatsApp
              </a>
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
        <footer style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}>
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
                className="text-sm font-semibold mb-4 tracking-wide uppercase opacity-80"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                Contacto
              </h4>
              <ul
                className="space-y-2 text-sm opacity-80"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                <li>contacto@glomabeauty.com</li>
                <li>+57 300 318 7871</li>
                <li>Calle 36, Vía Jamundí #128-321, Cali, Valle del Cauca</li>
              </ul>
            </div>
            <div>
              <h4
                className="text-sm font-semibold mb-4 tracking-wide uppercase opacity-80"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                Conecta
              </h4>
              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm opacity-80 hover:opacity-100"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                WhatsApp →
              </a>
            </div>
          </div>
          <div
            className="border-t border-white/10 py-5 text-center text-xs opacity-60"
            style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
          >
            © 2026 Gloma.
          </div>
        </footer>
      </div>
    </>
  );
}
