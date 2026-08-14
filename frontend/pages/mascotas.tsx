import Head from 'next/head';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Chat público de "Recupera Tu Mascota" — sprint "Ayuda a Cali".
 *
 * Vive en `mascotasperdidascali.glomabeauty.com` (ver `middleware.ts`) y es una
 * ventana de WhatsApp a pantalla completa: la gente que llega aquí está
 * angustiada y no debe tener que aprender una interfaz nueva. Conversa con el
 * mismo bot (`POST /api/mascotas/chat` → `/mascotas/chat`) que atenderá el
 * WhatsApp de la iniciativa cuando el número quede conectado.
 *
 * El estado de la conversación vive en el token `session` que devuelve el
 * backend (cifrado; el cliente solo lo reenvía). Las fotos se suben aparte
 * (`POST /api/mascotas/foto`) contra esa misma sesión y el backend las pega al
 * reporte cuando el bot lo registra.
 */

// Verde WhatsApp: aquí no es branding, es el affordance del canal. La gente
// reconoce esta pantalla y sabe qué hacer sin que nadie le explique.
const WA = {
  headerLight: '#008069',
  headerDark: '#202C33',
  fondoLight: '#EFEAE2',
  fondoDark: '#0B141A',
  burbujaBotLight: '#FFFFFF',
  burbujaBotDark: '#202C33',
  burbujaYoLight: '#D9FDD3',
  burbujaYoDark: '#005C4B',
  textoLight: '#111B21',
  textoDark: '#E9EDEF',
  textoTenueLight: '#667781',
  textoTenueDark: '#8696A0',
  composerLight: '#F0F2F5',
  composerDark: '#202C33',
  verde: '#25D366',
};

// Los tres casos de uso, visibles desde el primer momento: quien llega sabe de
// entrada qué puede pedir y no tiene que adivinarlo.
const ACCESOS = [
  { emoji: '🔎', titulo: 'Buscar a mi mascota', mensaje: 'Se me perdió mi mascota y quiero buscarla' },
  { emoji: '🐾', titulo: 'Reporté una que encontré', mensaje: 'Encontré una mascota y quiero reportarla' },
  { emoji: '📊', titulo: 'Descargar el listado', mensaje: 'Quiero descargar el listado de mascotas en Excel' },
];

const MAX_FOTO_BYTES = 8 * 1024 * 1024;

type Msg = {
  id: number;
  from: 'bot' | 'user';
  text: string;
  url?: string;
  kind?: 'texto' | 'imagen' | 'archivo';
  filename?: string;
  label?: string;
  hora: string;
  enviando?: boolean;
};

type ChatAction = {
  type: string;
  text: string;
  url?: string | null;
  media_type?: string | null;
  filename?: string | null;
  label?: string | null;
};

type ChatResponse = {
  actions: ChatAction[];
  session: string | null;
  finished: boolean;
  reporte_codigo: string | null;
};

function ahora(): string {
  return new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
}

/** Renderiza el formato de WhatsApp que usa el bot: *negrilla* y saltos de línea. */
function TextoFormateado({ text }: { text: string }) {
  const limpio = text.replace(/\*\*(\S[^*\n]*?\S|\S)\*\*/g, '*$1*');
  return (
    <>
      {limpio.split('\n').map((linea, li) => (
        <span key={li}>
          {li > 0 && <br />}
          {linea.split(/(\*[^*\n]+\*)/g).map((parte, pi) =>
            parte.startsWith('*') && parte.endsWith('*') && parte.length > 2 ? (
              <strong key={pi}>{parte.slice(1, -1)}</strong>
            ) : (
              <span key={pi}>{parte}</span>
            )
          )}
        </span>
      ))}
    </>
  );
}

function PuntosEscribiendo() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="escribiendo">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="rt-punto"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </span>
  );
}

