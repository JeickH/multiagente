import Head from 'next/head';
import Image from 'next/image';
import { useState } from 'react';

/**
 * Landing page de Gloma.
 *
 * Identidad (identidad_gloma/branding_gloma_v2.html):
 *  - Paleta: Rosa empolvado #F7D1CD, Marrón tierra #5E503F, Crema #FDFBF7.
 *  - Tipografía: Syne (títulos) + Inter (cuerpo).
 *  - Concepto "Soft Cyber": mucho aire, limpio, cálido.
 *
 * Assets servidos desde frontend/public/gloma/.
 */

const BRAND = {
  rose: '#F7D1CD',
  brown: '#5E503F',
  cream: '#FDFBF7',
  roseSoft: '#FBE9E7',
  brownLight: '#8B7A67',
};

// --- Datos de la landing (fácil editar) -----------------------------------
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
    title: 'Personalizado al ADN de tu marca',
    text: 'Configuramos el tono, las respuestas y los flujos para que cada mensaje sea indistinguible del de tu equipo.',
  },
  {
    title: 'Integraciones fluidas',
    text: 'Se conecta con tus fuentes de información y tu operación para que el sistema y tu equipo trabajen en sintonía.',
  },
  {
    title: 'Contexto a priori de tu empresa',
    text: 'El agente conoce tu catálogo, políticas y procesos antes de hablar con el primer cliente.',
  },
  {
    title: 'Escalamiento a agentes humanos',
    text: 'Cuando la conversación lo requiere, la derivamos a tu equipo con todo el contexto listo.',
  },
  {
    title: 'Medición y mejora continua',
    text: 'Tableros claros de conversiones, tiempos y satisfacción para seguir afinando la operación.',
  },
  {
    title: 'Equipo de soporte dedicado',
    text: 'Un equipo disponible para atender requerimientos, ajustes de flujos y nuevos casos de uso.',
  },
];

const STATS = [
  { value: '+150.000', label: 'mensajes enviados' },
  { value: '4 meses', label: 'retorno de inversión promedio' },
  { value: '+10.000', label: 'horas de asesores AI operando' },
];

// --- Componentes ----------------------------------------------------------
function IconPlaceholder({ label }: { label: string }) {
  return (
    <div
      className="w-12 h-12 rounded-full flex items-center justify-center mb-3 flex-shrink-0"
      style={{ backgroundColor: BRAND.roseSoft, color: BRAND.brown }}
      aria-hidden="true"
    >
      <span className="text-[10px] font-medium opacity-60 px-1 text-center leading-tight">
        icono
      </span>
    </div>
  );
}

