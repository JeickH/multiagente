import Head from 'next/head';
import { useEffect, useRef, useState } from 'react';

/**
 * Landing page de GORVEK — agentes autónomos de IA para automatización
 * de procesos corporativos complejos.
 *
 * Identidad (identidad_gorvek/brief.md):
 *  - Paleta: Deep Forest #004D40, Algorithmic Mint #4DB6AC, Soft Mint #E0F2F1,
 *    Technical Black #101817.
 *  - Tipografía: Urbanist (headlines) + Inter (body/UI).
 *  - Arquetipo: El Gobernante. Estructurado, premium, enterprise-grade.
 *  - Cards: rgba(255,255,255,0.03) con border rgba(77,182,172,0.15), radius máx 8px.
 *  - Acento (#4DB6AC) sólo para CTAs, hover, métricas y highlights.
 *
 * Nota: el WhatsApp / email / teléfono se reutilizan de Gloma como placeholder
 * mientras Gorvek no tenga sus propios canales de contacto.
 */

const BRAND = {
  bgBase: '#101817',
  bgAlt: '#0B1413',
  forest: '#004D40',
  mint: '#4DB6AC',
  softMint: '#E0F2F1',
  cardBg: 'rgba(255,255,255,0.03)',
  cardBorder: 'rgba(77,182,172,0.15)',
  cardBorderHover: 'rgba(77,182,172,0.45)',
  text: '#E6EFEE',
  textMuted: 'rgba(230,239,238,0.65)',
  textDim: 'rgba(230,239,238,0.45)',
};

const FONT_HEAD = 'Urbanist, system-ui, sans-serif';
const FONT_BODY = 'Inter, system-ui, sans-serif';

const WHATSAPP_URL =
  'https://wa.me/573003187871?text=Hola%20Gorvek%2C%20me%20gustar%C3%ADa%20hablar%20con%20un%20experto';

// --- Datos -----------------------------------------------------------------

const VALUE_PROPS = [
  {
    title: 'Automatice procesos complejos de extremo a extremo',
    text: 'Agentes que ejecutan workflows completos, no solo tareas aisladas.',
  },
  {
    title: 'Coordine sistemas y equipos con inteligencia operativa',
    text: 'Orqueste múltiples plataformas, reglas y actores desde una sola capa autónoma.',
  },
  {
    title: 'Escale operaciones sin perder control',
    text: 'Mantenga trazabilidad, gobernanza y precisión incluso en procesos críticos.',
  },
];

const STEPS = [
  {
    n: '01',
    title: 'Mapeo Operativo',
    text: 'Analizamos procesos, reglas de negocio y dependencias.',
  },
  {
    n: '02',
    title: 'Diseño de Agentes',
    text: 'Arquitectura de agentes adaptada a su operación.',
  },
  {
    n: '03',
    title: 'Integración de Sistemas',
    text: 'Conectamos infraestructura existente.',
  },
  {
    n: '04',
    title: 'Despliegue y Optimización',
    text: 'Activación progresiva con monitoreo continuo.',
  },
  {
    n: '05',
    title: 'Soporte y Acompañamiento',
    text: 'Acompañamos su operación después del despliegue, ajustando agentes según resultados y nuevos requerimientos.',
  },
];

const METRICS = [
  { value: '+70%', label: 'Reducción promedio en tiempo operativo manual' },
  { value: '24/7', label: 'Ejecución continua sin interrupciones' },
  { value: '100%', label: 'Trazabilidad de decisiones y acciones' },
  { value: 'Enterprise-Grade', label: 'Arquitectura diseñada para operaciones críticas' },
];

const USE_CASES = [
  {
    title: 'Operaciones Financieras',
    text: 'Conciliaciones, validaciones, procesamiento documental.',
  },
  {
    title: 'Supply Chain & Logística',
    text: 'Orquestación de inventarios, órdenes y excepciones.',
  },
  {
    title: 'Backoffice Corporativo',
    text: 'Automatización de procesos internos multi-departamento.',
  },
  {
    title: 'Customer Operations',
    text: 'Flujos complejos de atención, soporte y resolución.',
  },
];

// --- Hooks -----------------------------------------------------------------

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