export default function MascotasChat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [finalizado, setFinalizado] = useState(false);
  const [reporte, setReporte] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const arrancado = useRef(false);
  const idRef = useRef(0);
  // `session` en un ref además del estado: la subida de fotos ocurre fuera del
  // ciclo de render y necesita el token más reciente, no el de la clausura.
  const sessionRef = useRef<string | null>(null);

  const push = useCallback((items: Omit<Msg, 'id' | 'hora'>[]) => {
    setMsgs((prev) => [
      ...prev,
      ...items.map((m) => ({ ...m, id: (idRef.current += 1), hora: ahora() })),
    ]);
  }, []);

  const guardarSession = useCallback((valor: string | null) => {
    sessionRef.current = valor;
    setSession(valor);
  }, []);

  /** Un turno contra el backend. `texto=null` en el primer turno (saludo). */
  const enviar = useCallback(
    async (texto: string | null) => {
      setEnviando(true);
      try {
        const res = await fetch('/api/mascotas/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session: sessionRef.current, message: texto }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: ChatResponse = await res.json();
        push(
          (data.actions || []).map((a) => ({
            from: 'bot' as const,
            text: a.text || '',
            url: a.url || undefined,
            kind:
              a.type === 'say_media' ? ('imagen' as const)
              : a.type === 'say_file' ? ('archivo' as const)
              : ('texto' as const),
            filename: a.filename || undefined,
            label: a.label || undefined,
          }))
        );
        guardarSession(data.session);
        setFinalizado(Boolean(data.finished));
        if (data.reporte_codigo) setReporte(data.reporte_codigo);
      } catch {
        // El detalle queda del lado del servidor (regla de seguridad #6).
        push([
          {
            from: 'bot',
            text:
              'Uy, se nos cayó la conexión un momento 🙏 Intenta escribirme de nuevo, por favor.',
            kind: 'texto',
          },
        ]);
      } finally {
        setEnviando(false);
      }
    },
    [push, guardarSession]
  );

  // Saludo automático al abrir.
  useEffect(() => {
    if (arrancado.current) return;
    arrancado.current = true;
    void enviar(null);
  }, [enviar]);

  // Autoscroll + foco.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    if (!enviando && !finalizado) inputRef.current?.focus();
  }, [msgs, enviando, finalizado]);

  const enviarTexto = (e?: React.FormEvent) => {
    e?.preventDefault();
    const texto = input.trim();
    if (!texto || enviando || finalizado) return;
    setInput('');
    push([{ from: 'user', text: texto, kind: 'texto' }]);
    void enviar(texto);
  };

  const enviarAcceso = (mensaje: string) => {
    if (enviando || finalizado) return;
    push([{ from: 'user', text: mensaje, kind: 'texto' }]);
    void enviar(mensaje);
  };

  /** Adjunta una foto. Se puede hacer en cualquier momento de la conversación. */
  const subirFoto = async (file: File) => {
    if (subiendo || finalizado) return;
    if (file.size > MAX_FOTO_BYTES) {
      setAviso('Esa foto pesa más de 8 MB. Intenta con una más liviana.');
      return;
    }
    setAviso(null);
    setSubiendo(true);
    const preview = URL.createObjectURL(file);
    push([{ from: 'user', text: '', url: preview, kind: 'imagen', enviando: true }]);

    try {
      const form = new FormData();
      form.append('file', file);
      if (sessionRef.current) form.append('session', sessionRef.current);
      const res = await fetch('/api/mascotas/foto', { method: 'POST', body: form });
      if (!res.ok) {
        const cuerpo = await res.json().catch(() => null);
        throw new Error(cuerpo?.detail || 'No pudimos subir la foto');
      }
      setMsgs((prev) =>
        prev.map((m) => (m.enviando ? { ...m, enviando: false } : m))
      );
    } catch (err) {
      setMsgs((prev) => prev.filter((m) => !m.enviando));
      setAviso(
        err instanceof Error ? err.message : 'No pudimos subir la foto. Intenta de nuevo.'
      );
    } finally {
      setSubiendo(false);
    }
  };

  const modoOscuro = 'rt-oscuro';

  return (
    <>
      <Head>
        <title>Recupera Tu Mascota · Colombia</title>
        <meta
          name="description"
          content="Servicio gratuito para reunir mascotas perdidas con sus familias tras el terremoto en Colombia."
        />
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
      </Head>

      <style jsx global>{`
        html, body, #__next { height: 100%; margin: 0; }
        body {
          font-family: 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', sans-serif;
          background: ${WA.fondoLight};
        }
        @keyframes rtPunto {
          0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
          30% { opacity: 1; transform: translateY(-3px); }
        }
        .rt-punto {
          width: 6px; height: 6px; border-radius: 9999px;
          background: ${WA.textoTenueLight};
          display: inline-block;
          animation: rtPunto 1.2s ease-in-out infinite;
        }
        @keyframes rtEntra {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rt-burbuja { animation: rtEntra 200ms ease-out both; }
        /* Textura del fondo del chat, dibujada con gradientes: sin assets
           externos y sin peticiones de red extra. */
        .rt-fondo {
          background-color: ${WA.fondoLight};
          background-image:
            radial-gradient(circle at 20% 30%, rgba(0,128,105,0.05) 0 2px, transparent 2px),
            radial-gradient(circle at 70% 60%, rgba(0,128,105,0.04) 0 3px, transparent 3px),
            radial-gradient(circle at 45% 85%, rgba(0,128,105,0.03) 0 2px, transparent 2px);
          background-size: 130px 130px, 190px 190px, 160px 160px;
        }
        .rt-input::placeholder { color: ${WA.textoTenueLight}; }
        @media (prefers-color-scheme: dark) {
          body { background: ${WA.fondoDark}; }
          .rt-fondo { background-color: ${WA.fondoDark}; }
          .rt-punto { background: ${WA.textoTenueDark}; }
          .rt-input::placeholder { color: ${WA.textoTenueDark}; }
        }
      `}</style>

      <div className={`flex flex-col h-full ${modoOscuro}`} style={{ height: '100dvh' }}>
        {/* ===== Header ===== */}
        <header
          className="flex items-center gap-3 px-4 py-2.5 shrink-0"
          style={{
            backgroundColor: WA.headerLight,
            color: '#FFFFFF',
            paddingTop: 'calc(0.625rem + env(safe-area-inset-top))',
          }}
        >
          <div
            className="flex items-center justify-center rounded-full shrink-0 text-2xl"
            style={{ width: 42, height: 42, backgroundColor: 'rgba(255,255,255,0.2)' }}
            aria-hidden="true"
          >
            🐾
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold leading-tight truncate">
              Huella · Recupera Tu Mascota
            </div>
            <div className="text-[12px] opacity-90 flex items-center gap-1.5">
              {enviando ? (
                'escribiendo…'
              ) : (
                <>
                  <span
                    className="inline-block rounded-full"
                    style={{ width: 7, height: 7, backgroundColor: WA.verde }}
                  />
                  en línea · responde al instante
                </>
              )}
            </div>
          </div>
          {reporte && (
            <div
              className="text-[11px] px-2.5 py-1 rounded-full font-semibold shrink-0"
              style={{ backgroundColor: 'rgba(255,255,255,0.18)' }}
              title="Código de tu reporte"
            >
              {reporte}
            </div>
          )}
        </header>

        {/* ===== Mensajes ===== */}
        <div ref={scrollRef} className="rt-fondo flex-1 overflow-y-auto px-3 py-4">
          {/* Aviso de propósito: por qué existe este servicio. */}
          <div className="flex justify-center mb-4">
            <p
              className="text-[12px] text-center max-w-md px-4 py-2.5 rounded-lg leading-relaxed"
              style={{
                backgroundColor: '#FFF3C4',
                color: '#5B4A00',
                boxShadow: '0 1px 1px rgba(0,0,0,0.08)',
              }}
            >
              🤍 Servicio <strong>gratuito</strong> para ayudar a las personas y mascotas
              afectadas por el <strong>terremoto en Colombia</strong>. Te ayudamos a
              buscar tu mascota perdida, a reportar una que encontraste y a descargar el
              listado actualizado.
            </p>
          </div>
          <div className="flex justify-center mb-4">
            <p
              className="text-[11px] text-center max-w-md px-4 leading-relaxed"
              style={{ color: WA.textoTenueLight }}
            >
              Al continuar con la conversación aceptas que usemos los datos que
              compartas <strong>únicamente</strong> con el fin de reunir a las mascotas
              perdidas con sus dueños. Tu teléfono no se comparte con nadie hasta que
              alguien reconozca a la mascota.
            </p>
          </div>

          {msgs.map((m) => (
            <div
              key={m.id}
              className={`rt-burbuja flex mb-2 ${m.from === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className="max-w-[85%] sm:max-w-[70%] px-2.5 py-1.5 text-[14.5px] leading-relaxed"
                style={{
                  backgroundColor:
                    m.from === 'user' ? WA.burbujaYoLight : WA.burbujaBotLight,
                  color: WA.textoLight,
                  borderRadius:
                    m.from === 'user' ? '8px 8px 2px 8px' : '8px 8px 8px 2px',
                  boxShadow: '0 1px 0.5px rgba(0,0,0,0.13)',
                  opacity: m.enviando ? 0.6 : 1,
                }}
              >
                {m.kind === 'imagen' && m.url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={m.url}
                    alt={m.text || 'Foto de la mascota'}
                    className="rounded-md mb-1 w-full h-auto"
                    style={{ maxWidth: 280 }}
                  />
                )}
                {m.kind === 'archivo' && m.url && (
                  <a
                    href={m.url}
                    download={m.filename}
                    className="flex items-center gap-2.5 px-2 py-2 rounded-md mb-1 no-underline transition-opacity hover:opacity-85"
                    style={{ backgroundColor: 'rgba(0,128,105,0.08)', color: WA.textoLight }}
                  >
                    <span className="text-2xl" aria-hidden="true">📊</span>
                    <span className="min-w-0">
                      <span className="block text-[13px] font-semibold truncate">
                        {m.label || 'Listado de mascotas'}
                      </span>
                      <span className="block text-[11px]" style={{ color: WA.textoTenueLight }}>
                        {m.filename || 'listado.xlsx'} · toca para descargar
                      </span>
                    </span>
                  </a>
                )}
                {m.text && <TextoFormateado text={m.text} />}
                <span
                  className="block text-right text-[10.5px] mt-0.5"
                  style={{ color: WA.textoTenueLight }}
                >
                  {m.hora}
                </span>
              </div>
            </div>
          ))}

          {enviando && (
            <div className="flex justify-start mb-2">
              <div
                className="px-3 py-2.5"
                style={{
                  backgroundColor: WA.burbujaBotLight,
                  borderRadius: '8px 8px 8px 2px',
                  boxShadow: '0 1px 0.5px rgba(0,0,0,0.13)',
                }}
              >
                <PuntosEscribiendo />
              </div>
            </div>
          )}

          {/* Accesos rápidos: solo al inicio, cuando la persona aún no ha escrito. */}
          {!enviando && msgs.length > 0 && msgs.length <= 2 && !finalizado && (
            <div className="flex flex-col gap-2 mt-3 max-w-md mx-auto">
              <p className="text-[11px] text-center" style={{ color: WA.textoTenueLight }}>
                Toca una opción o escríbenos con tus palabras
              </p>
              {ACCESOS.map((a) => (
                <button
                  key={a.titulo}
                  type="button"
                  onClick={() => enviarAcceso(a.mensaje)}
                  className="flex items-center gap-3 px-3.5 py-3 text-left text-[14px] rounded-lg transition-transform hover:-translate-y-0.5"
                  style={{
                    backgroundColor: WA.burbujaBotLight,
                    color: WA.textoLight,
                    boxShadow: '0 1px 2px rgba(0,0,0,0.12)',
                  }}
                >
                  <span className="text-xl" aria-hidden="true">{a.emoji}</span>
                  <span className="font-medium">{a.titulo}</span>
                </button>
              ))}
            </div>
          )}

          {finalizado && (
            <div className="flex justify-center mt-4">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="text-[13px] px-4 py-2 rounded-full font-semibold"
                style={{ backgroundColor: WA.headerLight, color: '#FFFFFF' }}
              >
                Empezar una conversación nueva
              </button>
            </div>
          )}
        </div>

        {/* ===== Composer ===== */}
        {aviso && (
          <p
            className="text-[12px] text-center px-4 py-1.5 shrink-0"
            style={{ backgroundColor: '#FDECEA', color: '#8A1C12' }}
            role="alert"
          >
            {aviso}
          </p>
        )}
        <form
          onSubmit={enviarTexto}
          className="flex items-end gap-2 px-3 py-2.5 shrink-0"
          style={{ backgroundColor: WA.composerLight }}
        >
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void subirFoto(file);
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={subiendo || finalizado}
            aria-label="Adjuntar una foto de la mascota"
            title="Adjuntar una foto de la mascota"
            className="flex items-center justify-center rounded-full shrink-0 transition-opacity disabled:opacity-40"
            style={{ width: 40, height: 40, color: WA.textoTenueLight }}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={700}
            disabled={finalizado}
            placeholder={finalizado ? 'Conversación finalizada' : 'Escribe un mensaje'}
            aria-label="Escribe tu mensaje"
            className="rt-input flex-1 px-4 py-2.5 text-[15px] rounded-full focus:outline-none disabled:opacity-60"
            style={{
              backgroundColor: WA.burbujaBotLight,
              color: WA.textoLight,
              border: 'none',
            }}
          />
          <button
            type="submit"
            disabled={enviando || finalizado || !input.trim()}
            aria-label="Enviar mensaje"
            className="flex items-center justify-center rounded-full shrink-0 transition-opacity disabled:opacity-40"
            style={{ width: 42, height: 42, backgroundColor: WA.headerLight, color: '#FFFFFF' }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </form>

        {/* Firma de la tecnología. Vive SOLO en este sitio: la plataforma y la
            landing conservan su marca sin cambios. */}
        <footer
          className="text-center text-[11px] py-2 shrink-0"
          style={{
            backgroundColor: WA.composerLight,
            color: WA.textoTenueLight,
            paddingBottom: 'calc(0.5rem + env(safe-area-inset-bottom))',
          }}
        >
          Tecnología de{' '}
          <a
            href="https://www.instagram.com/gloma_app/"
            target="_blank"
            rel="noopener noreferrer"
            className="font-bold hover:underline"
            style={{ color: WA.headerLight }}
            title="Ver @gloma_app en Instagram"
          >
            Gloma App
          </a>
        </footer>
      </div>
    </>
  );
}
