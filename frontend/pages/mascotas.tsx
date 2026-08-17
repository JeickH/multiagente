import Head from 'next/head';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Chat público de "Recupera Tu Mascota" — sprint "Ayuda a Cali".
 *
 * Vive en `mascotasperdidascolombia.com` (ver `middleware.ts`) y es una ventana
 * de WhatsApp a pantalla completa: la gente que llega aquí está angustiada y no
 * debe tener que aprender una interfaz nueva. Conversa con el mismo bot
 * (`POST /api/mascotas/chat` → `/mascotas/chat`) que atenderá el WhatsApp de la
 * iniciativa cuando el número quede conectado.
 *
 * **Antesala antes del chat**: al entrar no arranca la conversación de una. Se
 * pide primero el nombre, el teléfono y a qué viene la persona (buscar la suya
 * o reportar una que encontró). Al tocar "Iniciar chat" esos tres datos viajan
 * como el primer mensaje del hilo, así que el bot arranca sabiendo el camino y
 * el contacto en vez de gastar tres turnos preguntándolos. Reemplaza a los
 * botones de acceso rápido que antes vivían dentro del chat.
 *
 * **El listado no abre chat**: es el tercer caso de uso del bot, pero entregar
 * un archivo no necesita que nadie converse. De 75 conversaciones reales, 21
 * fueron solo para bajar el Excel y 19 se resolvieron en un turno — cada una
 * gastando una conversación completa del modelo. Ese botón pide el enlace
 * firmado a `GET /api/mascotas/listado/enlace` y baja el archivo ahí mismo.
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

type Motivo = 'buscar' | 'encontrada';

// Los dos caminos que se eligen antes de abrir el chat. `frase` es lo que se
// escribe en el primer mensaje: se redacta en primera persona porque el bot lo
// recibe como si la persona lo hubiera tecleado.
const MOTIVOS: {
  id: Motivo;
  emoji: string;
  titulo: string;
  detalle: string;
  frase: string;
}[] = [
  {
    id: 'buscar',
    emoji: '🔎',
    titulo: 'Busco a mi mascota',
    detalle: 'Se me perdió y quiero encontrarla',
    frase: 'Se me perdió mi mascota y quiero buscarla',
  },
  {
    id: 'encontrada',
    emoji: '🐾',
    titulo: 'Encontré una mascota',
    detalle: 'Quiero reportarla para que aparezca su familia',
    frase: 'Encontré una mascota y quiero reportarla',
  },
];

const MAX_FOTO_BYTES = 8 * 1024 * 1024;

// Duración de la salida de la antesala. El chat se monta justo después, así que
// este número y el del CSS (`rtIntakeSale`) tienen que ir de la mano.
const MS_TRANSICION = 320;

type Fase = 'intake' | 'abriendo' | 'chat';

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

