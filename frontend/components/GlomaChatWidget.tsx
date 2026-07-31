import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Widget de chat de la landing Gloma (Sprint 20 #270).
 *
 * Botón flotante de WhatsApp en la esquina inferior derecha que abre una
 * conversación REAL con el bot institucional de Gloma — sin necesidad de que
 * el visitante tenga el WhatsApp de Gloma ni de salir de la página: el bot se
 * instancia en el backend (`POST /api/landing/chat` → `/landing/chat`), con el
 * mismo motor LLM que atiende el simulador de la app y que atenderá el
 * WhatsApp de Gloma cuando el número quede conectado.
 *
 * El estado de la conversación vive en el token `session` que devuelve el
 * backend (cifrado; el cliente solo lo reenvía).
 */

const BRAND = {
  rose: '#F7D1CD',
  brown: '#5E503F',
  cream: '#FDFBF7',
  roseSoft: '#FBE9E7',
  brownLight: '#8B7A67',
  whatsapp: '#25D366',
};

const WHATSAPP_URL =
  'https://wa.me/573003187871?text=Hola%20Gloma%2C%20quiero%20más%20información';

const SUGERENCIAS = [
  '¿Qué hace Gloma por mi empresa?',
  '¿Cómo lo conecto a mi WhatsApp?',
  '¿Cuánto cuesta?',
];

type Msg = {
  id: number;
  from: 'bot' | 'user';
  text: string;
  url?: string;
  mediaType?: string;
};

type ChatAction = {
  type: string;
  text: string;
  url?: string | null;
  media_type?: string | null;
};

type ChatResponse = {
  actions: ChatAction[];
  session: string | null;
  finished: boolean;
  handoff: boolean;
};

/** Renderiza el formato de WhatsApp que usa el bot: *negrilla* y saltos de línea. */
function FormattedText({ text }: { text: string }) {
  // El backend ya normaliza `**negrilla**` → `*negrilla*`; aquí por si acaso.
  const clean = text.replace(/\*\*(\S[^*\n]*?\S|\S)\*\*/g, '*$1*');
  return (
    <>
      {clean.split('\n').map((line, li) => (
        <span key={li}>
          {li > 0 && <br />}
          {line.split(/(\*[^*\n]+\*)/g).map((part, pi) =>
            part.startsWith('*') && part.endsWith('*') && part.length > 2 ? (
              <strong key={pi}>{part.slice(1, -1)}</strong>
            ) : (
              <span key={pi}>{part}</span>
            )
          )}
        </span>
      ))}
    </>
  );
}

function WhatsAppGlyph({ size = 30, color = '#FFFFFF' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} aria-hidden="true">
      <path d="M17.47 14.38c-.3-.15-1.75-.86-2.02-.96-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.64.07-.3-.15-1.25-.46-2.38-1.47-.88-.78-1.47-1.75-1.64-2.05-.17-.3-.02-.46.13-.6.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.6-.92-2.2-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.01-1.04 2.47s1.06 2.86 1.21 3.06c.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.69.63.71.22 1.36.19 1.87.12.57-.09 1.75-.72 2-1.41.25-.69.25-1.28.17-1.41-.07-.13-.27-.2-.57-.35z" />
      <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.46 1.32 4.96L2 22l5.25-1.38a9.87 9.87 0 0 0 4.79 1.22h.01c5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.82 9.82 0 0 0 12.04 2zm0 18.13h-.01a8.2 8.2 0 0 1-4.18-1.15l-.3-.18-3.11.82.83-3.04-.2-.31a8.17 8.17 0 0 1-1.25-4.36c0-4.54 3.7-8.24 8.24-8.24 2.2 0 4.27.86 5.82 2.42a8.18 8.18 0 0 1 2.41 5.83c0 4.54-3.69 8.23-8.25 8.23z" />
    </svg>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="escribiendo">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: 9999,
            backgroundColor: BRAND.brownLight,
            display: 'inline-block',
            animation: `glomaTyping 1.2s ease-in-out ${i * 0.18}s infinite`,
          }}
        />
      ))}
    </span>
  );
}