function smoothScrollTo(id: string) {
  return (e: React.MouseEvent<HTMLAnchorElement>) => {
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
  };
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

function Wordmark({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const px = size === 'sm' ? 18 : size === 'lg' ? 30 : 22;
  return (
    <span
      className="inline-flex items-center gap-2 select-none"
      aria-label="Gorvek"
      style={{ fontFamily: FONT_HEAD }}
    >
      <span
        aria-hidden="true"
        style={{
          width: px * 0.8,
          height: px * 0.8,
          borderRadius: 2,
          background: `linear-gradient(135deg, ${BRAND.mint}, ${BRAND.forest})`,
          boxShadow: `0 0 24px rgba(77,182,172,0.35)`,
          display: 'inline-block',
        }}
      />
      <span
        style={{
          fontSize: px,
          fontWeight: 800,
          letterSpacing: '0.18em',
          color: BRAND.text,
        }}
      >
        GORVEK
      </span>
    </span>
  );
}

/**
 * Fondo SVG abstracto de red neuronal: nodos + líneas con drift sutil.
 * Vive detrás del hero. Se desplaza suavemente con el cursor para dar
 * sensación enterprise / control room.
 */
function NetworkBackground({ offset }: { offset: { x: number; y: number } }) {
  const nodes = [
    { x: 120, y: 140 },
    { x: 320, y: 90 },
    { x: 520, y: 200 },
    { x: 760, y: 110 },
    { x: 1020, y: 220 },
    { x: 200, y: 380 },
    { x: 460, y: 460 },
    { x: 720, y: 380 },
    { x: 980, y: 460 },
    { x: 340, y: 640 },
    { x: 620, y: 700 },
    { x: 880, y: 640 },
  ];
  const links: [number, number][] = [
    [0, 1], [1, 2], [2, 3], [3, 4],
    [0, 5], [1, 6], [2, 6], [3, 7], [4, 8],
    [5, 6], [6, 7], [7, 8],
    [5, 9], [6, 10], [7, 10], [8, 11],
    [9, 10], [10, 11],
  ];
  return (
    <svg
      viewBox="0 0 1200 800"
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden="true"
      style={{
        transform: `translate3d(${offset.x * -18}px, ${offset.y * -18}px, 0)`,
        transition: 'transform 600ms cubic-bezier(.22,.61,.36,1)',
      }}
    >
      <defs>
        <radialGradient id="gorvekGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={BRAND.mint} stopOpacity="0.25" />
          <stop offset="100%" stopColor={BRAND.mint} stopOpacity="0" />
        </radialGradient>
        <linearGradient id="gorvekLink" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={BRAND.mint} stopOpacity="0.55" />
          <stop offset="100%" stopColor={BRAND.mint} stopOpacity="0.05" />
        </linearGradient>
      </defs>

      <circle cx="900" cy="180" r="320" fill="url(#gorvekGlow)" />
      <circle cx="280" cy="600" r="280" fill="url(#gorvekGlow)" />

      <g stroke="url(#gorvekLink)" strokeWidth="1">
        {links.map(([a, b], i) => (
          <line
            key={i}
            x1={nodes[a].x}
            y1={nodes[a].y}
            x2={nodes[b].x}
            y2={nodes[b].y}
          />
        ))}
      </g>
      <g fill={BRAND.mint}>
        {nodes.map((n, i) => (
          <g key={i}>
            <circle
              cx={n.x}
              cy={n.y}
              r="2.4"
              opacity="0.95"
              style={{
                animation: `gorvekPulse 3.6s ease-in-out ${(i % 6) * 0.4}s infinite`,
                transformOrigin: `${n.x}px ${n.y}px`,
              }}
            />
            <circle cx={n.x} cy={n.y} r="6" opacity="0.12" />
          </g>
        ))}
      </g>
    </svg>
  );
}

function Hero() {
  const heroRef = useRef<HTMLDivElement>(null);
  const { ref: contentRef, inView } = useInView<HTMLDivElement>('0px');
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const el = heroRef.current;
    if (!el) return;
    let raf = 0;
    const handle = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
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
      ref={heroRef}
      className="relative w-full overflow-hidden"
      style={{ minHeight: '100vh', backgroundColor: BRAND.bgBase }}
    >
      <NetworkBackground offset={offset} />

      {/* Vignette + grain sutil */}
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.55) 100%)',
        }}
      />

      {/* Nav */}
      <nav className="relative z-10 flex items-center justify-between max-w-6xl mx-auto px-6 md:px-10 pt-7">
        <Wordmark size="md" />
        <a
          href="#contacto"
          onClick={smoothScrollTo('contacto')}
          className="gorvek-cta-primary inline-flex items-center px-5 py-2.5 text-sm font-semibold transition-all"
          style={{
            fontFamily: FONT_BODY,
            borderRadius: 6,
            backgroundColor: BRAND.mint,
            color: BRAND.bgBase,
          }}
        >
          Hablar con un experto
        </a>
      </nav>

      {/* Contenido */}
      <div
        ref={contentRef}
        className="relative z-10 max-w-4xl mx-auto px-6 md:px-10 py-32 md:py-44 text-center"
      >
        <h1
          className="text-4xl md:text-6xl lg:text-7xl leading-[1.05] mb-8"
          style={{
            fontFamily: FONT_HEAD,
            fontWeight: 700,
            color: BRAND.text,
            letterSpacing: '-0.02em',
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 100ms, transform 900ms cubic-bezier(.22,.61,.36,1) 100ms',
          }}
        >
          Inteligencia autónoma para{' '}
          <span style={{ color: BRAND.mint }}>operaciones empresariales</span> complejas.
        </h1>

        <p
          className="text-base md:text-lg max-w-2xl mx-auto mb-12"
          style={{
            fontFamily: FONT_BODY,
            color: BRAND.textMuted,
            lineHeight: 1.7,
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 200ms, transform 900ms cubic-bezier(.22,.61,.36,1) 200ms',
          }}
        >
          Delegue procesos críticos a agentes de IA diseñados para ejecutar, coordinar y optimizar operaciones con precisión empresarial.
        </p>

        <div
          className="flex justify-center"
          style={{
            opacity: inView ? 1 : 0,
            transform: inView ? 'translateY(0)' : 'translateY(20px)',
            transition: 'opacity 900ms ease 300ms, transform 900ms cubic-bezier(.22,.61,.36,1) 300ms',
          }}
        >
          <a
            href="#contacto"
            onClick={smoothScrollTo('contacto')}
            className="gorvek-cta-primary inline-flex items-center justify-center px-7 py-3.5 text-sm font-semibold transition-all"
            style={{
              fontFamily: FONT_BODY,
              backgroundColor: BRAND.mint,
              color: BRAND.bgBase,
              borderRadius: 6,
            }}
          >
            Hablar con un experto
          </a>
        </div>
      </div>
    </header>
  );
}

