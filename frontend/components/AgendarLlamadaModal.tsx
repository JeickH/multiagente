/**
 * Modal «Agendar una llamada» con el calendario de Cal.com en un iframe
 * (#625). Lo usan la demo y la landing. Decisiones y controles en
 * `lib/agendarLlamada.ts` (#629):
 *
 *  - El iframe existe SOLO mientras el modal está abierto: al cargar la
 *    página no se pide nada a Cal.
 *  - Nada de `embed.js` ni scripts de Cal en la página. Nunca se le escribe
 *    al iframe por `postMessage`.
 *  - El aviso de reserva se escucha solo con el modal abierto, se valida
 *    (origen fijo, que venga de nuestro iframe, `originator` y tipo) y se
 *    toma una sola vez por apertura. De `data` no se pinta ni guarda nada.
 *  - Accesible: `role=dialog` + `aria-modal`, foco atrapado (incluye el
 *    iframe), Escape cierra (si el foco no está dentro del iframe: ahí el
 *    teclado es de Cal y queda el botón de cerrar), y el foco vuelve a donde
 *    estaba. En celular ocupa toda la pantalla.
 *  - Respaldo: «Ábrelo en otra pestaña» con `noopener,noreferrer`.
 *
 * Va por portal a `<body>`: en la demo se abre desde las slides, cuyo dialog
 * usa `transform`, y ahí un `position: fixed` quedaría atrapado.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { CAL_COLOR_SCHEME, CAL_SANDBOX, TEXTOS_AGENDAR as T, esReservaDeCal, urlCal } from '../lib/agendarLlamada';

const FOCUSABLES =
  'a[href], button:not([disabled]), iframe, input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Marca del DOM para que otros manejadores de teclado sepan que el modal está encima. */
export const ATRIBUTO_MODAL_AGENDAR = 'data-modal-agendar';

interface Props {
  abierto: boolean;
  onCerrar: () => void;
  /** Para prellenar el formulario de Cal. Solo desde la memoria de React. */
  nombre?: string | null;
  correo?: string | null;
  /** Se llama una vez por apertura cuando Cal confirma la reserva. */
  onAgendada?: () => void;
}

export default function AgendarLlamadaModal(props: Props) {
  // El portal necesita `document`: el modal nunca se pinta en el servidor
  // porque solo se abre con un clic.
  if (!props.abierto || typeof document === 'undefined') return null;
  return createPortal(<Modal {...props} />, document.body);
}

