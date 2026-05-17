import Head from 'next/head';
import Image from 'next/image';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Landing pública de ELECOL — electrolineras inteligentes con energía solar.
 *
 * Identidad "Infinito Eléctrico — Edición Mar + Sol"
 *  - #03045E azul profundo (fondo)
 *  - #0077B6 azul eléctrico (interactivos)
 *  - #00B4D8 cian solar (glow / gradientes)
 *  - #90E0EF azul cielo (detalles)
 *  - #CAF0F8 blanco espuma (texto secundario)
 *  - #FFC300 amarillo energía (CTAs, acentos solares)
 *
 * Referencias: Tesla Energy, Rivian, Apple, Stripe.
 * Sin libs nuevas — todo Tailwind + CSS + React puro.
 *
 * Brief en /Users/equipo/Downloads/ELECOL_Premium_Landing_Guide.md.
 * Assets viven en /public/elecol/ (ver public/elecol/README.md).
 */

const BRAND = {
  deep: '#03045E',
  electric: '#0077B6',
  cyan: '#00B4D8',
  sky: '#90E0EF',
  foam: '#CAF0F8',
  solar: '#FFC300',
};

const NAV_LINKS = [
  { href: '#tecnologia', label: 'Tecnología' },
  { href: '#infraestructura', label: 'Infraestructura' },
  { href: '#expansion', label: 'Expansión' },
  { href: '#roi', label: 'ROI' },
  { href: '#contacto', label: 'Contacto' },
];

// El generador escribe placeholders SVG para los assets no-SVG con sufijo
// `.placeholder.svg`. Cuando llegue el real, se quita ese sufijo.
function placeholder(path: string, real: boolean = false): string {
  // `real=true` significa: el archivo real ya está en disco con su nombre
  // canónico (no buscar .placeholder.svg). Útil para SVGs verdaderos.
  if (real) return path;
  return `${path}.placeholder.svg`;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

function useScrolled(threshold = 24): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > threshold);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [threshold]);
  return scrolled;
}

function useReveal<T extends HTMLElement>(rootMargin = '0px 0px -80px 0px') {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!('IntersectionObserver' in window)) {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setVisible(true);
            io.disconnect();
            return;
          }
        }
      },
      { rootMargin, threshold: 0.05 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [rootMargin]);
  return { ref, visible };
}

function useCountUp(target: number, durationMs = 1800) {
  const { ref, visible } = useReveal<HTMLSpanElement>();
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!visible) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [visible, target, durationMs]);
  return { ref, value };
}

// ---------------------------------------------------------------------------
// Componentes auxiliares
// ---------------------------------------------------------------------------

function Reveal({
  children,
  delay = 0,
  className = '',
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const { ref, visible } = useReveal<HTMLDivElement>();
  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(28px)',
        transition: `opacity 700ms ease-out ${delay}ms, transform 700ms cubic-bezier(.22,.61,.36,1) ${delay}ms`,
        willChange: 'opacity, transform',
      }}
    >
      {children}
    </div>
  );
}

