/**
 * Detalle de una demo (#630): panel lateral de 600 px en escritorio, pantalla
 * completa en celular. Se pide `GET /admin/demos/{public_id}` al abrir.
 *
 * Seguridad (#629):
 *  - Nombre, empresa, «otro», productos y transcripción son texto de terceros:
 *    se pintan como texto de React. La negrilla de WhatsApp sale de
 *    `formatearWhatsapp` (nodos, sin HTML) y NO hay autolinks: una URL o un
 *    teléfono que escribió el visitante queda como texto plano.
 *  - Las acciones con datos personales (WhatsApp y copiar correo) viven solo
 *    aquí, una demo a la vez, junto al consentimiento. wa.me con
 *    `rel="noopener noreferrer"`. Nada de exportar ni de selección múltiple.
 *
 * Teclado: al abrir, foco al título; Esc cierra; ← → recorren la página
 * actual de la lista; Tab no sale del panel.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, authedFetch } from '../../lib/api';
import {
  cuando,
  enlaceWhatsappProspecto,
  formatoCop,
  hiloConMarcas,
  primerNombre,
  tipoTexto,
  type DetalleDemo as Detalle,
} from '../../lib/demosAdmin';
import { fechaHoraCorta, horaCorta } from '../../lib/fechas';
import { formatearWhatsapp } from '../../lib/formatoWhatsapp';
import { BadgeEstado, Esq, EtiquetaInterna, Spin } from './piezas';

const FOCUSABLES =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

type Tab = 'datos' | 'chat';

function Paso({ hecho, texto, hora, extra }: { hecho: boolean; texto: string; hora?: string; extra?: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        className={`mt-0.5 w-5 h-5 shrink-0 rounded-full flex items-center justify-center text-[11px] ${
          hecho ? 'bg-gloma-brown text-white' : 'border border-gloma-rose text-gloma-brown-light'
        }`}
        aria-hidden="true"
      >
        {hecho ? '✓' : ''}
      </span>
      <span className={`flex-1 text-sm ${hecho ? 'text-gloma-brown' : 'text-gloma-brown-light'}`}>
        {texto}
        {extra}
        <span className="sr-only">{hecho ? ': sí' : ': no'}</span>
      </span>
      <span className="text-xs text-gloma-brown-light whitespace-nowrap">{hecho ? hora || '' : 'no'}</span>
    </li>
  );
}

export default function DetalleDemo({
  publicId,
  posicion,
  hayAnterior,
  haySiguiente,
  onMover,
  onCerrar,
  onAviso,
}: {
  publicId: string;
  /** «2 de 20 en esta página», o vacío si la demo no está en la página. */
  posicion: string;
  hayAnterior: boolean;
  haySiguiente: boolean;
  onMover: (delta: -1 | 1) => void;
  onCerrar: () => void;
  onAviso: (texto: string) => void;
}) {
  const [d, setD] = useState<Detalle | null>(null);
  const [error, setError] = useState<'404' | 'otro' | null>(null);
  const [tab, setTab] = useState<Tab>('datos');
  const [intento, setIntento] = useState(0);
  const panel = useRef<HTMLDivElement>(null);
  const titulo = useRef<HTMLHeadingElement>(null);
  const onCerrarRef = useRef(onCerrar);
  onCerrarRef.current = onCerrar;
  const onMoverRef = useRef(onMover);
  onMoverRef.current = onMover;

  // Carga (y recarga cada 5 s, máx. 1 min, si sigue generando).
  useEffect(() => {
    let vivo = true;
    let timer: number | undefined;
    const inicio = Date.now();
    setD(null);
    setError(null);
    setTab('datos');
    const cargar = async () => {
      try {
        const res = await authedFetch<Detalle>(`/admin/demos/${encodeURIComponent(publicId)}`);
        if (!vivo) return;
        setD(res);
        if (res.estado === 'generando' && Date.now() - inicio < 60000) timer = window.setTimeout(cargar, 5000);
      } catch (e) {
        if (!vivo) return;
        setError(e instanceof ApiError && e.status === 404 ? '404' : 'otro');
      }
    };
    void cargar();
    return () => {
      vivo = false;
      window.clearTimeout(timer);
    };
  }, [publicId, intento]);

  // Foco al título cuando llega (o cambia) la demo.
  useEffect(() => {
    if (d || error) titulo.current?.focus({ preventScroll: true });
  }, [d?.public_id, error]); // eslint-disable-line react-hooks/exhaustive-deps

  // Esc cierra; ← → recorren la página (si el foco no está en un campo).
  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCerrarRef.current();
        return;
      }
      if (/INPUT|SELECT|TEXTAREA/.test((e.target as HTMLElement).tagName)) return;
      if (e.key === 'ArrowLeft') onMoverRef.current(-1);
      if (e.key === 'ArrowRight') onMoverRef.current(1);
    };
    window.addEventListener('keydown', alTeclear);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', alTeclear);
      document.body.style.overflow = overflow;
    };
  }, []);

  const atraparFoco = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !panel.current) return;
    const els = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLES)).filter((el) => el.offsetParent !== null);
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

  const copiarCorreo = useCallback(
    async (correo: string) => {
      try {
        await navigator.clipboard.writeText(correo);
        onAviso('Correo copiado');
      } catch {
        onAviso('No se pudo copiar el correo');
      }
    },
    [onAviso],
  );

  const tabClase = (activa: boolean) =>
    `px-3 py-2 text-sm font-medium border-b-2 -mb-px ${
      activa ? 'border-gloma-brown text-gloma-brown' : 'border-transparent text-gloma-brown-light hover:text-gloma-brown'
    }`;

  const mensajesProspecto = d ? d.transcripcion.filter((m) => m.rol === 'usuario').length : 0;

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={onCerrar} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="det-titulo"
        onKeyDown={atraparFoco}
        className="absolute right-0 top-0 h-full w-full md:w-[600px] bg-white shadow-2xl flex flex-col font-body"
      >
        {/* Cabecera fija */}
        <div className="border-b border-gloma-rose-soft px-4 md:px-6 pt-4 pb-3">
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onMover(-1)}
                disabled={!hayAnterior}
                className="px-2.5 py-1 rounded-lg text-sm border border-gloma-rose-soft text-gloma-brown disabled:opacity-40"
                aria-label="Demo anterior"
              >
                ←
              </button>
              <button
                type="button"
                onClick={() => onMover(1)}
                disabled={!haySiguiente}
                className="px-2.5 py-1 rounded-lg text-sm border border-gloma-rose-soft text-gloma-brown disabled:opacity-40"
                aria-label="Demo siguiente"
              >
                →
              </button>
              <span className="text-xs text-gloma-brown-light ml-2">{posicion}</span>
            </div>
            <button
              type="button"
              onClick={onCerrar}
              className="w-9 h-9 rounded-full hover:bg-gloma-rose-soft text-gloma-brown text-xl leading-none"
              aria-label="Cerrar"
            >
              ×
            </button>
          </div>
          {d ? (
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2
                  id="det-titulo"
                  ref={titulo}
                  tabIndex={-1}
                  className="font-heading text-xl font-bold text-gloma-brown break-words focus:outline-none"
                >
                  {d.empresa}
                </h2>
                <p className="text-xs text-gloma-brown-light mt-0.5 break-words">
                  {tipoTexto(d)} · creada {cuando(d.created_at).toLowerCase()}
                  {d.interna && (
                    <>
                      {' '}
                      · <EtiquetaInterna />
                    </>
                  )}
                </p>
              </div>
              <BadgeEstado item={d} />
            </div>
          ) : error ? (
            <h2 id="det-titulo" ref={titulo} tabIndex={-1} className="font-heading text-xl font-bold text-gloma-brown focus:outline-none">
              Demo
            </h2>
          ) : (
            <div aria-hidden="true">
              <Esq className="h-6 w-2/3 mb-2" />
              <Esq className="h-3 w-1/2" />
              <h2 id="det-titulo" className="sr-only">
                Cargando la demo
              </h2>
            </div>
          )}
          {d && (
            <nav className="flex gap-2 mt-3 -mb-3" aria-label="Secciones del detalle">
              <button type="button" className={tabClase(tab === 'datos')} aria-current={tab === 'datos' ? 'page' : undefined} onClick={() => setTab('datos')}>
                Datos y productos
              </button>
              <button type="button" className={tabClase(tab === 'chat')} aria-current={tab === 'chat' ? 'page' : undefined} onClick={() => setTab('chat')}>
                Conversación <span className="text-xs">({mensajesProspecto})</span>
              </button>
            </nav>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="p-6">
              <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
                {error === '404' ? 'Esta demo ya no existe.' : '⚠ No pudimos abrir esta demo. Intenta de nuevo en un momento.'}{' '}
                {error === 'otro' && (
                  <button type="button" className="underline font-semibold ml-1" onClick={() => setIntento((n) => n + 1)}>
                    Reintentar
                  </button>
                )}
              </p>
            </div>
          )}
          {!d && !error && (
            <div className="p-6 space-y-3" aria-hidden="true">
              <Esq className="h-24 w-full" />
              <Esq className="h-24 w-full" />
            </div>
          )}
          {d && tab === 'datos' && <PestanaDatos d={d} onCopiar={copiarCorreo} />}
          {d && tab === 'chat' && <PestanaConversacion d={d} />}
        </div>
      </div>
    </div>
  );
}