export default function GlomaChatWidget() {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const [showWhatsappCta, setShowWhatsappCta] = useState(false);
  const [unread, setUnread] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const startedRef = useRef(false);
  const idRef = useRef(0);

  const pushMsgs = useCallback((items: Omit<Msg, 'id'>[]) => {
    setMsgs((prev) => [
      ...prev,
      ...items.map((m) => ({ ...m, id: (idRef.current += 1) })),
    ]);
  }, []);

  /** Un turno contra el backend. `text=null` en el primer turno (saludo). */
  const send = useCallback(
    async (text: string | null) => {
      setSending(true);
      try {
        const res = await fetch('/api/landing/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session, message: text }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: ChatResponse = await res.json();
        pushMsgs(
          (data.actions || []).map((a) => ({
            from: 'bot' as const,
            text: a.text || '',
            url: a.url || undefined,
            mediaType: a.media_type || undefined,
          }))
        );
        setSession(data.session);
        setFinished(Boolean(data.finished));
        if (data.handoff) setShowWhatsappCta(true);
      } catch {
        // Detalle solo del lado del servidor (regla de seguridad #6).
        pushMsgs([
          {
            from: 'bot',
            text:
              'Tuvimos un inconveniente para responderte por aquí 🙏 Escríbenos por WhatsApp al *+57 300 318 7871* y te atendemos de una vez.',
          },
        ]);
        setShowWhatsappCta(true);
      } finally {
        setSending(false);
      }
    },
    [session, pushMsgs]
  );

  // Primer saludo al abrir por primera vez.
  useEffect(() => {
    if (!open || startedRef.current) return;
    startedRef.current = true;
    void send(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Autoscroll + foco.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    if (open && !sending && !finished) inputRef.current?.focus();
  }, [msgs, sending, open, finished]);

  useEffect(() => {
    if (!open && msgs.length > 0) setUnread(true);
    if (open) setUnread(false);
  }, [msgs, open]);

  // Escape cierra el panel.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || sending || finished) return;
    setInput('');
    pushMsgs([{ from: 'user', text }]);
    void send(text);
  };

  const sendSuggestion = (text: string) => {
    if (sending || finished) return;
    pushMsgs([{ from: 'user', text }]);
    void send(text);
  };

  return (
    <>
      <style jsx global>{`
        @keyframes glomaTyping {
          0%, 60%, 100% { opacity: 0.25; transform: translateY(0); }
          30% { opacity: 1; transform: translateY(-3px); }
        }
        @keyframes glomaWidgetIn {
          from { opacity: 0; transform: translateY(16px) scale(0.97); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes glomaPulse {
          0% { box-shadow: 0 0 0 0 rgba(37, 211, 102, 0.55); }
          70% { box-shadow: 0 0 0 16px rgba(37, 211, 102, 0); }
          100% { box-shadow: 0 0 0 0 rgba(37, 211, 102, 0); }
        }
      `}</style>

      {/* ===== Panel de chat ===== */}
      {open && (
        <div
          role="dialog"
          aria-label="Chat con el asistente de Gloma"
          className="fixed z-[60] flex flex-col overflow-hidden shadow-2xl"
          style={{
            right: 'max(1rem, env(safe-area-inset-right))',
            bottom: 'calc(5.5rem + env(safe-area-inset-bottom))',
            width: 'min(23rem, calc(100vw - 2rem))',
            height: 'min(31rem, calc(100vh - 8rem))',
            borderRadius: 20,
            backgroundColor: BRAND.cream,
            fontFamily: 'Inter, system-ui, sans-serif',
            animation: 'glomaWidgetIn 260ms cubic-bezier(.22,.61,.36,1) both',
          }}
        >
          {/* Header */}
          <div
            className="flex items-center gap-3 px-4 py-3"
            style={{ backgroundColor: BRAND.brown, color: '#FFFFFF' }}
          >
            <div
              className="flex items-center justify-center rounded-full shrink-0"
              style={{ width: 38, height: 38, backgroundColor: BRAND.rose }}
            >
              <span
                style={{
                  fontFamily: 'Syne, system-ui, sans-serif',
                  fontWeight: 800,
                  color: BRAND.brown,
                  fontSize: 16,
                }}
              >
                L
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <div
                className="text-sm font-semibold truncate"
                style={{ fontFamily: 'Syne, system-ui, sans-serif' }}
              >
                Lía · Asistente de Gloma
              </div>
              <div className="text-[11px] flex items-center gap-1.5 opacity-90">
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 9999,
                    backgroundColor: BRAND.whatsapp,
                    display: 'inline-block',
                  }}
                />
                En línea · responde al instante
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Cerrar chat"
              className="p-1 rounded-full hover:bg-white/10 transition-colors"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Mensajes */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-4 space-y-2.5">
            <p
              className="text-[11px] text-center px-6 pb-1"
              style={{ color: BRAND.brownLight }}
            >
              Estás hablando con el agente de IA de Gloma — el mismo tipo de
              agente que montamos para tu marca ✨
            </p>
            <p
              className="text-[10px] text-center px-6 pb-2"
              style={{ color: BRAND.brownLight, opacity: 0.8 }}
            >
              Guardamos la conversación para mejorar el servicio. No compartas
              datos sensibles (contraseñas o información bancaria).
            </p>

            {msgs.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.from === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className="max-w-[85%] px-3 py-2 text-[13px] leading-relaxed"
                  style={
                    m.from === 'user'
                      ? {
                          backgroundColor: BRAND.brown,
                          color: '#FFFFFF',
                          borderRadius: '16px 16px 4px 16px',
                        }
                      : {
                          backgroundColor: '#FFFFFF',
                          color: BRAND.brown,
                          borderRadius: '16px 16px 16px 4px',
                          boxShadow: '0 1px 2px rgba(94,80,63,0.08)',
                        }
                  }
                >
                  {m.url && m.mediaType === 'image' ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={m.url}
                      alt={m.text || 'imagen'}
                      className="rounded-lg mb-1 max-w-full h-auto"
                    />
                  ) : null}
                  {m.text && <FormattedText text={m.text} />}
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex justify-start">
                <div
                  className="px-3 py-2.5"
                  style={{
                    backgroundColor: '#FFFFFF',
                    borderRadius: '16px 16px 16px 4px',
                    boxShadow: '0 1px 2px rgba(94,80,63,0.08)',
                  }}
                >
                  <TypingDots />
                </div>
              </div>
            )}

            {/* Sugerencias solo al inicio */}
            {!sending && msgs.length > 0 && msgs.length <= 2 && !finished && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {SUGERENCIAS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => sendSuggestion(s)}
                    className="text-[11px] px-2.5 py-1.5 rounded-full transition-colors hover:opacity-80"
                    style={{
                      backgroundColor: BRAND.roseSoft,
                      color: BRAND.brown,
                      border: `1px solid ${BRAND.rose}`,
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {showWhatsappCta && (
              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-full text-[13px] font-semibold transition-transform hover:-translate-y-0.5"
                style={{ backgroundColor: BRAND.whatsapp, color: '#FFFFFF' }}
              >
                <WhatsAppGlyph size={16} />
                Continuar por WhatsApp
              </a>
            )}
          </div>

          {/* Composer */}
          <form
            onSubmit={submit}
            className="flex items-center gap-2 px-3 py-3"
            style={{ backgroundColor: '#FFFFFF', borderTop: `1px solid ${BRAND.roseSoft}` }}
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              disabled={finished}
              placeholder={finished ? 'Conversación finalizada' : 'Escribe tu pregunta…'}
              aria-label="Escribe tu mensaje"
              className="flex-1 px-3 py-2 text-[13px] rounded-full focus:outline-none disabled:opacity-60"
              style={{
                backgroundColor: BRAND.cream,
                color: BRAND.brown,
                border: `1px solid ${BRAND.roseSoft}`,
              }}
            />
            <button
              type="submit"
              disabled={sending || finished || !input.trim()}
              aria-label="Enviar mensaje"
              className="flex items-center justify-center rounded-full transition-opacity disabled:opacity-40"
              style={{ width: 38, height: 38, backgroundColor: BRAND.brown, color: '#FFFFFF' }}
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            </button>
          </form>
        </div>
      )}

      {/* ===== Botón flotante ===== */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? 'Cerrar chat de WhatsApp' : 'Hablar con Gloma por WhatsApp'}
        className="fixed z-[60] flex items-center justify-center rounded-full shadow-xl transition-transform hover:scale-105 active:scale-95"
        style={{
          right: 'max(1rem, env(safe-area-inset-right))',
          bottom: 'calc(1rem + env(safe-area-inset-bottom))',
          width: 58,
          height: 58,
          backgroundColor: BRAND.whatsapp,
          animation: open ? undefined : 'glomaPulse 2.6s ease-out infinite',
        }}
      >
        {open ? (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        ) : (
          <WhatsAppGlyph />
        )}
        {unread && !open && (
          <span
            className="absolute"
            style={{
              top: 2,
              right: 2,
              width: 13,
              height: 13,
              borderRadius: 9999,
              backgroundColor: BRAND.rose,
              border: '2px solid #FFFFFF',
            }}
          />
        )}
      </button>
    </>
  );
}