export default function GlomaLanding() {
  const [form, setForm] = useState({ email: '', telefono: '' });
  const [status, setStatus] = useState<'idle' | 'sending' | 'ok' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const WHATSAPP_URL = 'https://wa.me/573003187871?text=Hola%20Gloma%2C%20quiero%20más%20información';

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
          content="Gloma: automatización de ventas por WhatsApp para distribuidores mayoristas de moda y belleza."
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
        {/* ===== HEADER con banner ===== */}
        <header className="relative w-full overflow-hidden">
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
                  'linear-gradient(to right, rgba(94,80,63,0.55), rgba(94,80,63,0.1))',
              }}
            />
          </div>
          <nav className="relative z-10 flex items-center justify-between max-w-6xl mx-auto px-6 md:px-10 pt-6">
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 md:w-11 md:h-11 rounded-full bg-white/90 flex items-center justify-center overflow-hidden"
                aria-label="Gloma"
              >
                <Image
                  src="/gloma/logo_gloma_original.png"
                  alt="Gloma"
                  width={44}
                  height={44}
                  className="object-contain"
                />
              </div>
              <span
                className="font-syne text-white text-xl md:text-2xl tracking-[0.15em]"
                style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800 }}
              >
                GLOMA
              </span>
            </div>
            <a
              href="#contacto"
              className="hidden md:inline-block px-5 py-2 rounded-full text-sm font-medium transition-opacity hover:opacity-90"
              style={{ backgroundColor: BRAND.rose, color: BRAND.brown }}
            >
              Agenda una demo
            </a>
          </nav>

          <div className="relative z-10 max-w-6xl mx-auto px-6 md:px-10 py-24 md:py-36">
            <h1
              className="text-white text-4xl md:text-6xl lg:text-7xl leading-tight max-w-3xl"
              style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800 }}
            >
              Tecnología que resalta tu catálogo
            </h1>
            <p
              className="text-white/90 mt-6 text-base md:text-xl max-w-xl font-light"
              style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
            >
              Conexión mayorista, automatización humana. Para distribuidores de moda y belleza que no quieren perder ventas por falta de respuesta.
            </p>
            <div className="mt-10 flex flex-col sm:flex-row gap-3">
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
                className="inline-block px-6 py-3 rounded-full text-sm font-semibold text-center border-2 border-white/80 text-white hover:bg-white/10 transition-colors"
              >
                Que te contactemos
              </a>
            </div>
          </div>
        </header>

        {/* ===== PREVIEW de la plataforma ===== */}
        <section className="max-w-6xl mx-auto px-6 md:px-10 py-20 md:py-28 space-y-24">
          {PREVIEW_SECTIONS.map((s, i) => (
            <div
              key={i}
              className={`grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center ${
                s.reverse ? 'md:[direction:rtl]' : ''
              }`}
            >
              <div className="md:[direction:ltr]">
                <div
                  className="inline-block text-xs tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
                  style={{ backgroundColor: BRAND.roseSoft, color: BRAND.brown }}
                >
                  {`0${i + 1} · valor`}
                </div>
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
                  <Image
                    src={s.image}
                    alt={s.title}
                    fill
                    className="object-cover"
                  />
                </div>
              </div>
            </div>
          ))}
        </section>

        {/* ===== FUNCIONALIDADES CLAVE ===== */}
        <section
          className="py-20 md:py-28"
          style={{ backgroundColor: '#FFFFFF' }}
        >
          <div className="max-w-6xl mx-auto px-6 md:px-10">
            <div className="text-center max-w-2xl mx-auto mb-14 md:mb-20">
              <div
                className="inline-block text-xs tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
                style={{ backgroundColor: BRAND.roseSoft, color: BRAND.brown }}
              >
                Funcionalidades clave
              </div>
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
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8 md:gap-10">
              {FEATURES.map((f) => (
                <div
                  key={f.title}
                  className="p-6 md:p-7 rounded-2xl transition-transform hover:-translate-y-1"
                  style={{ backgroundColor: BRAND.cream }}
                >
                  <IconPlaceholder label={f.title} />
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
              ))}
            </div>
          </div>
        </section>

        {/* ===== ESTADÍSTICAS ===== */}
        <section
          className="py-20 md:py-24"
          style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
        >
          <div className="max-w-5xl mx-auto px-6 md:px-10">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-6 text-center">
              {STATS.map((s) => (
                <div key={s.label} className="flex flex-col items-center">
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center mb-4"
                    style={{ backgroundColor: BRAND.rose, color: BRAND.brown }}
                  >
                    <span className="text-[10px] font-medium opacity-70 px-1 text-center leading-tight">
                      icono
                    </span>
                  </div>
                  <div
                    className="text-4xl md:text-5xl mb-2"
                    style={{
                      fontFamily: 'Syne, system-ui, sans-serif',
                      fontWeight: 800,
                      color: BRAND.rose,
                    }}
                  >
                    {s.value}
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

        {/* ===== CONTACTO ===== */}
        <section
          id="contacto"
          className="py-20 md:py-28"
          style={{ backgroundColor: BRAND.cream }}
        >
          <div className="max-w-5xl mx-auto px-6 md:px-10 grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-16 items-start">
            <div>
              <div
                className="inline-block text-xs tracking-widest uppercase mb-4 px-3 py-1 rounded-full"
                style={{ backgroundColor: BRAND.roseSoft, color: BRAND.brown }}
              >
                Conversemos
              </div>
              <h2
                className="text-3xl md:text-5xl mb-6 leading-tight"
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 700,
                  color: BRAND.brown,
                }}
              >
                ¿Listo para atender más, trabajando menos?
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
                className="inline-flex items-center gap-2 px-5 py-3 rounded-full text-sm font-semibold transition-transform hover:-translate-y-0.5"
                style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
              >
                <span>💬</span> Escríbenos por WhatsApp
              </a>
            </div>

            <form
              onSubmit={handleSubmit}
              className="bg-white rounded-3xl p-6 md:p-8 shadow-md"
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
                className="w-full px-4 py-3 border rounded-xl text-sm mb-5 focus:outline-none"
                style={{ borderColor: BRAND.roseSoft, color: BRAND.brown, fontFamily: 'Inter, system-ui, sans-serif' }}
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
                className="w-full px-4 py-3 border rounded-xl text-sm mb-6 focus:outline-none"
                style={{ borderColor: BRAND.roseSoft, color: BRAND.brown, fontFamily: 'Inter, system-ui, sans-serif' }}
              />
              <button
                type="submit"
                disabled={status === 'sending'}
                className="w-full py-3 rounded-full font-semibold text-sm transition-opacity hover:opacity-90 disabled:opacity-60"
                style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
              >
                {status === 'sending' ? 'Enviando…' : 'Que me contacten'}
              </button>
              {message && (
                <p
                  className="mt-4 text-sm text-center"
                  style={{ color: status === 'ok' ? '#10b981' : '#dc2626' }}
                >
                  {message}
                </p>
              )}
            </form>
          </div>
        </section>

        {/* ===== FOOTER ===== */}
        <footer style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}>
          <div className="max-w-6xl mx-auto px-6 md:px-10 py-14 grid grid-cols-1 md:grid-cols-3 gap-10">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-white/95 flex items-center justify-center overflow-hidden">
                  <Image
                    src="/gloma/logo_gloma_original.png"
                    alt="Gloma"
                    width={40}
                    height={40}
                    className="object-contain"
                  />
                </div>
                <span
                  className="text-xl tracking-[0.15em]"
                  style={{ fontFamily: 'Syne, system-ui, sans-serif', fontWeight: 800 }}
                >
                  GLOMA
                </span>
              </div>
              <p
                className="text-sm opacity-70 max-w-xs"
                style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
              >
                Glow al mayor. Conexión mayorista, automatización humana.
              </p>
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
                <li>hola@gloma.co</li>
                <li>+57 300 318 7871</li>
                <li>Cra. 15 #88-21, Bogotá, Colombia</li>
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
          <div className="border-t border-white/10 py-5 text-center text-xs opacity-60" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
            © 2026 Gloma. Datos de contacto de prueba.
          </div>
        </footer>
      </div>
    </>
  );
}