function Modal({ onCerrar, nombre, correo, onAgendada }: Props) {
  const dialogo = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  const onAgendadaRef = useRef(onAgendada);
  onAgendadaRef.current = onAgendada;
  const onCerrarRef = useRef(onCerrar);
  onCerrarRef.current = onCerrar;

  const [cargado, setCargado] = useState(false);
  const [lento, setLento] = useState(false);
  const [agendada, setAgendada] = useState(false);

  // La URL se fija al abrir: si cambian los datos con el modal abierto, el
  // iframe no se recarga.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const url = useMemo(() => urlCal({ nombre, correo }), []);

  // Foco al botón de cerrar, sin scroll detrás; al cerrar, todo vuelve.
  useEffect(() => {
    const previo = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    cerrarRef.current?.focus({ preventScroll: true });
    return () => {
      document.body.style.overflow = overflow;
      if (previo && document.contains(previo)) previo.focus({ preventScroll: true });
    };
  }, []);

  // Escape cierra (en captura, para que no lo tome otro manejador de abajo).
  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      onCerrarRef.current();
    };
    window.addEventListener('keydown', alTeclear, true);
    return () => window.removeEventListener('keydown', alTeclear, true);
  }, []);

  // Aviso de reserva: solo con el modal abierto, una vez por apertura.
  useEffect(() => {
    let avisado = false;
    const alMensaje = (e: MessageEvent) => {
      if (avisado) return;
      if (!esReservaDeCal(e, iframeRef.current?.contentWindow)) return;
      avisado = true;
      setAgendada(true);
      onAgendadaRef.current?.();
    };
    window.addEventListener('message', alMensaje);
    return () => window.removeEventListener('message', alMensaje);
  }, []);

  // Si a los 12 s no cargó, se resalta el respaldo.
  useEffect(() => {
    if (cargado) return;
    const t = window.setTimeout(() => setLento(true), 12000);
    return () => window.clearTimeout(t);
  }, [cargado]);

  const atraparFoco = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !dialogo.current) return;
    const els = Array.from(dialogo.current.querySelectorAll<HTMLElement>(FOCUSABLES)).filter(
      (el) => el.offsetParent !== null || el.tagName === 'IFRAME',
    );
    if (els.length === 0) return;
    const primero = els[0];
    const ultimo = els[els.length - 1];
    if (e.shiftKey && document.activeElement === primero) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && document.activeElement === ultimo) {
      e.preventDefault();
      primero.focus();
    }
  };

  const abrirAparte = () => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  return (
    <div {...{ [ATRIBUTO_MODAL_AGENDAR]: '' }} className="fixed inset-0 z-[90]">
      <div className="absolute inset-0 bg-black/70" aria-hidden="true" onClick={onCerrar} />
      <div
        ref={dialogo}
        role="dialog"
        aria-modal="true"
        aria-labelledby="agendar-titulo"
        aria-describedby="agendar-sub"
        onKeyDown={atraparFoco}
        // Mismo fondo que el tema oscuro de Cal (#111111) para que el
        // calendario no se vea como un recuadro pegado.
        className="absolute inset-0 md:inset-auto md:left-1/2 md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-[min(1040px,calc(100vw-3rem))] md:h-[min(780px,calc(100dvh-3rem))] flex flex-col bg-[#111111] md:rounded-3xl md:border md:border-white/15 md:shadow-2xl md:shadow-black/60 overflow-hidden text-gloma-ink-text"
        style={{ fontFamily: 'Inter, system-ui, sans-serif' }}
      >
        <div
          className="shrink-0 flex items-start gap-3 px-4 md:px-6 pb-3 bg-[#111111] border-b border-white/10"
          style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}
        >
          <div className="min-w-0 flex-1">
            <h2
              id="agendar-titulo"
              className="text-lg md:text-xl font-bold text-white leading-tight"
              style={{ fontFamily: 'Syne, system-ui, sans-serif' }}
            >
              {T.titulo}
            </h2>
            <p id="agendar-sub" className="text-xs md:text-sm text-gloma-ink-muted mt-0.5">
              {agendada ? T.agendada : T.subtitulo}
            </p>
          </div>
          <button
            ref={cerrarRef}
            type="button"
            onClick={onCerrar}
            aria-label={T.cerrar}
            className="shrink-0 w-11 h-11 -mr-1 rounded-full flex items-center justify-center text-white/85 bg-white/[0.06] border border-white/15 hover:bg-white/15 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-gloma-mint"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="relative flex-1 min-h-0">
          {!cargado && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm text-gloma-ink-muted" role="status">
              <span className="w-5 h-5 rounded-full border-2 border-gloma-mint border-r-transparent animate-spin motion-reduce:animate-none" aria-hidden="true" />
              {T.cargando}
            </div>
          )}
          <iframe
            ref={iframeRef}
            src={url}
            title={T.iframe}
            sandbox={CAL_SANDBOX}
            allow=""
            referrerPolicy="no-referrer"
            loading="lazy"
            onLoad={() => setCargado(true)}
            style={{ colorScheme: CAL_COLOR_SCHEME }}
            className={`absolute inset-0 w-full h-full border-0 transition-opacity duration-300 ${cargado ? 'opacity-100' : 'opacity-0'}`}
          />
        </div>

        <div
          className="shrink-0 px-4 md:px-6 pt-2 bg-[#111111] border-t border-white/10 text-xs text-center text-gloma-ink-muted"
          style={{ paddingBottom: 'max(8px, env(safe-area-inset-bottom))' }}
        >
          <span className={lento ? 'text-gloma-ink-text' : ''}>{T.lento}</span>{' '}
          <button
            type="button"
            onClick={abrirAparte}
            className="underline text-gloma-mint hover:text-gloma-rose min-h-[32px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-gloma-mint"
          >
            {T.abrirAparte}
            <span className="sr-only">{T.nuevaPestana}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Para páginas sin demo (la landing): una sola instancia del modal escucha
 * este evento de `window`, y cualquier botón (el hero, precios, la barra del
 * celular, el widget de Lía) lo abre con `abrirAgendarLlamada()`. Mismo
 * patrón que `OPEN_CHAT_EVENT` del widget. Aquí no se registran eventos: no
 * hay token de demo.
 */
export const ABRIR_AGENDAR_EVENT = 'gloma:abrir-agendar-llamada';

export function abrirAgendarLlamada() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(ABRIR_AGENDAR_EVENT));
}

export function AgendarLlamadaGlobal() {
  const [abierto, setAbierto] = useState(false);
  useEffect(() => {
    const abrir = () => setAbierto(true);
    window.addEventListener(ABRIR_AGENDAR_EVENT, abrir);
    return () => window.removeEventListener(ABRIR_AGENDAR_EVENT, abrir);
  }, []);
  return <AgendarLlamadaModal abierto={abierto} onCerrar={() => setAbierto(false)} />;
}