function Particles({ count = 28 }: { count?: number }) {
  // Partículas energéticas flotantes generadas determinísticamente para evitar
  // mismatch en SSR.
  const items = useMemo(() => {
    const seeded = (i: number) => {
      const x = Math.sin(i * 12.9898) * 43758.5453;
      return x - Math.floor(x);
    };
    return Array.from({ length: count }, (_, i) => {
      const left = seeded(i + 1) * 100;
      const top = seeded(i + 2) * 100;
      const size = 1.5 + seeded(i + 3) * 3;
      const delay = seeded(i + 4) * 8;
      const dur = 8 + seeded(i + 5) * 10;
      const solar = seeded(i + 6) > 0.78;
      return { left, top, size, delay, dur, solar };
    });
  }, [count]);

  return (
    <div className="elecol-particles" aria-hidden="true">
      {items.map((p, i) => (
        <span
          key={i}
          className="elecol-particle"
          style={{
            left: `${p.left}%`,
            top: `${p.top}%`,
            width: `${p.size}px`,
            height: `${p.size}px`,
            background: p.solar ? BRAND.solar : BRAND.cyan,
            boxShadow: `0 0 ${p.size * 4}px ${p.solar ? BRAND.solar : BRAND.cyan}`,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.dur}s`,
          }}
        />
      ))}
    </div>
  );
}

function EnergyLines() {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 1440 900"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="line-cyan" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={BRAND.cyan} stopOpacity="0" />
          <stop offset="0.5" stopColor={BRAND.cyan} stopOpacity="0.45" />
          <stop offset="1" stopColor={BRAND.cyan} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="line-solar" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor={BRAND.solar} stopOpacity="0" />
          <stop offset="0.5" stopColor={BRAND.solar} stopOpacity="0.35" />
          <stop offset="1" stopColor={BRAND.solar} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d="M -50 220 Q 360 120 720 240 T 1500 200" stroke="url(#line-cyan)" strokeWidth="1.2" fill="none" className="elecol-flow" />
      <path d="M -50 480 Q 380 380 760 520 T 1500 460" stroke="url(#line-cyan)" strokeWidth="0.8" fill="none" className="elecol-flow" style={{ animationDelay: '1.4s' }} />
      <path d="M -50 740 Q 420 640 800 760 T 1500 720" stroke="url(#line-solar)" strokeWidth="1" fill="none" className="elecol-flow" style={{ animationDelay: '2.8s' }} />
    </svg>
  );
}

function BrandLogo({ className = 'h-7' }: { className?: string }) {
  // Wordmark inline tipo SVG para evitar 404 si el archivo aún no está.
  return (
    <svg viewBox="0 0 220 56" className={className} aria-label="ELECOL" role="img">
      <defs>
        <linearGradient id="elecol-logo-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={BRAND.foam} />
          <stop offset="1" stopColor={BRAND.cyan} />
        </linearGradient>
      </defs>
      <path
        d="M 12 16 L 36 16 L 24 30 L 38 30 L 18 50 L 26 34 L 14 34 Z"
        fill={BRAND.solar}
      />
      <text
        x="54"
        y="40"
        fontFamily="ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif"
        fontWeight="800"
        letterSpacing="6"
        fontSize="30"
        fill="url(#elecol-logo-grad)"
      >
        ELE<tspan fill={BRAND.solar}>COL</tspan>
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Página principal
// ---------------------------------------------------------------------------

export default function ElecolLanding() {
  const scrolled = useScrolled(32);
  const [navOpen, setNavOpen] = useState(false);

  const scrollTo = useCallback((id: string) => {
    if (typeof window === 'undefined') return;
    const el = document.querySelector(id);
    if (!el) return;
    const rect = (el as HTMLElement).getBoundingClientRect();
    const targetY = window.scrollY + rect.top - 72;
    const startY = window.scrollY;
    const dist = targetY - startY;
    const dur = 900;
    const startTime = performance.now();
    const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
    const step = (now: number) => {
      const t = Math.min(1, (now - startTime) / dur);
      window.scrollTo(0, startY + dist * easeInOut(t));
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, []);

  return (
    <>
      <Head>
        <title>ELECOL — Las nuevas estaciones de energía para Latinoamérica</title>
        <meta
          name="description"
          content="Electrolineras inteligentes impulsadas por energía solar, automatización y una infraestructura diseñada para escalar en Latinoamérica."
        />
        <meta name="theme-color" content={BRAND.deep} />
        <meta property="og:title" content="ELECOL — Energía que fluye como nuestro mar" />
        <meta
          property="og:description"
          content="Infraestructura energética premium para la movilidad eléctrica en Latinoamérica."
        />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/elecol/brand/og-image.png.placeholder.svg" />
        <link rel="icon" type="image/svg+xml" href="/elecol/brand/isotipo.svg" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap"
          rel="stylesheet"
        />
      </Head>

      <div className="elecol-root">
        {/* HEADER -------------------------------------------------------- */}
        <header
          className={`fixed inset-x-0 top-0 z-50 transition-all duration-500 ${
            scrolled ? 'elecol-header-scrolled' : 'elecol-header'
          }`}
        >
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 lg:h-20 lg:px-10">
            <a
              href="#hero"
              onClick={(e) => {
                e.preventDefault();
                scrollTo('#hero');
              }}
              className="group flex items-center gap-3"
            >
              <BrandLogo className="h-7 lg:h-8" />
            </a>

            <nav className="hidden items-center gap-8 lg:flex">
              {NAV_LINKS.map((l) => (
                <a
                  key={l.href}
                  href={l.href}
                  onClick={(e) => {
                    e.preventDefault();
                    scrollTo(l.href);
                  }}
                  className="elecol-nav-link"
                >
                  {l.label}
                </a>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              <a
                href="#cta"
                onClick={(e) => {
                  e.preventDefault();
                  scrollTo('#cta');
                }}
                className="elecol-cta-solar hidden lg:inline-flex"
              >
                Descargar Brief
              </a>
              <button
                aria-label="Abrir menú"
                aria-expanded={navOpen}
                onClick={() => setNavOpen((s) => !s)}
                className="elecol-burger lg:hidden"
              >
                <span />
                <span />
                <span />
              </button>
            </div>
          </div>

          {/* Mobile drawer */}
          <div
            className={`lg:hidden overflow-hidden transition-[max-height,opacity] duration-500 ${
              navOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'
            }`}
          >
            <div className="elecol-mobile-drawer mx-4 mb-4 rounded-2xl p-6">
              <div className="flex flex-col gap-4">
                {NAV_LINKS.map((l) => (
                  <a
                    key={l.href}
                    href={l.href}
                    onClick={(e) => {
                      e.preventDefault();
                      setNavOpen(false);
                      scrollTo(l.href);
                    }}
                    className="text-base text-[color:var(--elecol-foam)]"
                  >
                    {l.label}
                  </a>
                ))}
                <a
                  href="#cta"
                  onClick={(e) => {
                    e.preventDefault();
                    setNavOpen(false);
                    scrollTo('#cta');
                  }}
                  className="elecol-cta-solar mt-2 justify-center"
                >
                  Descargar Brief
                </a>
              </div>
            </div>
          </div>
        </header>

        {/* HERO ---------------------------------------------------------- */}
        <section id="hero" className="elecol-hero relative overflow-hidden">
          {/* Background layers */}
          <div className="elecol-hero-gradient absolute inset-0" />
          <div className="elecol-grid-pattern absolute inset-0 opacity-50" />
          <EnergyLines />
          <Particles count={32} />
          {/* Aurora orbs */}
          <div className="elecol-orb elecol-orb-1" />
          <div className="elecol-orb elecol-orb-2" />
          <div className="elecol-orb elecol-orb-3" />

          <div className="relative mx-auto grid min-h-screen max-w-7xl items-center gap-10 px-6 pb-24 pt-32 lg:grid-cols-12 lg:gap-16 lg:px-10 lg:pt-36">
            {/* Texto */}
            <div className="lg:col-span-6">
              <Reveal>
                <span className="elecol-eyebrow">
                  <span className="elecol-eyebrow-dot" />
                  Infraestructura energética premium
                </span>
              </Reveal>
              <Reveal delay={120}>
                <h1 className="elecol-h1 mt-6">
                  Las nuevas estaciones de{' '}
                  <span className="elecol-text-gradient">energía</span>
                  <br />
                  para Latinoamérica.
                </h1>
              </Reveal>
              <Reveal delay={240}>
                <p className="elecol-lede mt-8 max-w-xl">
                  Electrolineras inteligentes impulsadas por energía solar, automatización
                  y una infraestructura diseñada para escalar.
                </p>
              </Reveal>
              <Reveal delay={360}>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <a
                    href="#cta"
                    onClick={(e) => {
                      e.preventDefault();
                      scrollTo('#cta');
                    }}
                    className="elecol-cta-solar"
                  >
                    Descargar presentación
                  </a>
                  <a
                    href="#contacto"
                    onClick={(e) => {
                      e.preventDefault();
                      scrollTo('#contacto');
                    }}
                    className="elecol-cta-ghost"
                  >
                    Agendar llamada
                  </a>
                </div>
              </Reveal>
              <Reveal delay={520}>
                <div className="mt-14 flex flex-wrap items-center gap-x-10 gap-y-3 text-[11px] uppercase tracking-[0.28em] text-[color:var(--elecol-sky)]/70">
                  <span>Energía solar 100%</span>
                  <span className="opacity-40">·</span>
                  <span>Operación 24/7</span>
                  <span className="opacity-40">·</span>
                  <span>Diseñado en Colombia</span>
                </div>
              </Reveal>
            </div>

            {/* Render placeholder (video / imagen) */}
            <div className="lg:col-span-6">
              <Reveal delay={300}>
                <div className="elecol-frame group">
                  <div className="elecol-frame-glow" />
                  <div className="relative aspect-[4/5] w-full overflow-hidden rounded-3xl border border-white/10 bg-black/40 lg:aspect-[5/6]">
                    <Image
                      src={placeholder('/elecol/hero/hero-render.webp')}
                      alt="Render de electrolinera solar ELECOL"
                      fill
                      priority
                      className="object-cover transition-transform duration-[1400ms] ease-out group-hover:scale-[1.04]"
                      sizes="(min-width: 1024px) 50vw, 100vw"
                    />
                    {/* Scanline solar */}
                    <div className="elecol-scanline" />
                    {/* Esquinas marcadoras estilo HUD */}
                    <span className="elecol-corner elecol-corner-tl" />
                    <span className="elecol-corner elecol-corner-tr" />
                    <span className="elecol-corner elecol-corner-bl" />
                    <span className="elecol-corner elecol-corner-br" />
                    {/* Etiqueta inferior */}
                    <div className="absolute bottom-4 left-4 right-4 flex items-center justify-between rounded-xl bg-[color:var(--elecol-deep)]/60 px-4 py-3 backdrop-blur-md">
                      <div className="flex items-center gap-3">
                        <span className="elecol-status-dot" />
                        <span className="text-[11px] uppercase tracking-[0.3em] text-[color:var(--elecol-foam)]">
                          Estación EL-01 · Online
                        </span>
                      </div>
                      <span className="text-[11px] tabular-nums text-[color:var(--elecol-sky)]/80">
                        12.4 kWh/min
                      </span>
                    </div>
                  </div>
                </div>
              </Reveal>
            </div>
          </div>

          {/* Scroll cue */}
          <div className="absolute inset-x-0 bottom-6 flex justify-center">
            <div className="elecol-scroll-cue" aria-hidden="true">
              <span />
            </div>
          </div>
        </section>

        {/* INFRAESTRUCTURA ---------------------------------------------- */}
        <section id="infraestructura" className="elecol-section relative">
          <div className="mx-auto max-w-7xl px-6 lg:px-10">
            <Reveal>
              <p className="elecol-section-eyebrow">Infraestructura inteligente</p>
            </Reveal>
            <Reveal delay={100}>
              <h2 className="elecol-h2 mt-4 max-w-3xl">
                Estaciones diseñadas para operar{' '}
                <span className="elecol-text-gradient">sin pausa</span>.
              </h2>
            </Reveal>
            <Reveal delay={180}>
              <p className="elecol-body mt-6 max-w-2xl text-[color:var(--elecol-sky)]/85">
                Hardware modular, energía solar integrada y un cerebro propio que ajusta la
                potencia, la disponibilidad y los pagos en tiempo real.
              </p>
            </Reveal>

            <div className="mt-16 grid items-center gap-10 lg:grid-cols-12 lg:gap-16">
              {/* Imagen estación */}
              <div className="lg:col-span-5">
                <Reveal>
                  <div className="elecol-frame group">
                    <div className="elecol-frame-glow" style={{ opacity: 0.55 }} />
                    <div className="relative aspect-[4/5] w-full overflow-hidden rounded-3xl border border-white/10 bg-black/40">
                      <Image
                        src={placeholder('/elecol/infraestructura/estacion-render.webp')}
                        alt="Render de estación ELECOL"
                        fill
                        className="object-cover transition-transform duration-[1400ms] ease-out group-hover:scale-[1.05]"
                        sizes="(min-width: 1024px) 40vw, 100vw"
                      />
                      <span className="elecol-corner elecol-corner-tl" />
                      <span className="elecol-corner elecol-corner-br" />
                    </div>
                  </div>
                </Reveal>
              </div>

              {/* Cards */}
              <div className="grid gap-5 sm:grid-cols-2 lg:col-span-7">
                {[
                  {
                    title: 'Energía solar integrada',
                    text: 'Paneles propios y compatibilidad con la red. Cada estación produce gran parte de la energía que entrega.',
                    icon: '/elecol/infraestructura/icon-solar.svg',
                    accent: BRAND.solar,
                  },
                  {
                    title: 'Operación autónoma 24/7',
                    text: 'Diagnóstico continuo, balanceo de carga y reinicio remoto sin necesidad de personal en sitio.',
                    icon: '/elecol/infraestructura/icon-autonomia.svg',
                    accent: BRAND.cyan,
                  },
                  {
                    title: 'Compatibilidad universal EV',
                    text: 'Conectores CCS, CHAdeMO y Type 2 en la misma estación. Listos para cualquier flota.',
                    icon: '/elecol/infraestructura/icon-ev.svg',
                    accent: BRAND.sky,
                  },
                  {
                    title: 'Carga rápida inteligente',
                    text: 'Distribución dinámica de potencia hasta 180 kW por punto, sin saturar la red local.',
                    icon: '/elecol/infraestructura/icon-carga-rapida.svg',
                    accent: BRAND.solar,
                  },
                ].map((c, i) => (
                  <Reveal key={c.title} delay={i * 90}>
                    <article className="elecol-card group h-full">
                      <div
                        className="elecol-card-icon"
                        style={{ background: `${c.accent}1f`, color: c.accent }}
                      >
                        <Image src={c.icon} alt="" width={28} height={28} />
                      </div>
                      <h3 className="elecol-card-title mt-6">{c.title}</h3>
                      <p className="elecol-card-text mt-3">{c.text}</p>
                      <span
                        className="elecol-card-border"
                        style={{ background: `linear-gradient(120deg, transparent, ${c.accent}66, transparent)` }}
                      />
                    </article>
                  </Reveal>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* SOFTWARE ELECOL OS ------------------------------------------- */}
        <section id="tecnologia" className="elecol-section relative">
          <div className="elecol-grid-pattern absolute inset-0 opacity-30" />
          <div className="relative mx-auto max-w-7xl px-6 lg:px-10">
            <div className="text-center">
              <Reveal>
                <p className="elecol-section-eyebrow">ELECOL OS</p>
              </Reveal>
              <Reveal delay={100}>
                <h2 className="elecol-h2 mx-auto mt-4 max-w-3xl">
                  Una plataforma, no solo una{' '}
                  <span className="elecol-text-gradient">estación</span>.
                </h2>
              </Reveal>
              <Reveal delay={180}>
                <p className="elecol-body mx-auto mt-6 max-w-2xl text-[color:var(--elecol-sky)]/85">
                  ELECOL OS conecta cada estación, cada operador y cada cliente bajo una
                  sola capa de control. Diseñado para escalar de 1 a 10.000 puntos sin
                  cambiar de herramienta.
                </p>
              </Reveal>
            </div>

            {/* Mockup dashboard central */}
            <Reveal delay={240}>
              <div className="elecol-frame group mt-16">
                <div className="elecol-frame-glow" style={{ opacity: 0.7 }} />
                <div className="relative aspect-[16/10] w-full overflow-hidden rounded-3xl border border-white/10 bg-black/40">
                  <Image
                    src={placeholder('/elecol/software/dashboard-mockup.webp')}
                    alt="Dashboard ELECOL OS"
                    fill
                    className="object-cover transition-transform duration-[1600ms] ease-out group-hover:scale-[1.025]"
                    sizes="(min-width: 1024px) 80vw, 100vw"
                  />
                  <div className="elecol-scanline" />
                  <span className="elecol-corner elecol-corner-tl" />
                  <span className="elecol-corner elecol-corner-tr" />
                  <span className="elecol-corner elecol-corner-bl" />
                  <span className="elecol-corner elecol-corner-br" />
                </div>
              </div>
            </Reveal>

            {/* Features grid */}
            <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {[
                { t: 'Reservas', d: 'Carga garantizada con reserva por app y prioridad de flotas.', icon: '/elecol/software/icon-reservas.svg', a: BRAND.cyan },
                { t: 'Gestión remota', d: 'Actualizaciones OTA, reinicio de puntos y diagnóstico desde cualquier lugar.', icon: '/elecol/software/icon-remoto.svg', a: BRAND.sky },
                { t: 'Monitoreo en tiempo real', d: 'Estado, energía entregada y temperatura de cada punto en vivo.', icon: '/elecol/software/icon-monitoreo.svg', a: BRAND.solar },
                { t: 'Analítica', d: 'Reportes de uso, recaudo y eficiencia por estación, ciudad o flota.', icon: '/elecol/software/icon-analitica.svg', a: BRAND.cyan },
                { t: 'Gestión de franquicias', d: 'Operadores múltiples, splits configurables y dashboards por marca.', icon: '/elecol/software/icon-franquicias.svg', a: BRAND.sky },
                { t: 'Pagos integrados', d: 'Tarjetas, QR, billeteras y planes corporativos sin terceros adicionales.', icon: '/elecol/software/icon-pagos.svg', a: BRAND.solar },
              ].map((f, i) => (
                <Reveal key={f.t} delay={i * 70}>
                  <article className="elecol-mini-card group">
                    <div
                      className="elecol-mini-icon"
                      style={{ background: `${f.a}1c`, color: f.a }}
                    >
                      <Image src={f.icon} alt="" width={22} height={22} />
                    </div>
                    <h3 className="elecol-mini-title">{f.t}</h3>
                    <p className="elecol-mini-text">{f.d}</p>
                  </article>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* RED LATAM ----------------------------------------------------- */}
        <section id="expansion" className="elecol-section relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent via-[color:var(--elecol-deep)] to-transparent" />
          <div className="relative mx-auto max-w-7xl px-6 lg:px-10">
            <div className="grid items-center gap-10 lg:grid-cols-12 lg:gap-16">
              <div className="lg:col-span-5">
                <Reveal>
                  <p className="elecol-section-eyebrow">Red nacional & LATAM</p>
                </Reveal>
                <Reveal delay={100}>
                  <h2 className="elecol-h2 mt-4">
                    Una red que <span className="elecol-text-gradient">conecta</span>{' '}
                    el continente.
                  </h2>
                </Reveal>
                <Reveal delay={200}>
                  <p className="elecol-body mt-6 text-[color:var(--elecol-sky)]/85">
                    Diseñado para conectar Colombia y Latinoamérica mediante infraestructura
                    energética inteligente. Cada estación es un nodo más de la red.
                  </p>
                </Reveal>
                <Reveal delay={300}>
                  <ul className="mt-8 space-y-3 text-[15px] text-[color:var(--elecol-foam)]/85">
                    {[
                      'Despliegue por corredores estratégicos',
                      'Modelo de franquicia con soporte técnico',
                      'Integración con flotas y operadores logísticos',
                    ].map((t) => (
                      <li key={t} className="flex items-start gap-3">
                        <span
                          className="mt-2 inline-block h-2 w-2 rounded-full"
                          style={{ background: BRAND.solar, boxShadow: `0 0 12px ${BRAND.solar}` }}
                        />
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                </Reveal>
              </div>

              <div className="lg:col-span-7">
                <Reveal delay={200}>
                  <div className="elecol-frame group">
                    <div className="elecol-frame-glow" />
                    <div className="relative aspect-[5/4] w-full overflow-hidden rounded-3xl border border-white/10 bg-black/40">
                      <Image
                        src={'/elecol/red-latam/mapa-latam.svg'}
                        alt="Mapa de cobertura LATAM"
                        fill
                        className="object-contain"
                        sizes="(min-width: 1024px) 55vw, 100vw"
                      />
                      {/* Dots de ciudades animados */}
                      {[
                        { x: '46%', y: '30%', solar: true },
                        { x: '54%', y: '44%', solar: false },
                        { x: '50%', y: '62%', solar: true },
                        { x: '44%', y: '76%', solar: false },
                        { x: '58%', y: '24%', solar: false },
                        { x: '40%', y: '52%', solar: true },
                      ].map((d, i) => (
                        <span
                          key={i}
                          className="elecol-map-dot"
                          style={{
                            left: d.x,
                            top: d.y,
                            background: d.solar ? BRAND.solar : BRAND.cyan,
                            boxShadow: `0 0 16px ${d.solar ? BRAND.solar : BRAND.cyan}`,
                            animationDelay: `${i * 0.4}s`,
                          }}
                        />
                      ))}
                    </div>
                  </div>
                </Reveal>
              </div>
            </div>
          </div>
        </section>

        {/* ROI & ESTADÍSTICAS ------------------------------------------- */}
        <RoiSection />

        {/* CTA FINAL ----------------------------------------------------- */}
        <section id="cta" className="elecol-section relative overflow-hidden">
          <div className="absolute inset-0">
            <Image
              src={placeholder('/elecol/cta/cta-bg.webp')}
              alt=""
              fill
              className="object-cover opacity-60"
              sizes="100vw"
            />
            <div className="absolute inset-0 bg-gradient-to-b from-[color:var(--elecol-deep)] via-[color:var(--elecol-deep)]/40 to-[color:var(--elecol-deep)]" />
          </div>
          <Particles count={22} />
          <div className="relative mx-auto max-w-4xl px-6 py-32 text-center lg:py-40 lg:px-10">
            <Reveal>
              <p className="elecol-section-eyebrow justify-center">Conviértete en parte</p>
            </Reveal>
            <Reveal delay={120}>
              <h2 className="elecol-h2 mx-auto mt-4 max-w-3xl">
                de la infraestructura energética del{' '}
                <span className="elecol-text-gradient">futuro</span>.
              </h2>
            </Reveal>
            <Reveal delay={240}>
              <p className="elecol-body mx-auto mt-8 max-w-xl text-[color:var(--elecol-sky)]/85">
                Hablemos sobre cómo ELECOL puede impulsar tu flota, tu ciudad o tu negocio
                con energía limpia y tecnología de clase mundial.
              </p>
            </Reveal>
            <Reveal delay={360}>
              <div id="contacto" className="mt-12 flex flex-wrap items-center justify-center gap-4">
                <a href="#cta" className="elecol-cta-solar">
                  Descargar brief
                </a>
                <a href="#contacto" className="elecol-cta-ghost">
                  Hablar con un asesor
                </a>
              </div>
            </Reveal>
          </div>
        </section>

        {/* FOOTER -------------------------------------------------------- */}
        <footer className="elecol-footer">
          <div className="mx-auto flex max-w-7xl flex-col gap-10 px-6 py-14 lg:flex-row lg:items-start lg:justify-between lg:px-10">
            <div className="max-w-sm">
              <BrandLogo className="h-8" />
              <p className="mt-5 text-sm text-[color:var(--elecol-sky)]/70">
                Energía que fluye como nuestro mar. Infraestructura energética premium
                para la movilidad eléctrica en Latinoamérica.
              </p>
            </div>

            <div className="grid flex-1 grid-cols-2 gap-8 sm:grid-cols-3 lg:max-w-2xl">
              <div>
                <p className="elecol-footer-h">Producto</p>
                <ul className="mt-3 space-y-2 text-sm text-[color:var(--elecol-foam)]/70">
                  <li><a href="#tecnologia">ELECOL OS</a></li>
                  <li><a href="#infraestructura">Estaciones</a></li>
                  <li><a href="#expansion">Red LATAM</a></li>
                </ul>
              </div>
              <div>
                <p className="elecol-footer-h">Compañía</p>
                <ul className="mt-3 space-y-2 text-sm text-[color:var(--elecol-foam)]/70">
                  <li><a href="#roi">Impacto</a></li>
                  <li><a href="#cta">Contacto</a></li>
                  <li><a href="#cta">Brief inversionistas</a></li>
                </ul>
              </div>
              <div>
                <p className="elecol-footer-h">Cobertura</p>
                <ul className="mt-3 space-y-2 text-sm text-[color:var(--elecol-foam)]/70">
                  <li>Colombia · sede</li>
                  <li>Expansión LATAM</li>
                  <li>contacto@elecol.co</li>
                </ul>
              </div>
            </div>
          </div>
          <div className="border-t border-white/5">
            <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-6 py-6 text-xs text-[color:var(--elecol-sky)]/50 sm:flex-row lg:px-10">
              <span>© {new Date().getFullYear()} ELECOL · Energía que fluye como nuestro mar</span>
              <span>Diseñado en Colombia · Construido para Latinoamérica</span>
            </div>
          </div>
        </footer>
      </div>

      {/* Estilos --------------------------------------------------------- */}
      <style jsx global>{`
        :root {
          --elecol-deep: ${BRAND.deep};
          --elecol-electric: ${BRAND.electric};
          --elecol-cyan: ${BRAND.cyan};
          --elecol-sky: ${BRAND.sky};
          --elecol-foam: ${BRAND.foam};
          --elecol-solar: ${BRAND.solar};
        }

        .elecol-root {
          background: var(--elecol-deep);
          color: var(--elecol-foam);
          font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
          -webkit-font-smoothing: antialiased;
          scroll-behavior: smooth;
          min-height: 100vh;
        }

        html { scroll-behavior: smooth; }

        /* Header */
        .elecol-header {
          background: transparent;
          border-bottom: 1px solid transparent;
        }
        .elecol-header-scrolled {
          background: rgba(3, 4, 94, 0.55);
          backdrop-filter: saturate(160%) blur(18px);
          -webkit-backdrop-filter: saturate(160%) blur(18px);
          border-bottom: 1px solid rgba(144, 224, 239, 0.08);
          box-shadow: 0 12px 40px -24px rgba(0, 180, 216, 0.4);
        }
        .elecol-nav-link {
          position: relative;
          font-size: 13px;
          letter-spacing: 0.08em;
          color: rgba(202, 240, 248, 0.78);
          transition: color 220ms ease;
        }
        .elecol-nav-link:hover { color: var(--elecol-foam); }
        .elecol-nav-link::after {
          content: '';
          position: absolute;
          left: 50%;
          bottom: -6px;
          height: 1px;
          width: 0;
          background: linear-gradient(90deg, transparent, var(--elecol-cyan), transparent);
          transform: translateX(-50%);
          transition: width 320ms ease;
        }
        .elecol-nav-link:hover::after { width: 120%; }

        .elecol-cta-solar {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 10px 22px;
          border-radius: 999px;
          background: var(--elecol-solar);
          color: #1A1300;
          font-weight: 600;
          font-size: 14px;
          letter-spacing: 0.02em;
          box-shadow: 0 12px 32px -10px rgba(255, 195, 0, 0.55), inset 0 -2px 0 rgba(0,0,0,0.12);
          transition: transform 240ms ease, box-shadow 320ms ease, filter 240ms ease;
        }
        .elecol-cta-solar:hover {
          transform: translateY(-2px);
          box-shadow: 0 18px 44px -10px rgba(255, 195, 0, 0.7), inset 0 -2px 0 rgba(0,0,0,0.15);
          filter: brightness(1.04);
        }
        .elecol-cta-ghost {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 10px 22px;
          border-radius: 999px;
          background: transparent;
          color: var(--elecol-foam);
          font-weight: 500;
          font-size: 14px;
          letter-spacing: 0.02em;
          border: 1px solid rgba(202, 240, 248, 0.25);
          backdrop-filter: blur(6px);
          transition: border-color 240ms ease, background 240ms ease, transform 240ms ease;
        }
        .elecol-cta-ghost:hover {
          border-color: var(--elecol-cyan);
          background: rgba(0, 180, 216, 0.08);
          transform: translateY(-2px);
        }

        .elecol-burger {
          width: 40px;
          height: 40px;
          border-radius: 12px;
          border: 1px solid rgba(202, 240, 248, 0.18);
          display: inline-flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 5px;
          background: rgba(3, 4, 94, 0.45);
          backdrop-filter: blur(8px);
        }
        .elecol-burger span {
          display: block;
          width: 16px;
          height: 1.5px;
          background: var(--elecol-foam);
          border-radius: 2px;
        }
        .elecol-mobile-drawer {
          background: rgba(3, 4, 94, 0.85);
          backdrop-filter: blur(18px);
          border: 1px solid rgba(144, 224, 239, 0.1);
        }

        /* Hero */
        .elecol-hero { min-height: 100vh; }
        .elecol-hero-gradient {
          background:
            radial-gradient(1200px 600px at 15% 20%, rgba(0, 119, 182, 0.45), transparent 60%),
            radial-gradient(900px 500px at 85% 70%, rgba(0, 180, 216, 0.30), transparent 60%),
            radial-gradient(700px 500px at 50% 100%, rgba(255, 195, 0, 0.10), transparent 70%),
            linear-gradient(180deg, #03045E 0%, #020330 100%);
        }
        .elecol-grid-pattern {
          background-image:
            linear-gradient(rgba(144, 224, 239, 0.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(144, 224, 239, 0.06) 1px, transparent 1px);
          background-size: 64px 64px;
          mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
          -webkit-mask-image: radial-gradient(ellipse at center, black 30%, transparent 80%);
        }
        .elecol-orb {
          position: absolute;
          border-radius: 50%;
          filter: blur(80px);
          opacity: 0.55;
          pointer-events: none;
          animation: elecol-float 16s ease-in-out infinite;
        }
        .elecol-orb-1 { width: 420px; height: 420px; background: var(--elecol-electric); top: -120px; left: -120px; }
        .elecol-orb-2 { width: 520px; height: 520px; background: var(--elecol-cyan); bottom: -200px; right: -160px; animation-delay: 4s; opacity: 0.4; }
        .elecol-orb-3 { width: 320px; height: 320px; background: var(--elecol-solar); top: 30%; right: 25%; animation-delay: 8s; opacity: 0.15; }

        .elecol-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          padding: 8px 16px;
          border-radius: 999px;
          font-size: 11px;
          letter-spacing: 0.3em;
          text-transform: uppercase;
          color: var(--elecol-sky);
          background: rgba(0, 180, 216, 0.08);
          border: 1px solid rgba(0, 180, 216, 0.22);
        }
        .elecol-eyebrow-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: var(--elecol-solar);
          box-shadow: 0 0 10px var(--elecol-solar);
          animation: elecol-pulse 2.4s ease-in-out infinite;
        }
        .elecol-section-eyebrow {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          font-size: 11px;
          letter-spacing: 0.32em;
          text-transform: uppercase;
          color: var(--elecol-sky);
        }
        .elecol-section-eyebrow::before {
          content: '';
          width: 28px;
          height: 1px;
          background: linear-gradient(90deg, transparent, var(--elecol-cyan));
        }

        .elecol-h1 {
          font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
          font-weight: 700;
          font-size: clamp(2.6rem, 5.2vw, 4.8rem);
          line-height: 1.02;
          letter-spacing: -0.025em;
          color: var(--elecol-foam);
        }
        .elecol-h2 {
          font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
          font-weight: 700;
          font-size: clamp(2rem, 3.6vw, 3.2rem);
          line-height: 1.08;
          letter-spacing: -0.02em;
          color: var(--elecol-foam);
        }
        .elecol-text-gradient {
          background: linear-gradient(120deg, var(--elecol-cyan) 0%, var(--elecol-sky) 40%, var(--elecol-solar) 100%);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        .elecol-lede {
          font-size: clamp(1.05rem, 1.4vw, 1.25rem);
          line-height: 1.55;
          color: rgba(202, 240, 248, 0.85);
          font-weight: 300;
        }
        .elecol-body {
          font-size: 16px;
          line-height: 1.7;
        }

        /* Frame premium para placeholders */
        .elecol-frame { position: relative; }
        .elecol-frame-glow {
          position: absolute;
          inset: -20px;
          background: radial-gradient(closest-side, rgba(0, 180, 216, 0.45), transparent 70%);
          filter: blur(28px);
          opacity: 0.7;
          pointer-events: none;
          transition: opacity 600ms ease;
          z-index: 0;
        }
        .elecol-frame:hover .elecol-frame-glow { opacity: 1; }
        .elecol-corner {
          position: absolute;
          width: 24px;
          height: 24px;
          border: 1.5px solid var(--elecol-cyan);
          opacity: 0.8;
        }
        .elecol-corner-tl { top: 14px; left: 14px; border-right: 0; border-bottom: 0; }
        .elecol-corner-tr { top: 14px; right: 14px; border-left: 0; border-bottom: 0; }
        .elecol-corner-bl { bottom: 14px; left: 14px; border-right: 0; border-top: 0; }
        .elecol-corner-br { bottom: 14px; right: 14px; border-left: 0; border-top: 0; }
        .elecol-scanline {
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, transparent 0%, rgba(0, 180, 216, 0.10) 50%, transparent 100%);
          background-size: 100% 8px;
          mix-blend-mode: screen;
          pointer-events: none;
          opacity: 0.4;
        }
        .elecol-status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--elecol-solar);
          box-shadow: 0 0 12px var(--elecol-solar);
          animation: elecol-pulse 1.6s ease-in-out infinite;
        }

        .elecol-scroll-cue {
          width: 24px;
          height: 38px;
          border-radius: 14px;
          border: 1px solid rgba(202, 240, 248, 0.3);
          display: flex;
          justify-content: center;
          padding-top: 6px;
        }
        .elecol-scroll-cue span {
          width: 3px;
          height: 8px;
          border-radius: 3px;
          background: var(--elecol-cyan);
          animation: elecol-scroll-dot 1.8s ease-in-out infinite;
        }

        /* Sections base */
        .elecol-section { padding: clamp(80px, 12vw, 160px) 0; position: relative; }

        /* Cards */
        .elecol-card {
          position: relative;
          padding: 28px 26px;
          border-radius: 22px;
          background: linear-gradient(160deg, rgba(255,255,255,0.04), rgba(255,255,255,0.015));
          border: 1px solid rgba(144, 224, 239, 0.08);
          backdrop-filter: blur(10px);
          overflow: hidden;
          transition: transform 360ms ease, border-color 360ms ease, box-shadow 360ms ease;
        }
        .elecol-card:hover {
          transform: translateY(-4px);
          border-color: rgba(0, 180, 216, 0.45);
          box-shadow: 0 30px 60px -30px rgba(0, 180, 216, 0.35);
        }
        .elecol-card-icon {
          width: 52px;
          height: 52px;
          border-radius: 14px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }
        .elecol-card-title {
          font-family: 'Space Grotesk', ui-sans-serif, system-ui, sans-serif;
          font-size: 19px;
          font-weight: 600;
          color: var(--elecol-foam);
        }
        .elecol-card-text {
          font-size: 14.5px;
          line-height: 1.6;
          color: rgba(202, 240, 248, 0.7);
        }
        .elecol-card-border {
          position: absolute;
          inset: 0;
          border-radius: 22px;
          padding: 1px;
          background: linear-gradient(120deg, transparent, rgba(0, 180, 216, 0.4), transparent);
          -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
          -webkit-mask-composite: xor;
                  mask-composite: exclude;
          opacity: 0;
          transition: opacity 360ms ease;
        }
        .elecol-card:hover .elecol-card-border { opacity: 1; }

        .elecol-mini-card {
          padding: 24px 22px;
          border-radius: 18px;
          background: rgba(255,255,255,0.025);
          border: 1px solid rgba(144, 224, 239, 0.07);
          transition: transform 320ms ease, border-color 320ms ease;
        }
        .elecol-mini-card:hover {
          transform: translateY(-3px);
          border-color: rgba(0, 180, 216, 0.35);
        }
        .elecol-mini-icon {
          width: 42px;
          height: 42px;
          border-radius: 12px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }
        .elecol-mini-title {
          font-family: 'Space Grotesk', sans-serif;
          font-size: 16px;
          font-weight: 600;
          color: var(--elecol-foam);
          margin-top: 18px;
        }
        .elecol-mini-text {
          font-size: 13.5px;
          line-height: 1.55;
          color: rgba(202, 240, 248, 0.65);
          margin-top: 8px;
        }

        /* ROI counters */
        .elecol-roi-card {
          padding: 36px 28px;
          border-radius: 24px;
          background: linear-gradient(160deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
          border: 1px solid rgba(144, 224, 239, 0.08);
          position: relative;
          overflow: hidden;
        }
        .elecol-roi-value {
          font-family: 'Space Grotesk', sans-serif;
          font-weight: 700;
          font-size: clamp(2.2rem, 4.2vw, 3.6rem);
          line-height: 1;
          background: linear-gradient(120deg, var(--elecol-foam), var(--elecol-cyan));
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
          letter-spacing: -0.02em;
        }
        .elecol-roi-bar {
          margin-top: 18px;
          width: 100%;
          height: 4px;
          background: rgba(144, 224, 239, 0.1);
          border-radius: 999px;
          overflow: hidden;
          position: relative;
        }
        .elecol-roi-bar::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(90deg, var(--elecol-cyan), var(--elecol-solar));
          transform-origin: left;
          animation: elecol-bar 2.4s cubic-bezier(.22,.61,.36,1) forwards;
        }

        /* Map dots */
        .elecol-map-dot {
          position: absolute;
          width: 10px;
          height: 10px;
          border-radius: 50%;
          transform: translate(-50%, -50%);
          animation: elecol-pulse 2.2s ease-in-out infinite;
        }

        /* Footer */
        .elecol-footer {
          background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.4));
          border-top: 1px solid rgba(144, 224, 239, 0.08);
        }
        .elecol-footer-h {
          font-size: 11px;
          letter-spacing: 0.3em;
          text-transform: uppercase;
          color: var(--elecol-sky);
        }
        .elecol-footer a:hover { color: var(--elecol-foam); }

        /* Particles */
        .elecol-particles { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
        .elecol-particle {
          position: absolute;
          border-radius: 50%;
          opacity: 0.7;
          animation: elecol-particle-float linear infinite;
        }

        /* Keyframes */
        @keyframes elecol-float {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(30px, -40px) scale(1.08); }
        }
        @keyframes elecol-pulse {
          0%, 100% { transform: scale(1); opacity: 0.9; }
          50% { transform: scale(1.4); opacity: 0.5; }
        }
        @keyframes elecol-scroll-dot {
          0% { transform: translateY(0); opacity: 1; }
          80% { transform: translateY(12px); opacity: 0; }
          100% { transform: translateY(12px); opacity: 0; }
        }
        @keyframes elecol-flow {
          0% { stroke-dasharray: 0 600; }
          100% { stroke-dasharray: 600 0; }
        }
        .elecol-flow {
          stroke-dasharray: 0 600;
          animation: elecol-flow 6s ease-in-out infinite alternate;
        }
        @keyframes elecol-particle-float {
          0% { transform: translateY(0) translateX(0); opacity: 0; }
          10% { opacity: 0.9; }
          50% { transform: translateY(-40px) translateX(20px); opacity: 0.6; }
          90% { opacity: 0.4; }
          100% { transform: translateY(-90px) translateX(-10px); opacity: 0; }
        }
        @keyframes elecol-bar {
          0% { transform: scaleX(0); }
          100% { transform: scaleX(1); }
        }

        @media (prefers-reduced-motion: reduce) {
          .elecol-particle,
          .elecol-orb,
          .elecol-flow,
          .elecol-map-dot,
          .elecol-status-dot,
          .elecol-eyebrow-dot,
          .elecol-scroll-cue span,
          .elecol-roi-bar::after {
            animation: none !important;
          }
        }
      `}</style>
    </>
  );
}

// ---------------------------------------------------------------------------
// Sección ROI con counters animados
// ---------------------------------------------------------------------------

function RoiSection() {
  const stats = [
    { value: 1_240_000, suffix: '+', label: 'Horas de carga acumuladas', format: 'compact' as const },
    { value: 38, suffix: '%', label: 'ROI estimado anual' },
    { value: 180, suffix: ' kW', label: 'Potencia por punto de carga' },
    { value: 12_400, suffix: ' Ton', label: 'CO₂ evitado / año', format: 'compact' as const },
    { value: 92, suffix: '%', label: 'Energía solar promedio' },
    { value: 4, suffix: 'x', label: 'Crecimiento proyectado (24m)' },
  ];
  return (
    <section id="roi" className="elecol-section relative">
      <div className="mx-auto max-w-7xl px-6 lg:px-10">
        <div className="text-center">
          <Reveal>
            <p className="elecol-section-eyebrow">Impacto medible</p>
          </Reveal>
          <Reveal delay={100}>
            <h2 className="elecol-h2 mx-auto mt-4 max-w-3xl">
              Números que <span className="elecol-text-gradient">demuestran</span> el modelo.
            </h2>
          </Reveal>
          <Reveal delay={180}>
            <p className="elecol-body mx-auto mt-6 max-w-2xl text-[color:var(--elecol-sky)]/85">
              Estimaciones basadas en piloto y proyecciones de despliegue por corredor.
              ROI calculado con un horizonte de 5 años.
            </p>
          </Reveal>
        </div>

        <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {stats.map((s, i) => (
            <Reveal key={s.label} delay={i * 80}>
              <RoiCard {...s} />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function RoiCard({
  value,
  suffix,
  label,
  format,
}: {
  value: number;
  suffix?: string;
  label: string;
  format?: 'compact';
}) {
  const { ref, value: current } = useCountUp(value, 2000);
  const formatted = useMemo(() => {
    if (format === 'compact' && current >= 1000) {
      if (current >= 1_000_000) return `${(current / 1_000_000).toFixed(1)}M`;
      return `${Math.round(current / 1000)}K`;
    }
    return current.toLocaleString('es-CO');
  }, [current, format]);
  return (
    <article className="elecol-roi-card">
      <span ref={ref} className="elecol-roi-value">
        {formatted}
        {suffix ? <span className="text-[color:var(--elecol-solar)]">{suffix}</span> : null}
      </span>
      <p className="mt-4 text-[14px] uppercase tracking-[0.2em] text-[color:var(--elecol-sky)]/70">
        {label}
      </p>
      <div className="elecol-roi-bar" />
    </article>
  );
}