function PestanaDatos({ d, onCopiar }: { d: Detalle; onCopiar: (correo: string) => void }) {
  const wa = d.lead_borrado ? null : enlaceWhatsappProspecto(d.telefono, d.nombre);
  const primerMensaje = d.transcripcion.find((m) => m.rol === 'usuario');

  const prospecto = d.lead_borrado ? (
    <>
      <div className="rounded-xl border border-gloma-rose-soft bg-gloma-cream p-4 text-sm text-gloma-brown-light">
        Los datos de contacto de este prospecto se borraron por la política de retención. Se conserva la demo, sus productos y la
        conversación.
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button type="button" disabled className="px-4 py-2 rounded-full text-sm font-semibold bg-gloma-brown text-white opacity-40 cursor-not-allowed">
          Escribir por WhatsApp
        </button>
        <button type="button" disabled className="px-4 py-2 rounded-full text-sm border border-gloma-rose text-gloma-brown opacity-40 cursor-not-allowed">
          Copiar correo
        </button>
      </div>
    </>
  ) : (
    <>
      <dl className="grid grid-cols-[8.5rem_1fr] gap-x-3 gap-y-2 text-sm">
        <dt className="text-gloma-brown-light">Nombre</dt>
        <dd className="text-gloma-brown font-medium break-words">{d.nombre}</dd>
        <dt className="text-gloma-brown-light">Correo</dt>
        <dd className="text-gloma-brown break-all">{d.correo}</dd>
        <dt className="text-gloma-brown-light">Teléfono</dt>
        <dd className="text-gloma-brown tabular-nums">{d.telefono}</dd>
        <dt className="text-gloma-brown-light">Autorizó contacto</dt>
        <dd className="text-gloma-brown">
          {fechaHoraCorta(d.acepto_contacto_at, '—')}
          {d.consent_version && (
            <>
              {' '}
              · texto <code className="text-xs">{d.consent_version}</code>
            </>
          )}
        </dd>
        <dt className="text-gloma-brown-light">Promociones</dt>
        <dd>
          {d.acepta_promociones ? (
            <span className="text-gloma-brown font-medium">
              Sí aceptó{d.acepta_promociones_at ? ` · ${fechaHoraCorta(d.acepta_promociones_at)}` : ''}
            </span>
          ) : (
            <span className="text-gloma-brown-light">No aceptó</span>
          )}
        </dd>
      </dl>
      <div className="flex flex-wrap gap-2 mt-4">
        {wa ? (
          <a
            href={wa}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold bg-gloma-brown text-white hover:opacity-90"
          >
            Escribir por WhatsApp <span aria-hidden="true">↗</span>
            <span className="sr-only"> (se abre en otra pestaña)</span>
          </a>
        ) : (
          <button type="button" disabled className="px-4 py-2 rounded-full text-sm font-semibold bg-gloma-brown text-white opacity-40 cursor-not-allowed">
            Escribir por WhatsApp
          </button>
        )}
        {d.correo && (
          <button
            type="button"
            onClick={() => onCopiar(d.correo as string)}
            className="px-4 py-2 rounded-full text-sm font-medium border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft"
          >
            Copiar correo
          </button>
        )}
      </div>
      {!d.acepta_promociones && (
        <p className="mt-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Solo seguimiento de su demo. No aceptó promociones: no lo agregues a campañas.
        </p>
      )}
    </>
  );

  return (
    <div className="p-4 md:p-6 space-y-7">
      <section>
        <h3 className="font-heading font-bold text-gloma-brown mb-3">Prospecto</h3>
        {prospecto}
      </section>

      {d.estado === 'lista' && (
        <section>
          <h3 className="font-heading font-bold text-gloma-brown mb-3">Recorrido</h3>
          <ol className="space-y-2.5">
            <Paso hecho texto="Creó la demo" hora={horaCorta(d.created_at)} />
            <Paso
              hecho
              texto="Su bot quedó listo"
              hora={horaCorta(d.lista_at)}
              extra={d.origen_productos === 'respaldo' ? <span className="text-xs text-amber-800"> (con productos de respaldo)</span> : null}
            />
            <Paso
              hecho={d.turnos > 0}
              texto="Escribió en el chat"
              hora={horaCorta(primerMensaje?.at ?? null)}
              extra={d.turnos > 0 ? <span className="text-xs text-gloma-brown-light"> ({d.turnos} mensajes)</span> : null}
            />
            <Paso hecho={Boolean(d.traspaso_at)} texto="Llegó al traspaso a asesor" hora={horaCorta(d.traspaso_at)} />
            <Paso
              hecho={d.clics_whatsapp > 0}
              texto="Hizo clic en WhatsApp"
              hora={horaCorta(d.primer_clic_whatsapp_at)}
              extra={d.clics_whatsapp > 1 ? <span className="text-xs text-gloma-brown-light"> ({d.clics_whatsapp} veces)</span> : null}
            />
            <Paso
              hecho={d.aperturas_llamada > 0}
              texto="Abrió el agendador"
              hora={horaCorta(d.primer_apertura_llamada_at)}
              extra={d.aperturas_llamada > 1 ? <span className="text-xs text-gloma-brown-light"> ({d.aperturas_llamada} veces)</span> : null}
            />
            <Paso
              hecho={Boolean(d.llamada_agendada_at)}
              texto="Agendó una llamada"
              hora={horaCorta(d.llamada_agendada_at)}
              extra={<span className="text-xs text-gloma-brown-light"> · reportada por el navegador</span>}
            />
          </ol>
        </section>
      )}

      <section>
        <h3 className="font-heading font-bold text-gloma-brown mb-3">Los productos de su bot</h3>
        <div className="space-y-2">
          {d.estado === 'generando' && (
            <>
              <p className="text-sm text-gloma-brown-light flex items-center gap-2 mb-3">
                <Spin />
                El bot de esta demo se está armando. Esto se actualiza solo mientras tengas el panel abierto.
              </p>
              <Esq className="h-20 w-full" />
            </>
          )}
          {d.estado === 'error' && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              ⚠ La generación falló y el prospecto vio el aviso de error de la demo; no llegó a tener bot. Si dejó sus datos, vale la
              pena escribirle.
            </p>
          )}
          {d.bot_eliminado_at && (
            <div className="text-xs text-gloma-brown-light bg-gloma-cream border border-gloma-rose-soft rounded-lg px-3 py-2 mb-3">
              <p>
                Bot eliminado el {fechaHoraCorta(d.bot_eliminado_at, '—')} (los datos del prospecto se conservan). Estos son los
                productos que tenía.
              </p>
              {d.uso_resumen && (
                <p className="mt-1">
                  Consumo: {d.uso_resumen.turnos} mensajes · {d.uso_resumen.decisiones} respuestas del modelo ·{' '}
                  {(d.uso_resumen.tokens_in + d.uso_resumen.cache_read + d.uso_resumen.cache_write).toLocaleString('es-CO')} tokens de
                  entrada y {d.uso_resumen.tokens_out.toLocaleString('es-CO')} de salida
                  {d.uso_resumen.costo_usd_estimado !== null &&
                    ` · ≈ US$ ${d.uso_resumen.costo_usd_estimado.toLocaleString('es-CO', { maximumFractionDigits: 3 })}`}
                </p>
              )}
            </div>
          )}
          {d.estado === 'lista' && d.origen_productos === 'respaldo' && (
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
              ◐ El modelo no generó productos válidos y la demo usó los genéricos de este tipo de empresa.
            </p>
          )}
          {d.estado === 'lista' &&
            d.productos.map((p, i) => (
              <article key={`${p.nombre}-${i}`} className="rounded-xl border border-gloma-rose-soft p-4">
                <div className="flex items-baseline justify-between gap-3">
                  <h4 className="font-semibold text-gloma-brown break-words">{p.nombre}</h4>
                  {p.precio_cop !== null && (
                    <span className="text-sm text-gloma-brown whitespace-nowrap">
                      <b>{formatoCop(p.precio_cop)}</b> <span className="text-xs text-gloma-brown-light">{p.unidad_precio}</span>
                    </span>
                  )}
                </div>
                {p.resumen && <p className="text-sm text-gloma-brown-light mt-1 break-words">{p.resumen}</p>}
                {p.ficha && (
                  <details className="mt-2 text-xs text-gloma-brown-light">
                    <summary className="cursor-pointer text-gloma-brown">Ver ficha completa</summary>
                    <p className="mt-1 leading-relaxed whitespace-pre-wrap break-words">{formatearWhatsapp(p.ficha)}</p>
                  </details>
                )}
              </article>
            ))}
        </div>
      </section>
    </div>
  );
}

