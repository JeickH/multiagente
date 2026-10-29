/**
 * Etapa 3: ventana tipo WhatsApp con el bot de la demo (+ panel lateral en
 * escritorio).
 *
 * Del wireframe #611:
 *  - El prospecto escribe primero: el hilo arranca vacío y `mensaje_sugerido`
 *    es el `value` del cuadro, SIN enviar. El foco inicial va al botón de
 *    enviar (enfocar el cuadro abre el teclado del celular y tapa el chat). La
 *    marca guía y el anillo del botón desaparecen al primer envío o al editar.
 *  - Varias `actions` se muestran una por una con «escribiendo…» entre ellas.
 *  - El texto del bot se pinta SOLO con `formatearWhatsapp` (nodos de React,
 *    sin HTML ni autolinks) dentro de un contenedor `whitespace-pre-wrap`.
 *  - Falla de red al enviar: la burbuja queda con «No se envió. Toca para
 *    reintentar» y el reintento reusa el mismo texto.
 *  - `handoff` o `finished` → tarjeta de sistema + CTA en el hilo, y la barra
 *    «La demo terminó · Agendar con Gloma» reemplaza al cuadro de texto.
 *  - El CTA de Gloma nunca flota sobre los mensajes.
 *
 * Avisos de #608: la cabecera lleva fijo «Demostración generada con IA ·
 * productos y precios ficticios», y el hilo arranca con el aviso de que la
 * conversación se guarda y de no compartir datos personales reales.
 *
 * Reporte de ejemplo (2026-10-28): «Ver reporte de ejemplo» abre `DemoReporte`
 * (datos ficticios). En escritorio está en el panel lateral; en el celular, el
 * botón de barras de la cabecera y el desplegable «Ideas». Al terminar la
 * demo, también en la tarjeta de cierre.
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { DEMO_COPY, DEMO_UI, rellenarCopy } from '../../lib/demo_copy';
import {
  DemoApiError,
  enviarChat,
  type ChatGuardado,
  type CheckMensaje,
  type FinDemo,
  type MensajeChat,
  type ProductoDemo,
} from '../../lib/demoApi';
import { inicialesEmpresa } from '../../lib/demoFormulario';
import { REPORTE_TEXTOS } from '../../lib/demoReporte';
import { horaCorta } from '../../lib/fechas';
import { formatearWhatsapp } from '../../lib/formatoWhatsapp';
import CtaAgendar, { type AccionesAgendar } from './CtaAgendar';
import DemoNoDisponible from './DemoNoDisponible';
import DemoReporte from './DemoReporte';
import MenuContacto from './MenuContacto';
import PanelLateral, { ListaIdeas } from './PanelLateral';
import { Check, IconoAsesor, IconoError, IconoEnviar, IconoFlecha, IconoInfo, IconoReporte } from './iconos';

const U = DEMO_UI;

const esperar = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const ahora = () => horaCorta(new Date().toISOString());

function Burbuja({
  m,
  empresa,
  onReintentar,
  reintentoBloqueado,
}: {
  m: MensajeChat;
  empresa: string;
  onReintentar: (m: MensajeChat) => void;
  reintentoBloqueado: boolean;
}) {
  if (m.de === 'bot') {
    return (
      <div className="flex justify-start demo-entra">
        <div className="demo-b-in max-w-[80%] px-3 py-1.5 text-[14.5px] leading-snug">
          <span className="sr-only">{empresa}: </span>
          <span className="whitespace-pre-wrap break-words">{formatearWhatsapp(m.texto)}</span>
          <span className="demo-b-meta">{m.hora}</span>
        </div>
      </div>
    );
  }
  const check: CheckMensaje = m.check || 'leido';
  return (
    <div className="flex flex-col items-end demo-entra">
      <div className="demo-b-out max-w-[80%] px-3 py-1.5 text-[14.5px] leading-snug">
        <span className="whitespace-pre-wrap break-words">{m.texto}</span>
        <span className="demo-b-meta">
          {m.hora}{' '}
          {check === 'error' ? (
            <span className="text-gloma-ink-err">
              <IconoError size={14} className="shrink-0" />
            </span>
          ) : (
            <>
              <Check doble={check !== 'enviado'} leido={check === 'leido'} />
              <span className="sr-only">
                {check === 'enviado' ? U.chat.checkEnviado : check === 'entregado' ? U.chat.checkEntregado : U.chat.checkLeido}
              </span>
            </>
          )}
        </span>
      </div>
      {check === 'error' && (
        <button
          type="button"
          onClick={() => onReintentar(m)}
          disabled={reintentoBloqueado}
          className="mt-1 text-xs text-gloma-ink-err flex items-center gap-1 min-h-[32px] px-1 disabled:opacity-50"
        >
          {U.chat.noEnviado} <span className="underline">{U.chat.reintentar}</span>
        </button>
      )}
    </div>
  );
}

export default function DemoChat({
  demoId,
  token,
  empresa,
  productos,
  mensajeSugerido,
  inicial,
  onPersistir,
  noDisponible,
  onNoDisponible,
  onNuevaDemo,
  acciones,
}: {
  demoId: string;
  token: string;
  empresa: string;
  productos: ProductoDemo[];
  mensajeSugerido: string;
  /** Hilo recuperado de `sessionStorage` tras una recarga. */
  inicial?: ChatGuardado;
  onPersistir: (chat: ChatGuardado) => void;
  noDisponible: boolean;
  onNoDisponible: () => void;
  onNuevaDemo: () => void;
  acciones: AccionesAgendar;
}) {
  const yaHabiaHilo = Boolean(inicial && inicial.mensajes.length > 0);
  const [mensajes, setMensajes] = useState<MensajeChat[]>(inicial?.mensajes ?? []);
  const [fin, setFin] = useState<FinDemo>(inicial?.fin ?? null);
  const [texto, setTexto] = useState(yaHabiaHilo ? '' : mensajeSugerido);
  const [guia, setGuia] = useState(!yaHabiaHilo);
  const [pendiente, setPendiente] = useState(false);
  const [escribiendo, setEscribiendo] = useState(false);
  const [anuncio, setAnuncio] = useState('');
  const [ideasAbiertas, setIdeasAbiertas] = useState(false);
  const [reporteAbierto, setReporteAbierto] = useState(false);

  const idRef = useRef(mensajes.reduce((max, m) => Math.max(max, m.id), 0));
  const vivo = useRef(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const enviarRef = useRef<HTMLButtonElement>(null);

  const datos = { empresa };

  useEffect(() => {
    vivo.current = true;
    return () => {
      vivo.current = false;
    };
  }, []);

  // Foco inicial en el botón de enviar (no en el cuadro: abriría el teclado).
  useEffect(() => {
    if (!yaHabiaHilo && !inicial?.fin) enviarRef.current?.focus({ preventScroll: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persistencia en sessionStorage (la hace DemoPage).
  useEffect(() => {
    onPersistir({ fin, mensajes });
  }, [mensajes, fin, onPersistir]);

  // Bajar al último mensaje.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [mensajes, escribiendo, fin]);

  // El cuadro crece hasta 120 px.
  useLayoutEffect(() => {
    const t = textareaRef.current;
    if (!t) return;
    t.style.height = 'auto';
    t.style.height = `${Math.min(t.scrollHeight, 120)}px`;
  }, [texto]);

  const ideas = useMemo(() => {
    const p = productos[1] || productos[0];
    return U.chat.ideas
      .map((idea) => (idea.includes('{producto}') ? (p ? idea.replace('{producto}', p.nombre) : '') : idea))
      .filter(Boolean);
  }, [productos]);

  const agregar = (m: Omit<MensajeChat, 'id'>): number => {
    idRef.current += 1;
    const id = idRef.current;
    setMensajes((prev) => [...prev, { ...m, id }]);
    return id;
  };
  const marcar = (id: number, check: CheckMensaje) =>
    setMensajes((prev) => prev.map((m) => (m.id === id ? { ...m, check } : m)));

  const terminar = useCallback(
    (tipo: Exclude<FinDemo, null>) => {
      setFin(tipo);
      setAnuncio(tipo === 'handoff' ? rellenarCopy(U.chat.anuncioHandoff, { empresa }) : U.chat.anuncioFin);
    },
    [empresa],
  );

  const enviar = async (contenido: string, reintento?: MensajeChat) => {
    const limpio = contenido.trim();
    if (!limpio || pendiente || fin || noDisponible) return;
    setGuia(false);
    setAnuncio('');

    let id: number;
    if (reintento) {
      id = reintento.id;
      marcar(id, 'enviado');
    } else {
      id = agregar({ de: 'yo', texto: limpio, hora: ahora(), check: 'enviado' });
      setTexto('');
    }
    setPendiente(true);

    // Checks como en WhatsApp: ✓ enviado → ✓✓ entregado → ✓✓ leído + «escribiendo…».
    const timers = [
      window.setTimeout(() => marcar(id, 'entregado'), 350),
      window.setTimeout(() => {
        marcar(id, 'leido');
        setEscribiendo(true);
        setAnuncio(rellenarCopy(U.chat.anuncioEscribiendo, datos));
      }, 900),
    ];

    let res;
    try {
      // Solo `{message}`: historial y contador de turnos viven en el servidor.
      res = await enviarChat(demoId, token, limpio);
    } catch (e) {
      timers.forEach((t) => window.clearTimeout(t));
      if (!vivo.current) return;
      setEscribiendo(false);
      setPendiente(false);
      const status = e instanceof DemoApiError ? e.status : 0;
      if (status === 404) {
        onNoDisponible();
        return;
      }
      if (status === 429) {
        // El tope de turnos llega como `finished=true`; un 429 se trata igual.
        marcar(id, 'leido');
        terminar('finished');
        return;
      }
      marcar(id, 'error');
      setAnuncio(U.chat.anuncioNoEnviado);
      return;
    }

    timers.forEach((t) => window.clearTimeout(t));
    if (!vivo.current) return;
    marcar(id, 'leido');

    const partes = res.actions.map((a) => a.text.trim()).filter(Boolean);
    for (let i = 0; i < partes.length; i += 1) {
      setEscribiendo(true);
      await esperar(i === 0 ? 400 : 900);
      if (!vivo.current) return;
      setEscribiendo(false);
      agregar({ de: 'bot', texto: partes[i], hora: ahora() });
      if (i < partes.length - 1) await esperar(250);
    }
    setEscribiendo(false);
    if (res.handoff) terminar('handoff');
    else if (res.finished) terminar('finished');
    setPendiente(false);
  };

  const alEnviar = (e: React.FormEvent) => {
    e.preventDefault();
    void enviar(texto);
  };

  const alTeclear = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter envía y Shift+Enter hace salto, solo en escritorio.
    if (e.key === 'Enter' && !e.shiftKey && window.matchMedia('(min-width: 768px)').matches) {
      e.preventDefault();
      void enviar(texto);
    }
  };

  const alElegirIdea = (idea: string) => {
    if (fin) return;
    setTexto(idea);
    setGuia(false);
    setIdeasAbiertas(false);
    textareaRef.current?.focus();
  };

  const bloqueado = Boolean(fin) || noDisponible;

  return (
    <div className="h-full md:max-w-5xl md:mx-auto md:p-6 md:grid md:grid-cols-[320px_1fr] md:gap-6">
      <PanelLateral
        empresa={empresa}
        productos={productos}
        ideas={ideas}
        onIdea={alElegirIdea}
        ideasDeshabilitadas={bloqueado}
        acciones={acciones}
        onReporte={() => setReporteAbierto(true)}
      />

      <div className="relative h-full flex flex-col min-h-0 md:rounded-3xl overflow-hidden md:border md:border-gloma-mint/20 md:shadow-2xl bg-gloma-ink-alt">
        {/* ChatHeader */}
        <header className="shrink-0 bg-gloma-brown-dark" style={{ paddingTop: 'max(10px, env(safe-area-inset-top))' }}>
          <div className="flex items-center gap-3 px-3 pb-2">
            <span
              className="w-10 h-10 rounded-full bg-gloma-mint text-gloma-ink font-heading font-extrabold flex items-center justify-center shrink-0 text-sm"
              aria-hidden="true"
            >
              {inicialesEmpresa(empresa)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 min-w-0">
                <span className="font-semibold text-white truncate">{empresa}</span>
                <span className="shrink-0 text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-white/15 text-white">
                  {U.chat.etiquetaDemo}
                </span>
              </p>
              <p className={`text-xs truncate ${escribiendo ? 'text-gloma-rose' : 'text-white/75'}`} aria-hidden="true">
                {escribiendo ? U.chat.escribiendo : U.chat.enLinea}
              </p>
            </div>
            {/* Reporte de ejemplo: en el celular, solo el ícono (en escritorio está en el panel). */}
            <button
              type="button"
              onClick={() => setReporteAbierto(true)}
              aria-haspopup="dialog"
              aria-label={REPORTE_TEXTOS.boton}
              title={REPORTE_TEXTOS.boton}
              className="md:hidden shrink-0 w-9 h-9 rounded-full border border-white/50 text-white flex items-center justify-center hover:bg-white/10"
            >
              <IconoReporte />
            </button>
            {/* #634: menú con las dos salidas (llamada y asesor). */}
            <MenuContacto acciones={acciones} />
          </div>
          {/* Aviso fijo de #608 (M4): no se cierra ni se desplaza con el hilo. */}
          <p className="px-3 py-1 text-[11px] leading-snug text-white/85 bg-black/20 text-center">{U.chat.avisoIA}</p>
        </header>

        {/* LineaAyuda */}
        <div className="shrink-0 bg-gloma-mint/10 border-b border-gloma-mint/20 px-3 py-2">
          <div className="flex items-center gap-2">
            <IconoInfo />
            <p className="text-[13px] text-gloma-ink-text flex-1 leading-snug break-words">
              {rellenarCopy(U.chat.ayudaLinea, datos)}
            </p>
            <button
              type="button"
              className="md:hidden shrink-0 text-xs font-semibold text-gloma-mint px-2 min-h-[36px] flex items-center gap-1"
              aria-expanded={ideasAbiertas}
              aria-controls="ayuda-detalle"
              onClick={() => setIdeasAbiertas((v) => !v)}
            >
              {U.chat.ideasBoton}
              <IconoFlecha dir="abajo" size={12} />
            </button>
          </div>
          <div id="ayuda-detalle" className="md:hidden pt-2 pb-1" hidden={!ideasAbiertas}>
            <p className="text-xs text-gloma-ink-muted mb-1.5">{U.chat.ideasTitulo}</p>
            <ListaIdeas ideas={ideas} onIdea={alElegirIdea} deshabilitado={bloqueado} />
            {productos.length > 0 && (
              <>
                <p className="text-xs text-gloma-ink-muted mt-3">{U.chat.panelProductos}</p>
                <ul className="mt-1 space-y-1 text-xs text-gloma-ink-text">
                  {productos.map((p) => (
                    <li key={p.nombre}>· {p.nombre}</li>
                  ))}
                </ul>
              </>
            )}
            <button
              type="button"
              onClick={() => setReporteAbierto(true)}
              aria-haspopup="dialog"
              className="mt-3 inline-flex items-center gap-2 min-h-[36px] px-3 rounded-full border border-gloma-mint/60 text-gloma-mint text-xs font-semibold"
            >
              <IconoReporte size={14} />
              {REPORTE_TEXTOS.boton}
            </button>
          </div>
        </div>

        {/* Mensajes */}
        <div ref={scrollRef} className="relative flex-1 min-h-0 overflow-y-auto demo-fondo-chat px-3 md:px-5 py-4">
          <div className="flex justify-center">
            <span className="text-[11px] font-semibold uppercase px-3 py-1 rounded-lg demo-chip-sis">{U.chat.hoy}</span>
          </div>
          <div className="flex justify-center mt-3">
            <p className="max-w-[92%] md:max-w-[80%] text-center text-[12px] leading-snug px-3 py-2 rounded-lg demo-chip-sis">
              {U.chat.avisoSistema}
            </p>
          </div>

          <div role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversación" className="mt-3 space-y-1.5">
            {mensajes.map((m) => (
              <Burbuja
                key={m.id}
                m={m}
                empresa={empresa}
                onReintentar={(msg) => void enviar(msg.texto, msg)}
                reintentoBloqueado={pendiente || bloqueado}
              />
            ))}
          </div>

          {escribiendo && (
            <div className="flex justify-start mt-1.5" aria-hidden="true">
              <div className="demo-b-in px-3.5 py-3 demo-tecleo">
                <span /> <span /> <span />
              </div>
            </div>
          )}

          {fin && (
            <div className="space-y-3 mt-4">
              <div className="flex justify-center demo-entra">
                <div className="max-w-[92%] md:max-w-[80%] text-center text-[13px] leading-snug px-4 py-3 rounded-2xl demo-chip-sis">
                  {fin === 'handoff' ? (
                    <>
                      <IconoAsesor />
                      <b className="block text-white">{DEMO_COPY.chat.traspaso.titulo}</b>
                      <span className="block mt-1 text-gloma-ink-muted">
                        {rellenarCopy(DEMO_COPY.chat.traspaso.texto, datos)}
                      </span>
                    </>
                  ) : (
                    <>
                      <b className="block text-white">{U.chat.finTitulo}</b>
                      <span className="block mt-1 text-gloma-ink-muted">{U.chat.finTexto}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="demo-entra rounded-2xl bg-gloma-forest border border-gloma-mint/30 p-4 max-w-sm mx-auto">
                <p className="font-heading font-bold text-white text-lg leading-snug">{U.cta.finTitulo}</p>
                <p className="text-[13px] text-white/80 mt-1">{U.cta.finTexto}</p>
                <CtaAgendar acciones={acciones} variante="bloque" className="mt-3" />
                <button
                  type="button"
                  onClick={() => setReporteAbierto(true)}
                  aria-haspopup="dialog"
                  className="mt-2 w-full inline-flex items-center justify-center gap-2 min-h-[44px] px-4 text-sm font-semibold text-gloma-rose underline underline-offset-4 hover:text-white"
                >
                  <IconoReporte />
                  {REPORTE_TEXTOS.boton}
                </button>
              </div>
            </div>
          )}
        </div>

        <p role="status" className="sr-only">
          {anuncio}
        </p>

        {fin ? (
          <div
            className="shrink-0 px-3 pt-3 bg-gloma-ink border-t border-white/10 flex items-center gap-3"
            style={{ paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
          >
            <p className="flex-1 min-w-0 text-[13px] text-gloma-ink-muted">{U.chat.finBarra}</p>
            <CtaAgendar acciones={acciones} variante="barra" className="shrink-0" />
          </div>
        ) : (
          <form
            onSubmit={alEnviar}
            className="relative shrink-0 flex items-end gap-2 px-2.5 pt-2.5 bg-gloma-ink border-t border-white/10"
            style={{ paddingBottom: 'max(10px, env(safe-area-inset-bottom))' }}
          >
            {guia && (
              <div
                className="absolute right-2 bottom-full mb-2 max-w-[240px] rounded-2xl bg-gloma-mint text-gloma-ink text-[13px] font-medium px-3 py-2 shadow-lg demo-entra"
                aria-hidden="true"
              >
                {DEMO_COPY.chat.ayuda}
                <span className="absolute -bottom-1.5 right-5 w-3 h-3 bg-gloma-mint rotate-45" />
              </div>
            )}
            <label htmlFor="demo-msg" className="sr-only">
              {rellenarCopy(U.chat.etiquetaMensaje, datos)}
            </label>
            <textarea
              id="demo-msg"
              ref={textareaRef}
              rows={1}
              maxLength={500}
              enterKeyHint="send"
              aria-describedby={guia ? 'demo-msg-ayuda' : undefined}
              value={texto}
              disabled={noDisponible}
              onChange={(e) => {
                setTexto(e.target.value);
                setGuia(false);
              }}
              onKeyDown={alTeclear}
              placeholder={U.chat.placeholder}
              className="flex-1 min-h-[44px] max-h-[120px] resize-none px-4 py-2.5 rounded-[22px] bg-gloma-ink-surface text-[15px] leading-snug text-gloma-ink-text border border-white/10 focus:outline-none focus:border-gloma-mint placeholder:text-white/45"
            />
            <p id="demo-msg-ayuda" className="sr-only">
              {U.chat.sugeridoSr}
            </p>
            <button
              ref={enviarRef}
              type="submit"
              disabled={!texto.trim() || pendiente || noDisponible}
              aria-label={U.chat.enviar}
              className={`w-11 h-11 rounded-full bg-gloma-mint text-gloma-ink flex items-center justify-center shrink-0 disabled:opacity-40 disabled:cursor-not-allowed ${
                guia ? 'ring-4 ring-gloma-mint/30 demo-pulso' : ''
              }`}
            >
              <IconoEnviar />
            </button>
          </form>
        )}

        {noDisponible && <DemoNoDisponible cubrir onNuevaDemo={onNuevaDemo} acciones={acciones} />}
      </div>

      {reporteAbierto && (
        <DemoReporte
          empresa={empresa}
          onCerrar={() => setReporteAbierto(false)}
          onAgendar={() => {
            setReporteAbierto(false);
            acciones.abrirLlamada();
          }}
        />
      )}
    </div>
  );
}