function SectionHeading({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <Reveal className="max-w-3xl mx-auto text-center mb-16 md:mb-20">
      <h2
        className="text-3xl md:text-5xl leading-[1.1]"
        style={{
          fontFamily: FONT_HEAD,
          fontWeight: 700,
          color: BRAND.text,
          letterSpacing: '-0.02em',
        }}
      >
        {title}
      </h2>
      {subtitle && (
        <p
          className="text-base md:text-lg mt-6"
          style={{ fontFamily: FONT_BODY, color: BRAND.textMuted, lineHeight: 1.7 }}
        >
          {subtitle}
        </p>
      )}
    </Reveal>
  );
}

function ValuePropSection() {
  return (
    <section
      className="py-24 md:py-32"
      style={{ backgroundColor: BRAND.bgBase }}
    >
      <div className="max-w-6xl mx-auto px-6 md:px-10">
        <SectionHeading title="Infraestructura autónoma diseñada para negocio real" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {VALUE_PROPS.map((v, i) => (
            <Reveal key={v.title} delay={i * 100}>
              <div
                className="gorvek-card p-7 h-full"
                style={{
                  backgroundColor: BRAND.cardBg,
                  border: `1px solid ${BRAND.cardBorder}`,
                  borderRadius: 8,
                  transition: 'border-color 300ms ease, box-shadow 300ms ease, transform 300ms ease',
                }}
              >
                <div
                  className="mb-5"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 4,
                    border: `1px solid ${BRAND.cardBorderHover}`,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <span
                    style={{
                      fontFamily: FONT_HEAD,
                      fontWeight: 700,
                      fontSize: 13,
                      color: BRAND.mint,
                    }}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </span>
                </div>
                <h3
                  className="text-lg md:text-xl mb-3"
                  style={{
                    fontFamily: FONT_HEAD,
                    fontWeight: 600,
                    color: BRAND.text,
                    letterSpacing: '-0.01em',
                  }}
                >
                  {v.title}
                </h3>
                <p
                  className="text-sm leading-relaxed"
                  style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}
                >
                  {v.text}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorksSection() {
  return (
    <section
      id="proceso"
      className="py-24 md:py-32"
      style={{ backgroundColor: BRAND.bgBase }}
    >
      <div className="max-w-6xl mx-auto px-6 md:px-10">
        <SectionHeading title="Implementación estructurada para operaciones críticas" />
        <div className="relative">
          {/* Línea horizontal en desktop (solo cuando los 5 pasos van en una sola fila) */}
          <div
            className="hidden lg:block absolute left-0 right-0"
            style={{
              top: 24,
              height: 1,
              background: `linear-gradient(to right, transparent 0%, ${BRAND.cardBorderHover} 15%, ${BRAND.cardBorderHover} 85%, transparent 100%)`,
            }}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-8">
            {STEPS.map((s, i) => (
              <Reveal key={s.n} delay={i * 120}>
                <div className="relative">
                  <div
                    className="relative mx-auto lg:mx-0 flex items-center justify-center mb-5"
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: 999,
                      backgroundColor: BRAND.bgBase,
                      border: `1px solid ${BRAND.mint}`,
                      boxShadow: `0 0 24px rgba(77,182,172,0.25)`,
                      fontFamily: FONT_HEAD,
                      fontWeight: 700,
                      color: BRAND.mint,
                      fontSize: 14,
                    }}
                  >
                    {s.n}
                  </div>
                  <h3
                    className="text-lg md:text-xl mb-2 text-center lg:text-left"
                    style={{
                      fontFamily: FONT_HEAD,
                      fontWeight: 600,
                      color: BRAND.text,
                      letterSpacing: '-0.01em',
                    }}
                  >
                    {s.title}
                  </h3>
                  <p
                    className="text-sm leading-relaxed text-center lg:text-left"
                    style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}
                  >
                    {s.text}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricsSection() {
  return (
    <section
      className="py-24 md:py-28 relative overflow-hidden"
      style={{
        background: `linear-gradient(180deg, ${BRAND.bgAlt} 0%, ${BRAND.bgBase} 100%)`,
      }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(circle at 50% 0%, rgba(77,182,172,0.10), transparent 60%)`,
        }}
      />
      <div className="relative max-w-6xl mx-auto px-6 md:px-10">
        <SectionHeading title="Resultados medibles en operaciones empresariales" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {METRICS.map((m, i) => (
            <Reveal key={m.label} delay={i * 100}>
              <div
                className="p-7 h-full text-center"
                style={{
                  backgroundColor: BRAND.cardBg,
                  border: `1px solid ${BRAND.cardBorder}`,
                  borderRadius: 8,
                }}
              >
                <div
                  className="mb-3"
                  style={{
                    fontFamily: FONT_HEAD,
                    fontWeight: 800,
                    color: BRAND.mint,
                    fontSize: m.value.length > 8 ? 24 : 40,
                    letterSpacing: '-0.02em',
                    lineHeight: 1.1,
                  }}
                >
                  {m.value}
                </div>
                <div
                  className="text-sm leading-relaxed"
                  style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}
                >
                  {m.label}
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function UseCasesSection() {
  return (
    <section
      id="casos"
      className="py-24 md:py-32"
      style={{ backgroundColor: BRAND.bgAlt }}
    >
      <div className="max-w-6xl mx-auto px-6 md:px-10">
        <SectionHeading title="Aplicaciones para operaciones de alta complejidad" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {USE_CASES.map((u, i) => (
            <Reveal key={u.title} delay={i * 100}>
              <div
                className="gorvek-card p-8 h-full flex items-start gap-5"
                style={{
                  backgroundColor: BRAND.cardBg,
                  border: `1px solid ${BRAND.cardBorder}`,
                  borderRadius: 8,
                  transition: 'border-color 300ms ease, box-shadow 300ms ease, transform 300ms ease',
                }}
              >
                <div
                  className="flex-shrink-0 flex items-center justify-center"
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 4,
                    border: `1px solid ${BRAND.cardBorderHover}`,
                    color: BRAND.mint,
                  }}
                >
                  <UseCaseIcon index={i} />
                </div>
                <div>
                  <h3
                    className="text-lg md:text-xl mb-2"
                    style={{
                      fontFamily: FONT_HEAD,
                      fontWeight: 600,
                      color: BRAND.text,
                      letterSpacing: '-0.01em',
                    }}
                  >
                    {u.title}
                  </h3>
                  <p
                    className="text-sm leading-relaxed"
                    style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}
                  >
                    {u.text}
                  </p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function UseCaseIcon({ index }: { index: number }) {
  const stroke = BRAND.mint;
  const sw = 1.5;
  switch (index) {
    case 0:
      return (
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <rect x="3" y="5" width="16" height="12" rx="1" stroke={stroke} strokeWidth={sw} />
          <path d="M3 9 H19" stroke={stroke} strokeWidth={sw} />
          <path d="M7 13 H11" stroke={stroke} strokeWidth={sw} strokeLinecap="round" />
        </svg>
      );
    case 1:
      return (
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <path d="M3 17 V8 L11 4 L19 8 V17" stroke={stroke} strokeWidth={sw} strokeLinejoin="round" />
          <path d="M7 17 V12 H15 V17" stroke={stroke} strokeWidth={sw} strokeLinejoin="round" />
        </svg>
      );
    case 2:
      return (
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <rect x="3" y="3" width="7" height="7" stroke={stroke} strokeWidth={sw} />
          <rect x="12" y="3" width="7" height="7" stroke={stroke} strokeWidth={sw} />
          <rect x="3" y="12" width="7" height="7" stroke={stroke} strokeWidth={sw} />
          <rect x="12" y="12" width="7" height="7" stroke={stroke} strokeWidth={sw} />
        </svg>
      );
    case 3:
      return (
        <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
          <circle cx="11" cy="9" r="4" stroke={stroke} strokeWidth={sw} />
          <path d="M3 19 C 3 14 19 14 19 19" stroke={stroke} strokeWidth={sw} strokeLinecap="round" />
        </svg>
      );
    default:
      return null;
  }
}

type FormStatus = 'idle' | 'sending' | 'ok' | 'error';

function FinalCTASection({
  form,
  setForm,
  status,
  message,
  onSubmit,
}: {
  form: { email: string; telefono: string; empresa: string };
  setForm: (f: { email: string; telefono: string; empresa: string }) => void;
  status: FormStatus;
  message: string;
  onSubmit: (e: React.FormEvent) => void;
}) {
  const isSending = status === 'sending';
  const isDone = status === 'ok';
  const isError = status === 'error';

  return (
    <section
      id="contacto"
      className="py-24 md:py-32 relative overflow-hidden"
      style={{ backgroundColor: BRAND.bgBase }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(ellipse at 50% 100%, rgba(0,77,64,0.30), transparent 60%)`,
        }}
      />
      <div className="relative max-w-5xl mx-auto px-6 md:px-10 grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
        <Reveal>
          <h2
            className="text-3xl md:text-5xl mb-6 leading-[1.1]"
            style={{
              fontFamily: FONT_HEAD,
              fontWeight: 700,
              color: BRAND.text,
              letterSpacing: '-0.02em',
            }}
          >
            Conversemos sobre los procesos que puede delegar a un agente.
          </h2>
          <p
            className="text-base md:text-lg mb-8"
            style={{ fontFamily: FONT_BODY, color: BRAND.textMuted, lineHeight: 1.7 }}
          >
            Cuéntenos brevemente cómo opera su empresa y le mostramos qué tareas pueden ejecutarse de forma autónoma — sin reemplazar las herramientas que ya usa.
          </p>
          <a
            href={WHATSAPP_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-5 py-3 text-sm font-semibold transition-all hover:bg-white/5"
            style={{
              fontFamily: FONT_BODY,
              color: BRAND.text,
              border: `1px solid ${BRAND.cardBorder}`,
              borderRadius: 6,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7 H12 M8 3 L12 7 L8 11" stroke={BRAND.mint} strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            O contáctenos por WhatsApp
          </a>
        </Reveal>

        <Reveal delay={120}>
          <div
            className="relative"
            style={{
              backgroundColor: BRAND.cardBg,
              border: `1px solid ${BRAND.cardBorder}`,
              borderRadius: 8,
              backdropFilter: 'blur(8px)',
            }}
          >
            <form
              onSubmit={onSubmit}
              aria-hidden={isDone}
              className="p-7 md:p-8 transition-all duration-500"
              style={{
                opacity: isDone ? 0 : 1,
                transform: isDone ? 'translateY(-8px)' : 'translateY(0)',
                pointerEvents: isDone ? 'none' : 'auto',
              }}
            >
              <Field
                label="Empresa"
                value={form.empresa}
                onChange={(v) => setForm({ ...form, empresa: v })}
                placeholder="Nombre de la organización"
                disabled={isSending}
              />
              <Field
                label="Correo corporativo"
                type="email"
                value={form.email}
                onChange={(v) => setForm({ ...form, email: v })}
                placeholder="usted@empresa.com"
                disabled={isSending}
              />
              <Field
                label="Teléfono"
                type="tel"
                value={form.telefono}
                onChange={(v) => setForm({ ...form, telefono: v })}
                placeholder="+57 300 000 0000"
                disabled={isSending}
              />
              <button
                type="submit"
                disabled={isSending}
                className="gorvek-cta-primary w-full py-3 mt-2 font-semibold text-sm transition-all disabled:opacity-70 disabled:cursor-not-allowed"
                style={{
                  fontFamily: FONT_BODY,
                  backgroundColor: BRAND.mint,
                  color: BRAND.bgBase,
                  borderRadius: 6,
                }}
              >
                {isSending ? 'Enviando…' : 'Hablar con un experto'}
              </button>
              {isError && message && (
                <p
                  className="mt-4 text-sm text-center"
                  style={{ color: BRAND.textMuted, fontFamily: FONT_BODY }}
                >
                  {message}
                </p>
              )}
            </form>

            {isDone && (
              <div
                className="absolute inset-0 flex flex-col items-center justify-center px-6 md:px-8 text-center"
                style={{
                  backgroundColor: BRAND.cardBg,
                  borderRadius: 8,
                }}
                role="status"
                aria-live="polite"
              >
                <div
                  className="flex items-center justify-center mb-5"
                  style={{
                    width: 64,
                    height: 64,
                    borderRadius: 999,
                    border: `1px solid ${BRAND.mint}`,
                    boxShadow: `0 0 32px rgba(77,182,172,0.35)`,
                  }}
                >
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                    <path
                      d="M7 14.5 L12 19.5 L21 9.5"
                      stroke={BRAND.mint}
                      strokeWidth="2"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      style={{
                        strokeDasharray: 30,
                        strokeDashoffset: 30,
                        animation: 'gorvekDraw 600ms ease-out 150ms forwards',
                      }}
                    />
                  </svg>
                </div>
                <h3
                  className="text-xl md:text-2xl mb-2"
                  style={{ fontFamily: FONT_HEAD, fontWeight: 700, color: BRAND.text }}
                >
                  Mensaje recibido
                </h3>
                <p
                  className="text-sm md:text-base"
                  style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}
                >
                  {message || 'Lo contactaremos para coordinar la conversación.'}
                </p>
              </div>
            )}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  disabled,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  disabled: boolean;
  type?: string;
}) {
  return (
    <div className="mb-5">
      <label
        className="block text-xs uppercase tracking-widest mb-2"
        style={{ color: BRAND.textDim, fontFamily: FONT_BODY }}
      >
        {label}
      </label>
      <input
        type={type}
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="gorvek-input w-full px-4 py-3 text-sm focus:outline-none transition-all disabled:opacity-60"
        style={{
          backgroundColor: 'rgba(255,255,255,0.02)',
          border: `1px solid ${BRAND.cardBorder}`,
          color: BRAND.text,
          borderRadius: 6,
          fontFamily: FONT_BODY,
        }}
      />
    </div>
  );
}

function Footer() {
  return (
    <footer style={{ backgroundColor: BRAND.bgAlt, borderTop: `1px solid ${BRAND.cardBorder}` }}>
      <div className="max-w-6xl mx-auto px-6 md:px-10 py-16 grid grid-cols-1 md:grid-cols-4 gap-10">
        <div className="md:col-span-2">
          <Wordmark size="md" />
          <p
            className="mt-5 text-sm max-w-sm"
            style={{ fontFamily: FONT_BODY, color: BRAND.textMuted, lineHeight: 1.7 }}
          >
            La infraestructura de IA para empresas que escalan.
          </p>
        </div>
        <div>
          <h4
            className="text-xs uppercase tracking-widest mb-4"
            style={{ color: BRAND.mint, fontFamily: FONT_BODY }}
          >
            Soluciones
          </h4>
          <ul className="space-y-2 text-sm" style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}>
            <li>
              <a href="#casos" onClick={smoothScrollTo('casos')} className="hover:text-white transition-colors">
                Casos de Uso
              </a>
            </li>
            <li>
              <a href="#proceso" onClick={smoothScrollTo('proceso')} className="hover:text-white transition-colors">
                Proceso
              </a>
            </li>
            <li>
              <a href="#contacto" onClick={smoothScrollTo('contacto')} className="hover:text-white transition-colors">
                Contacto
              </a>
            </li>
          </ul>
        </div>
        <div>
          <h4
            className="text-xs uppercase tracking-widest mb-4"
            style={{ color: BRAND.mint, fontFamily: FONT_BODY }}
          >
            Contacto
          </h4>
          <ul className="space-y-2 text-sm" style={{ fontFamily: FONT_BODY, color: BRAND.textMuted }}>
            <li>contacto@glomabeauty.com</li>
            <li>+57 300 318 7871</li>
            <li>
              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-white transition-colors"
              >
                WhatsApp →
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div
        className="border-t py-5 text-center text-xs"
        style={{
          borderColor: BRAND.cardBorder,
          color: BRAND.textDim,
          fontFamily: FONT_BODY,
        }}
      >
        © 2026 Gorvek. Inteligencia autónoma para operaciones complejas.
      </div>
    </footer>
  );
}

// --- Página ----------------------------------------------------------------

export default function GorvekLanding() {
  const [form, setForm] = useState({ email: '', telefono: '', empresa: '' });
  const [status, setStatus] = useState<FormStatus>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('sending');
    setMessage('');
    try {
      const res = await fetch('/api/landing/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, source: 'gorvek_landing' }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      setStatus('ok');
      setMessage('Lo contactaremos pronto para coordinar la conversación.');
      setForm({ email: '', telefono: '', empresa: '' });
    } catch (err: any) {
      setStatus('error');
      setMessage(err.message || 'No pudimos enviar su solicitud. Intente nuevamente.');
    }
  };

  return (
    <>
      <Head>
        <title>Gorvek — Inteligencia autónoma para operaciones empresariales</title>
        <meta
          name="description"
          content="Gorvek: agentes autónomos de IA para automatización de procesos corporativos complejos. Infraestructura enterprise-grade para operaciones críticas."
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Urbanist:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </Head>

      <style jsx global>{`
        .gorvek-root {
          background-color: ${BRAND.bgBase};
          color: ${BRAND.text};
          font-family: ${FONT_BODY};
        }
        .gorvek-root ::selection {
          background: ${BRAND.mint};
          color: ${BRAND.bgBase};
        }
        .gorvek-card:hover {
          border-color: ${BRAND.cardBorderHover} !important;
          box-shadow: 0 0 0 1px rgba(77,182,172,0.18), 0 24px 60px -20px rgba(0,0,0,0.55), 0 0 50px -20px rgba(77,182,172,0.35);
          transform: translateY(-2px);
        }
        .gorvek-cta-primary:hover {
          box-shadow: 0 0 0 1px rgba(77,182,172,0.5), 0 12px 32px -10px rgba(77,182,172,0.55);
          transform: translateY(-1px);
        }
        .gorvek-input:focus {
          border-color: ${BRAND.mint} !important;
          box-shadow: 0 0 0 3px rgba(77,182,172,0.18);
        }
        @keyframes gorvekPulse {
          0%, 100% { transform: scale(1); opacity: 0.95; }
          50%      { transform: scale(1.6); opacity: 0.55; }
        }
        @keyframes gorvekDraw {
          to { stroke-dashoffset: 0; }
        }
      `}</style>

      <div className="gorvek-root min-h-screen">
        <Hero />
        <ValuePropSection />
        <HowItWorksSection />
        <MetricsSection />
        <UseCasesSection />
        <FinalCTASection
          form={form}
          setForm={setForm}
          status={status}
          message={message}
          onSubmit={handleSubmit}
        />
        <Footer />
      </div>
    </>
  );
}