function PestanaConversacion({ d }: { d: Detalle }) {
  let cuerpo: React.ReactNode;
  if (d.estado !== 'lista') {
    cuerpo = (
      <p className="text-sm text-gloma-brown-light text-center py-12">
        {d.estado === 'generando' ? 'El bot todavía se está armando; aún no hay conversación.' : 'La demo no llegó a tener chat.'}
      </p>
    );
  } else if (d.transcripcion.length === 0) {
    cuerpo = (
      <div className="text-center py-12 text-gloma-brown-light">
        <p className="text-3xl mb-2" aria-hidden="true">
          💬
        </p>
        <p className="text-sm font-medium text-gloma-brown">No escribió nada en el chat</p>
        <p className="text-xs mt-1">Vio su bot listo pero no le mandó ningún mensaje.</p>
      </div>
    );
  } else {
    const quien = d.lead_borrado ? 'Prospecto' : primerNombre(d.nombre) || 'Prospecto';
    cuerpo = (
      <>
        <p className="text-[11px] text-gloma-brown-light text-center mb-3">
          Solo lectura · {cuando(d.created_at)} · el texto se muestra tal cual se escribió
        </p>
        {hiloConMarcas(d).map((e) =>
          e.tipo === 'marca' ? (
            <div key={e.orden} className="flex justify-center my-2">
              <span className="text-[11px] px-3 py-1 rounded-full bg-gloma-brown text-white">
                {e.texto} · {horaCorta(e.at)}
              </span>
            </div>
          ) : e.rol === 'usuario' ? (
            <div key={e.orden} className="flex justify-start">
              <div className="max-w-[85%] px-3 py-2 bg-white border border-gloma-rose-soft rounded-[4px_14px_14px_14px]">
                <p className="text-[11px] font-semibold text-gloma-brown-light mb-0.5">{quien}</p>
                <p className="text-sm text-gloma-brown-darker whitespace-pre-wrap break-words">{formatearWhatsapp(e.texto)}</p>
                {e.at && <p className="text-[10px] text-gloma-brown-light text-right mt-0.5">{horaCorta(e.at)}</p>}
              </div>
            </div>
          ) : (
            <div key={e.orden} className="flex justify-end">
              <div className="max-w-[85%] px-3 py-2 bg-gloma-rose-soft rounded-[14px_4px_14px_14px]">
                <p className="text-[11px] font-semibold text-gloma-brown mb-0.5">Agente de la demo</p>
                <p className="text-sm text-gloma-brown-darker whitespace-pre-wrap break-words">{formatearWhatsapp(e.texto)}</p>
                {e.at && <p className="text-[10px] text-gloma-brown-light text-right mt-0.5">{horaCorta(e.at)}</p>}
              </div>
            </div>
          ),
        )}
      </>
    );
  }
  return <div className="p-4 md:p-6 bg-gloma-cream min-h-full flex flex-col gap-2">{cuerpo}</div>;
}
