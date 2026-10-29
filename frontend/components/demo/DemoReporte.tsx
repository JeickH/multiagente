/**
 * Reporte de EJEMPLO de la demo (encargo del CEO del 2026-10-28): cómo se
 * vería el reporte del negocio que hizo la demo tras un mes con Gloma.
 *
 * - Datos ficticios y fijos de `lib/demoReporte.ts`, rotulados a la vista
 *   arriba de todo. Solo el nombre de la empresa sale de la demo.
 * - Diálogo modal: `role="dialog"` + `aria-modal`, foco al título al abrir,
 *   Tab no sale del diálogo, Escape y el botón «Cerrar» lo cierran, y el foco
 *   vuelve a donde estaba (el botón que lo abrió).
 * - Gráficos con divs, sin librerías. Cada gráfico es una `figure` con su
 *   texto leíble: las barras son decorativas y los valores van escritos.
 * - Sin scroll horizontal a 375 px: todo en una columna con `min-w-0`.
 */
import { useEffect, useMemo, useRef } from 'react';

import { TEXTOS_AGENDAR } from '../../lib/agendarLlamada';
import { rellenarCopy } from '../../lib/demo_copy';
import {
  CALIFICACION,
  HORARIO_OFICINA,
  MENSAJES_POR_HORA,
  PASOS,
  RECORDATORIOS,
  REPORTE_TEXTOS as T,
  RESPUESTA_POR_FRANJA,
  TICKET_PROMEDIO,
  VENTA_EN_EL_AIRE,
  duracion,
  enHorarioDeOficina,
  horaDelDia,
  mayorCaida,
  miles,
  millones,
  pesos,
  porcentaje,
  resumenReporte,
} from '../../lib/demoReporte';
import { IconoInfo } from './iconos';

/** Colores de los gráficos (validados sobre #101817; todo va con etiqueta escrita). */
const AGENTE = '#4DB6AC'; // mint de la marca
const ASESORES = '#F5C24B'; // dorado del premio
const NEUTRO = 'rgba(230, 239, 238, 0.28)';