type Errores = { nombre?: string; telefono?: string; motivo?: string };

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
  const [fase, setFase] = useState<Fase>('intake');
  const [nombre, setNombre] = useState('');
  const [telefono, setTelefono] = useState('');
  const [motivo, setMotivo] = useState<Motivo | null>(null);
  const [errores, setErrores] = useState<Errores>({});

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [subiendo, setSubiendo] = useState(false);
  const [session, setSession] = useState<string | null>(null);
  const [finalizado, setFinalizado] = useState(false);
  const [reporte, setReporte] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [descargando, setDescargando] = useState(false);
  const [errorListado, setErrorListado] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const nombreRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<number | null>(null);
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

  /** Un turno contra el backend. */
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

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  // Foco inicial en el nombre, solo en pantallas grandes: en el celular abrir
  // el teclado de una tapa media pantalla y esconde el resto del formulario.
  useEffect(() => {
    if (fase !== 'intake') return;
    if (window.matchMedia('(min-width: 640px)').matches) nombreRef.current?.focus();
  }, [fase]);

  // Autoscroll + foco.
  useEffect(() => {
    if (fase !== 'chat') return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    if (!enviando && !finalizado) inputRef.current?.focus();
  }, [msgs, enviando, finalizado, fase]);

  /** Arma el primer mensaje del hilo con lo que se llenó en la antesala. */
  const primerMensaje = (elegido: Motivo): string => {
    const frase = MOTIVOS.find((m) => m.id === elegido)!.frase;
    return `Hola, soy ${nombre.trim()}. ${frase}. Mi teléfono de contacto es ${telefono.trim()}.`;
  };

  const validar = (): boolean => {
    const errs: Errores = {};
    if (nombre.trim().length < 2) {
      errs.nombre = 'Escribe tu nombre para saber cómo llamarte.';
    }
    // Solo se cuentan los dígitos: la gente escribe el número como quiere
    // (+57, espacios, guiones) y no es momento de pelear por el formato.
    const digitos = telefono.replace(/\D/g, '');
    if (digitos.length < 7 || digitos.length > 15) {
      errs.telefono = 'Escribe un número de contacto válido, por ejemplo 300 123 4567.';
    }
    if (!motivo) {
      errs.motivo = 'Cuéntanos si buscas a tu mascota o si encontraste una.';
    }
    setErrores(errs);
    return Object.keys(errs).length === 0;
  };

  /** Cierra la antesala y abre el chat con el primer mensaje ya escrito. */
  const abrirChat = (elegido: Motivo) => {
    if (fase !== 'intake') return;
    if (!validar()) return;
    const texto = primerMensaje(elegido);
    setFase('abriendo');
    timerRef.current = window.setTimeout(() => {
      setFase('chat');
      push([{ from: 'user', text: texto, kind: 'texto' }]);
      void enviar(texto);
    }, MS_TRANSICION);
  };

  /**
   * Baja el listado de encontradas sin abrir el chat.
   *
   * El backend firma el enlace y lo devuelve; aquí solo se navega a él. Se usa
   * `location.href` y no `window.open` porque la respuesta viene con
   * `Content-Disposition: attachment`: el navegador baja el archivo y deja la
   * antesala como está, sin arriesgarse a que un bloqueador de ventanas
   * emergentes se coma la descarga.
   */
  const descargarListado = async () => {
    if (descargando) return;
    setDescargando(true);
    setErrorListado(null);
    try {
      const res = await fetch('/api/mascotas/listado/enlace');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: { url?: string } = await res.json();
      if (!data.url) throw new Error('respuesta sin enlace');
      window.location.href = data.url;
    } catch {
      // El detalle queda del lado del servidor (regla de seguridad #6).
      setErrorListado(
        'No pudimos preparar la descarga. Intenta de nuevo o pídenos el listado en el chat.'
      );
    } finally {
      setDescargando(false);
    }
  };

  const enviarTexto = (e?: React.FormEvent) => {
    e?.preventDefault();
    const texto = input.trim();
    if (!texto || enviando || finalizado) return;
    setInput('');
    push([{ from: 'user', text: texto, kind: 'texto' }]);
    void enviar(texto);
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

  const enAntesala = fase !== 'chat';

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

        /* ===== Transición antesala → chat =====
           La tarjeta del formulario se encoge y se desvanece; enseguida el chat
           entra abriéndose, con el header bajando y el composer subiendo. La
           idea es que se sienta como una ventana de chat que se abre, no como
           un cambio de página. */
        @keyframes rtIntakeEntra {
          from { opacity: 0; transform: translateY(16px) scale(0.98); }
          to { opacity: 1; transform: none; }
        }
        @keyframes rtIntakeSale {
          from { opacity: 1; transform: none; }
          to { opacity: 0; transform: translateY(-12px) scale(0.93); }
        }
        @keyframes rtChatAbre {
          from { opacity: 0; transform: scale(0.97); }
          to { opacity: 1; transform: none; }
        }
        @keyframes rtHeaderBaja {
          from { transform: translateY(-100%); }
          to { transform: none; }
        }
        @keyframes rtComposerSube {
          from { transform: translateY(140%); }
          to { transform: none; }
        }
        .rt-tarjeta { animation: rtIntakeEntra 320ms cubic-bezier(0.2, 0.8, 0.3, 1) both; }
        .rt-tarjeta-sale {
          animation: rtIntakeSale ${MS_TRANSICION}ms cubic-bezier(0.4, 0, 1, 1) both;
        }
        .rt-chat { animation: rtChatAbre 360ms cubic-bezier(0.2, 0.8, 0.3, 1) both; }
        .rt-chat-header { animation: rtHeaderBaja 340ms cubic-bezier(0.2, 0.9, 0.3, 1) both; }
        .rt-chat-composer { animation: rtComposerSube 380ms cubic-bezier(0.2, 0.9, 0.3, 1) both; }

        .rt-campo {
          width: 100%;
          border: 1.5px solid #DDE3E7;
          border-radius: 10px;
          padding: 0.65rem 0.85rem;
          font-size: 15px;
          color: ${WA.textoLight};
          background: #FFFFFF;
          outline: none;
          transition: border-color 140ms ease, box-shadow 140ms ease;
        }
        .rt-campo:focus {
          border-color: ${WA.headerLight};
          box-shadow: 0 0 0 3px rgba(0,128,105,0.12);
        }
        .rt-campo[aria-invalid='true'] { border-color: #C6362B; }
        .rt-campo::placeholder { color: #9AA6AD; }
        /* El fieldset trae min-inline-size: min-content del navegador y no se
           deja encoger; sin esto ensancha la tarjeta en pantallas angostas. */
        .rt-grupo { min-width: 0; }
        .rt-opcion {
          display: flex; align-items: center; gap: 0.75rem; width: 100%; min-width: 0;
          text-align: left; padding: 0.7rem 0.85rem;
          border: 1.5px solid #DDE3E7; border-radius: 12px; background: #FFFFFF;
          transition: border-color 140ms ease, background-color 140ms ease, transform 140ms ease;
        }
        .rt-opcion:hover { border-color: rgba(0,128,105,0.5); transform: translateY(-1px); }
        .rt-opcion[aria-pressed='true'] {
          border-color: ${WA.headerLight};
          background: rgba(0,128,105,0.07);
        }

        @media (prefers-color-scheme: dark) {
          body { background: ${WA.fondoDark}; }
          .rt-fondo { background-color: ${WA.fondoDark}; }
          .rt-punto { background: ${WA.textoTenueDark}; }
          .rt-input::placeholder { color: ${WA.textoTenueDark}; }
        }
        @media (prefers-reduced-motion: reduce) {
          .rt-burbuja, .rt-tarjeta, .rt-tarjeta-sale, .rt-chat,
          .rt-chat-header, .rt-chat-composer { animation-duration: 1ms; }
        }
      `}</style>

      <div className="flex flex-col" style={{ height: '100dvh' }}>
        {enAntesala ? (
          /* ================= Antesala: quién eres y a qué vienes ================= */
          /* Columna, no fila: centrando con `items-center` en un flex de fila la
             tarjeta no podía encogerse por debajo de su min-content y se salía
             de la pantalla en el celular. Aquí el ancho lo manda el contenedor
             y `mx-auto` la centra. */
          <div className="rt-fondo flex-1 overflow-y-auto flex flex-col justify-center px-4 py-6">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                abrirChat(motivo ?? 'buscar');
              }}
              className={`w-full max-w-[430px] mx-auto rounded-2xl px-5 py-6 sm:px-7 ${
                fase === 'abriendo' ? 'rt-tarjeta-sale' : 'rt-tarjeta'
              }`}
              style={{
                backgroundColor: WA.burbujaBotLight,
                boxShadow: '0 8px 30px rgba(0,0,0,0.13)',
              }}
              noValidate
            >
              {/* Presentación: la misma cara que van a ver en el header del chat,
                  para que la transición se sienta continua. */}
              <div className="flex items-center gap-3 mb-4">
                <div
                  className="flex items-center justify-center rounded-full shrink-0 text-2xl"
                  style={{ width: 48, height: 48, backgroundColor: 'rgba(0,128,105,0.12)' }}
                  aria-hidden="true"
                >
                  🐾
                </div>
                <div className="min-w-0">
                  <h1
                    className="text-[17px] font-semibold leading-tight"
                    style={{ color: WA.textoLight }}
                  >
                    Recupera Tu Mascota
                  </h1>
                  <p
                    className="text-[12px] flex items-center gap-1.5"
                    style={{ color: WA.textoTenueLight }}
                  >
                    <span
                      className="inline-block rounded-full"
                      style={{ width: 7, height: 7, backgroundColor: WA.verde }}
                    />
                    Huella te responde al instante
                  </p>
                </div>
              </div>

              <p
                className="text-[13px] leading-relaxed mb-5 px-3 py-2.5 rounded-lg"
                style={{ backgroundColor: '#FFF3C4', color: '#5B4A00' }}
              >
                🤍 Servicio <strong>gratuito</strong> para ayudar a las personas y mascotas
                afectadas por el <strong>terremoto en Colombia</strong>. Cuéntanos quién
                eres y qué necesitas, y abrimos el chat.
              </p>

              <div className="mb-3.5">
                <label
                  htmlFor="rt-nombre"
                  className="block text-[13px] font-semibold mb-1.5"
                  style={{ color: WA.textoLight }}
                >
                  ¿Cómo te llamas?
                </label>
                <input
                  id="rt-nombre"
                  ref={nombreRef}
                  className="rt-campo"
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  onBlur={() => errores.nombre && validar()}
                  maxLength={80}
                  autoComplete="name"
                  placeholder="Tu nombre"
                  aria-invalid={Boolean(errores.nombre)}
                  aria-describedby={errores.nombre ? 'rt-nombre-error' : undefined}
                />
                {errores.nombre && (
                  <p id="rt-nombre-error" className="text-[12px] mt-1" style={{ color: '#C6362B' }} role="alert">
                    {errores.nombre}
                  </p>
                )}
              </div>

              <div className="mb-4">
                <label
                  htmlFor="rt-telefono"
                  className="block text-[13px] font-semibold mb-1.5"
                  style={{ color: WA.textoLight }}
                >
                  ¿A qué número te contactamos?
                </label>
                <input
                  id="rt-telefono"
                  className="rt-campo"
                  value={telefono}
                  onChange={(e) => setTelefono(e.target.value)}
                  onBlur={() => errores.telefono && validar()}
                  maxLength={24}
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="300 123 4567"
                  aria-invalid={Boolean(errores.telefono)}
                  aria-describedby={
                    errores.telefono ? 'rt-telefono-error' : 'rt-telefono-ayuda'
                  }
                />
                {errores.telefono ? (
                  <p id="rt-telefono-error" className="text-[12px] mt-1" style={{ color: '#C6362B' }} role="alert">
                    {errores.telefono}
                  </p>
                ) : (
                  <p id="rt-telefono-ayuda" className="text-[12px] mt-1" style={{ color: WA.textoTenueLight }}>
                    Solo lo usamos para avisarte si aparece tu mascota.
                  </p>
                )}
              </div>

              <fieldset
                className="rt-grupo mb-5"
                aria-describedby={errores.motivo ? 'rt-motivo-error' : undefined}
              >
                <legend
                  className="text-[13px] font-semibold mb-2"
                  style={{ color: WA.textoLight }}
                >
                  ¿Qué necesitas hoy?
                </legend>
                <div className="flex flex-col gap-2">
                  {MOTIVOS.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => {
                        setMotivo(m.id);
                        setErrores((prev) => ({ ...prev, motivo: undefined }));
                      }}
                      aria-pressed={motivo === m.id}
                      className="rt-opcion"
                    >
                      <span className="text-2xl shrink-0" aria-hidden="true">{m.emoji}</span>
                      <span className="min-w-0">
                        <span
                          className="block text-[14.5px] font-medium"
                          style={{ color: WA.textoLight }}
                        >
                          {m.titulo}
                        </span>
                        <span className="block text-[12px]" style={{ color: WA.textoTenueLight }}>
                          {m.detalle}
                        </span>
                      </span>
                    </button>
                  ))}

                  {/* Tercer caso de uso del bot, pero este NO abre el chat: el
                      archivo se baja de una. Entregar un Excel no necesita
                      conversación (ni el teléfono de nadie), y así deja de
                      costar una conversación del modelo cada vez. La flecha lo
                      distingue de las dos opciones de arriba: estas eligen, esta
                      hace algo ya. */}
                  <button
                    type="button"
                    onClick={() => void descargarListado()}
                    disabled={descargando}
                    className="rt-opcion disabled:opacity-60"
                    aria-describedby={errorListado ? 'rt-listado-error' : undefined}
                  >
                    <span className="text-2xl shrink-0" aria-hidden="true">📊</span>
                    <span className="min-w-0 flex-1">
                      <span
                        className="block text-[14.5px] font-medium"
                        style={{ color: WA.textoLight }}
                      >
                        {descargando ? 'Preparando la descarga…' : 'Solo quiero el listado'}
                      </span>
                      <span className="block text-[12px]" style={{ color: WA.textoTenueLight }}>
                        Descárgalo en Excel al instante, sin chat
                      </span>
                    </span>
                    <svg
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="shrink-0"
                      style={{ color: WA.headerLight }}
                      aria-hidden="true"
                    >
                      <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 19h16" />
                    </svg>
                  </button>
                </div>
                {errores.motivo && (
                  <p id="rt-motivo-error" className="text-[12px] mt-1.5" style={{ color: '#C6362B' }} role="alert">
                    {errores.motivo}
                  </p>
                )}
                {errorListado && (
                  <p id="rt-listado-error" className="text-[12px] mt-1.5" style={{ color: '#C6362B' }} role="alert">
                    {errorListado}
                  </p>
                )}
              </fieldset>

              <button
                type="submit"
                className="w-full flex items-center justify-center gap-2 py-3 rounded-full text-[15px] font-semibold transition-transform hover:-translate-y-0.5"
                style={{
                  backgroundColor: WA.headerLight,
                  color: '#FFFFFF',
                  boxShadow: '0 3px 10px rgba(0,128,105,0.28)',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 2a10 10 0 0 0-8.7 14.94L2 22l5.2-1.36A10 10 0 1 0 12 2z" />
                </svg>
                Iniciar chat
              </button>

              <p
                className="text-[11px] text-center mt-4 leading-relaxed"
                style={{ color: WA.textoTenueLight }}
              >
                Al iniciar el chat aceptas que usemos los datos que compartas{' '}
                <strong>únicamente</strong> con el fin de reunir a las mascotas perdidas
                con sus dueños. Tu teléfono no se comparte con nadie hasta que alguien
                reconozca a la mascota.
              </p>
            </form>
          </div>
        ) : (
          /* ========================= Chat ========================= */
          <div className="rt-chat flex flex-col flex-1 min-h-0">
            {/* ===== Header ===== */}
            <header
              className="rt-chat-header flex items-center gap-3 px-4 py-2.5 shrink-0"
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
              {/* El detalle del servicio y el aviso de datos ya se leyeron en la
                  antesala; aquí queda solo el recordatorio en una línea. */}
              <div className="flex justify-center mb-4">
                <p
                  className="text-[11.5px] text-center max-w-md px-3.5 py-2 rounded-lg leading-relaxed"
                  style={{
                    backgroundColor: '#FFF3C4',
                    color: '#5B4A00',
                    boxShadow: '0 1px 1px rgba(0,0,0,0.08)',
                  }}
                >
                  🤍 Servicio <strong>gratuito</strong> por el terremoto en Colombia. Tus
                  datos se usan <strong>únicamente</strong> para reunir a las mascotas con
                  sus familias.
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
            <div className="rt-chat-composer shrink-0">
              {aviso && (
                <p
                  className="text-[12px] text-center px-4 py-1.5"
                  style={{ backgroundColor: '#FDECEA', color: '#8A1C12' }}
                  role="alert"
                >
                  {aviso}
                </p>
              )}
              <form
                onSubmit={enviarTexto}
                className="flex items-end gap-2 px-3 py-2.5"
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
            </div>
          </div>
        )}

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