const FOCUSABLES =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function Seccion({
  id,
  titulo,
  sub,
  children,
}: {
  id: string;
  titulo: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="rounded-3xl bg-white/[0.04] border border-gloma-mint/15 p-4 md:p-5 min-w-0">
      <h3 id={id} className="font-heading font-bold text-lg md:text-xl text-white leading-tight">
        {titulo}
      </h3>
      {sub && <p className="text-[13px] text-gloma-ink-muted mt-1 leading-snug">{sub}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Frase de conclusión de cada gráfico: lo primero que se lee después del título. */
function Conclusion({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-sm text-gloma-ink-text leading-snug">{children}</p>;
}

function Muestra({ color, etiqueta }: { color: string; etiqueta: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-gloma-ink-muted">
      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: color }} aria-hidden="true" />
      {etiqueta}
    </span>
  );
}

/** Ancho en % con un mínimo visible para que una barra chica no desaparezca. */
const ancho = (valor: number, max: number, minimo = 1.5) => `${Math.max(minimo, (valor / max) * 100)}%`;

export default function DemoReporte({
  empresa,
  onCerrar,
  onAgendar,
}: {
  empresa: string;
  onCerrar: () => void;
  /** «Agendar una llamada» del cierre; el reporte se cierra antes de abrir el chat. */
  onAgendar: () => void;
}) {
  const dialogo = useRef<HTMLDivElement>(null);
  const titulo = useRef<HTMLHeadingElement>(null);
  const r = useMemo(() => resumenReporte(), []);
  const caida = useMemo(() => mayorCaida(), []);
  const datos = { empresa };

  // Foco al título, scroll del fondo bloqueado y, al cerrar, el foco vuelve.
  useEffect(() => {
    const previo = document.activeElement as HTMLElement | null;
    titulo.current?.focus({ preventScroll: true });
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = overflow;
      previo?.focus?.({ preventScroll: true });
    };
  }, []);

  const alTeclear = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      onCerrar();
      return;
    }
    if (e.key !== 'Tab' || !dialogo.current) return;
    const lista = Array.from(dialogo.current.querySelectorAll<HTMLElement>(FOCUSABLES));
    if (lista.length === 0) return;
    const primero = lista[0];
    const ultimo = lista[lista.length - 1];
    const activo = document.activeElement;
    if (e.shiftKey && (activo === primero || activo === titulo.current)) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && activo === ultimo) {
      e.preventDefault();
      primero.focus();
    }
  };

  const maxPersonas = PASOS[0].personas;
  const maxAsesoresMin = Math.max(...RESPUESTA_POR_FRANJA.map((f) => f.asesoresMin));
  const maxHora = Math.max(...MENSAJES_POR_HORA);
  const horaPico = (desde: number, hasta: number) => {
    let h = desde;
    for (let i = desde; i < hasta; i += 1) if (MENSAJES_POR_HORA[i] > MENSAJES_POR_HORA[h]) h = i;
    return h;
  };
  const picoDia = horaPico(0, 15);
  const picoNoche = horaPico(15, 24);
  const totalCalif = CALIFICACION.reduce((a, c) => a + c.personas, 0);
  const coloresCalif: Record<string, string> = { listos: AGENTE, tibios: ASESORES, no_listos: NEUTRO };
  const maxAire = Math.max(...VENTA_EN_EL_AIRE.map((s) => s.pesos));
  const noche = RESPUESTA_POR_FRANJA[RESPUESTA_POR_FRANJA.length - 1];

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto overflow-x-hidden bg-black/75 text-gloma-ink-text"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCerrar();
      }}
    >
      <div
        ref={dialogo}
        role="dialog"
        aria-modal="true"
        aria-labelledby="reporte-titulo"
        aria-describedby="reporte-rotulo"
        onKeyDown={alTeclear}
        className="relative w-full min-h-full md:min-h-0 md:max-w-3xl md:mx-auto md:my-8 md:rounded-3xl bg-gloma-ink md:border md:border-gloma-mint/20 md:shadow-2xl demo-entra"
      >
        {/* Cabecera fija con el cierre siempre a mano */}
        <header
          className="sticky top-0 z-10 flex items-start gap-3 px-4 md:px-6 pb-3 bg-gloma-ink/95 backdrop-blur border-b border-white/10 md:rounded-t-3xl"
          style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}
        >
          <div className="min-w-0 flex-1">
            <p className="text-xs uppercase tracking-widest font-semibold text-gloma-mint">{T.periodo}</p>
            <h2
              id="reporte-titulo"
              ref={titulo}
              tabIndex={-1}
              className="font-heading font-extrabold text-xl md:text-3xl text-white leading-tight break-words focus:outline-none"
            >
              {T.titulo}
            </h2>
          </div>
          <button
            type="button"
            onClick={onCerrar}
            aria-label={T.cerrar}
            className="shrink-0 w-11 h-11 rounded-full border border-white/40 text-white flex items-center justify-center hover:bg-white/10"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        <div className="px-4 md:px-6 pt-4 space-y-4" style={{ paddingBottom: 'max(24px, env(safe-area-inset-bottom))' }}>
          {/* Rótulo de datos ficticios: visible, no en letra pequeña. */}
          <p
            id="reporte-rotulo"
            className="flex items-start gap-2 rounded-2xl border border-[#F5C24B]/50 bg-[#F5C24B]/10 px-3.5 py-2.5 text-[13px] md:text-sm font-semibold text-white break-words"
          >
            <IconoInfo />
            <span className="min-w-0">{rellenarCopy(T.rotulo, datos)}</span>
          </p>

          {/* Resumen */}
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            {[
              { k: 'Conversaciones', v: miles(r.conversaciones), d: 'en 30 días' },
              { k: 'Responde el agente', v: duracion(r.agenteSeg), d: `tus asesores: ${duracion(r.asesoresOficinaMin * 60)} en horario de oficina` },
              { k: 'Fuera de horario', v: `${r.pctFueraDeHorario} %`, d: `${miles(r.fueraDeHorario)} de ${miles(r.totalMensajes)} mensajes` },
              { k: 'En el aire esta semana', v: millones(r.ventaAireUltimaSemana), d: 'en planes que cotizaron y no reservaron' },
            ].map((t) => (
              <div key={t.k} className="rounded-2xl bg-white/[0.04] border border-gloma-mint/15 p-3 min-w-0">
                <dt className="text-xs text-gloma-ink-muted">{t.k}</dt>
                <dd className="font-heading font-extrabold text-xl md:text-[22px] text-white leading-tight mt-1">{t.v}</dd>
                <dd className="text-[11.5px] text-gloma-ink-muted leading-snug mt-1">{t.d}</dd>
              </div>
            ))}
          </dl>

          {/* 1. En qué paso se va la gente */}
          <Seccion id="rep-pasos" titulo="En qué paso se va la gente" sub="De las personas que te escribieron en el mes, cuántas llegaron a cada paso.">
            <figure className="m-0">
              <figcaption className="sr-only">
                {PASOS.map((p) => `${p.etiqueta}: ${miles(p.personas)}`).join('. ')}.
              </figcaption>
              <ol className="space-y-1">
                {PASOS.map((p, i) => {
                  const seFueron = i > 0 ? PASOS[i - 1].personas - p.personas : 0;
                  const esLaMayor = i === caida.indice;
                  return (
                    <li key={p.clave} aria-hidden="true">
                      {i > 0 && (
                        <p className={`text-[11.5px] pl-1 py-0.5 ${esLaMayor ? 'text-[#F5C24B] font-semibold' : 'text-gloma-ink-muted'}`}>
                          ↓ se fueron {miles(seFueron)}
                          {esLaMayor ? ' · aquí se va más gente' : ''}
                        </p>
                      )}
                      <div className="flex items-baseline justify-between gap-3 text-sm">
                        <span className="text-white min-w-0">{p.etiqueta}</span>
                        <span className="tabular-nums text-white font-semibold shrink-0">
                          {miles(p.personas)}{' '}
                          <span className="text-gloma-ink-muted font-normal">· {porcentaje(p.personas, maxPersonas)} %</span>
                        </span>
                      </div>
                      <div className="mt-1 h-3 rounded bg-white/[0.06]">
                        <div className="h-3 rounded" style={{ width: ancho(p.personas, maxPersonas), background: AGENTE }} />
                      </div>
                    </li>
                  );
                })}
              </ol>
            </figure>
            <Conclusion>
              Donde más gente se va es justo después del precio: {miles(caida.seFueron)} personas lo recibieron y no
              dejaron sus datos. Ahí es donde más sirven los recordatorios del agente.
            </Conclusion>
          </Seccion>

          {/* 2. Tiempos de respuesta */}
          <Seccion
            id="rep-tiempos"
            titulo="Cuánto tardan en contestar"
            sub="Tiempo hasta la primera respuesta, según la hora en que escribe el cliente."
          >
            <div className="flex flex-wrap gap-x-4 gap-y-1" aria-hidden="true">
              <Muestra color={AGENTE} etiqueta="El agente" />
              <Muestra color={ASESORES} etiqueta="Tus asesores" />
            </div>
            <figure className="m-0 mt-3">
              <figcaption className="sr-only">
                {RESPUESTA_POR_FRANJA.map(
                  (f) => `De ${f.franja}: el agente ${duracion(f.agenteSeg)}, tus asesores ${duracion(f.asesoresMin * 60)}`,
                ).join('. ')}
                .
              </figcaption>
              <ul className="space-y-3" aria-hidden="true">
                {RESPUESTA_POR_FRANJA.map((f) => (
                  <li key={f.franja}>
                    <p className="text-[13px] text-white">{f.franja}</p>
                    <div className="mt-1 grid grid-cols-[1fr_auto] items-center gap-x-2 gap-y-1">
                      <div className="h-2.5 rounded bg-white/[0.06]">
                        <div className="h-2.5 rounded" style={{ width: ancho(f.agenteSeg, maxAsesoresMin * 60, 1) , background: AGENTE }} />
                      </div>
                      <span className="text-xs tabular-nums text-gloma-ink-text w-20 text-right">{duracion(f.agenteSeg)}</span>
                      <div className="h-2.5 rounded bg-white/[0.06]">
                        <div className="h-2.5 rounded" style={{ width: ancho(f.asesoresMin, maxAsesoresMin), background: ASESORES }} />
                      </div>
                      <span className="text-xs tabular-nums text-gloma-ink-text w-20 text-right">{duracion(f.asesoresMin * 60)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </figure>
            <Conclusion>
              De {noche.franja} tus asesores tardan {duracion(noche.asesoresMin * 60)} en contestar; el agente,{' '}
              {duracion(noche.agenteSeg)}. Para esa hora, muchos clientes ya cotizaron en otro lado.
            </Conclusion>
          </Seccion>

          {/* 3. A qué horas escriben */}
          <Seccion
            id="rep-horas"
            titulo="A qué horas te escriben"
            sub={`Mensajes del mes por hora. Horario de oficina: de ${horaDelDia(HORARIO_OFICINA.desde)} a ${horaDelDia(HORARIO_OFICINA.hasta)}`}
          >
            <div className="flex flex-wrap gap-x-4 gap-y-1" aria-hidden="true">
              <Muestra color={AGENTE} etiqueta="En horario de oficina" />
              <Muestra color={ASESORES} etiqueta="Fuera de horario" />
            </div>
            <figure className="m-0 mt-3">
              <figcaption className="sr-only">
                {`Llegaron ${miles(r.totalMensajes)} mensajes. ${miles(r.fueraDeHorario)} (${r.pctFueraDeHorario} %) fuera de horario. `}
                {`La hora con más mensajes de día es ${horaDelDia(picoDia)} (${miles(MENSAJES_POR_HORA[picoDia])}) y de noche ${horaDelDia(picoNoche)} (${miles(MENSAJES_POR_HORA[picoNoche])}).`}
              </figcaption>
              <div className="flex items-end gap-[2px] h-28" aria-hidden="true">
                {MENSAJES_POR_HORA.map((n, h) => (
                  <div
                    key={h}
                    title={`${horaDelDia(h)}: ${miles(n)} mensajes`}
                    className="flex-1 min-w-0 rounded-t-[3px]"
                    style={{ height: ancho(n, maxHora, 2), background: enHorarioDeOficina(h) ? AGENTE : ASESORES }}
                  />
                ))}
              </div>
              <div className="relative h-4 mt-1 text-[10.5px] text-gloma-ink-muted" aria-hidden="true">
                {[0, 6, 12, 18].map((h) => (
                  <span key={h} className="absolute" style={{ left: `${(h / 24) * 100}%` }}>
                    {horaDelDia(h)}
                  </span>
                ))}
              </div>
            </figure>
            <Conclusion>
              {miles(r.fueraDeHorario)} mensajes ({r.pctFueraDeHorario} %) llegaron fuera de horario. A las{' '}
              {horaDelDia(picoNoche)} te escriben casi tanto como en el pico de la mañana ({horaDelDia(picoDia)}).
            </Conclusion>
          </Seccion>

          {/* 4. Calificación */}
          <Seccion
            id="rep-calif"
            titulo="Quiénes están listos para comprar"
            sub="El agente califica a cada interesado con lo que te contó en el chat."
          >
            <figure className="m-0">
              <figcaption className="sr-only">
                {CALIFICACION.map((c) => `${c.etiqueta}: ${miles(c.personas)}`).join('. ')}.
              </figcaption>
              <div className="flex h-4 gap-[2px] rounded overflow-hidden" aria-hidden="true">
                {CALIFICACION.map((c) => (
                  <div key={c.clave} style={{ width: `${(c.personas / totalCalif) * 100}%`, background: coloresCalif[c.clave] }} />
                ))}
              </div>
              <ul className="mt-3 space-y-2" aria-hidden="true">
                {CALIFICACION.map((c) => (
                  <li key={c.clave} className="flex items-start gap-2.5">
                    <span className="mt-1 w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: coloresCalif[c.clave] }} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm text-white font-semibold">
                        {c.etiqueta}{' '}
                        <span className="tabular-nums">
                          {miles(c.personas)} <span className="text-gloma-ink-muted font-normal">· {porcentaje(c.personas, totalCalif)} %</span>
                        </span>
                      </span>
                      <span className="block text-[12.5px] text-gloma-ink-muted leading-snug">{c.detalle}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </figure>
            <Conclusion>
              Tus asesores atienden primero a los {miles(CALIFICACION[0].personas)} listos, con todo el historial; a los
              tibios el agente les vuelve a escribir.
            </Conclusion>
          </Seccion>

          {/* 5. Venta en el aire */}
          <Seccion
            id="rep-aire"
            titulo="Venta que se queda en el aire"
            sub={`Planes que los clientes cotizaron y no reservaron, con el valor promedio de una reserva (${pesos(TICKET_PROMEDIO)}).`}
          >
            <figure className="m-0">
              <figcaption className="sr-only">
                {VENTA_EN_EL_AIRE.map((s) => `${s.semana}: ${pesos(s.pesos)}`).join('. ')}.
              </figcaption>
              <ul className="space-y-2.5" aria-hidden="true">
                {VENTA_EN_EL_AIRE.map((s) => (
                  <li key={s.semana}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="text-white">{s.semana}</span>
                      <span className="tabular-nums text-white font-semibold">{pesos(s.pesos)}</span>
                    </div>
                    <div className="mt-1 h-3 rounded bg-white/[0.06]">
                      <div className="h-3 rounded" style={{ width: ancho(s.pesos, maxAire), background: ASESORES }} />
                    </div>
                  </li>
                ))}
              </ul>
            </figure>
            <Conclusion>
              En promedio, {pesos(r.ventaAirePromedio)} por semana en clientes que preguntaron y nadie retomó a tiempo.
            </Conclusion>
          </Seccion>

          {/* 6. Recordatorios */}
          <Seccion
            id="rep-recordatorios"
            titulo="Los que recuperaron los recordatorios"
            sub="Clientes que dejaron de contestar y a los que el agente les volvió a escribir."
          >
            <ol className="grid grid-cols-3 gap-2">
              {[
                { n: RECORDATORIOS.dejaronDeContestar, t: 'dejaron de contestar' },
                { n: RECORDATORIOS.volvieron, t: 'volvieron a escribir' },
                { n: RECORDATORIOS.reservaron, t: 'reservaron' },
              ].map((p, i) => (
                <li key={p.t} className="rounded-2xl bg-white/[0.04] border border-gloma-mint/15 p-2.5 min-w-0">
                  <p className="font-heading font-extrabold text-xl md:text-2xl leading-tight" style={{ color: i === 2 ? AGENTE : '#FFFFFF' }}>
                    {miles(p.n)}
                  </p>
                  <p className="text-[11.5px] md:text-xs text-gloma-ink-muted leading-snug mt-0.5">{p.t}</p>
                </li>
              ))}
            </ol>
            <Conclusion>
              {porcentaje(RECORDATORIOS.volvieron, RECORDATORIOS.dejaronDeContestar)} % volvió a la conversación y{' '}
              {miles(RECORDATORIOS.reservaron)} reservaron: {pesos(r.recuperadoPesos)} en ventas que ya se daban por perdidas.
            </Conclusion>
          </Seccion>

          {/* Cierre */}
          <div className="rounded-3xl bg-gloma-forest border border-gloma-mint/30 p-4 md:p-5">
            <p className="font-heading font-bold text-white text-lg leading-snug break-words">{rellenarCopy(T.cierreTitulo, datos)}</p>
            <p className="text-[13px] text-white/85 mt-1">{T.cierreTexto}</p>
            <div className="mt-3 flex flex-col sm:flex-row gap-2">
              <button type="button" onClick={onAgendar} className="demo-btn-primario w-full sm:w-auto !min-h-[44px] !text-sm">
                {TEXTOS_AGENDAR.agendar}
              </button>
              <button
                type="button"
                onClick={onCerrar}
                className="inline-flex items-center justify-center w-full sm:w-auto min-h-[44px] px-5 rounded-full border border-white/50 text-white text-sm font-semibold hover:bg-white/10"
              >
                Volver a la demo
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
