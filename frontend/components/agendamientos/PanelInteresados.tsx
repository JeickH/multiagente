import { useRouter } from 'next/router';
import { ReactNode, useCallback, useMemo, useRef, useState } from 'react';
import Paginacion from '../Paginacion';
import TutorialOverlay from '../TutorialOverlay';
import { ApiError, authedFetch } from '../../lib/api';
import {
  EstadoInteresado,
  Interesado,
  agrupar,
  duracionCorta,
  msRestantes,
  nombreVisible,
  textoMotivo,
} from '../../lib/interesados';
import AvisoFlotante, { Aviso } from './AvisoFlotante';
import ModalTomar from './ModalTomar';
import ResumenInteresados from './ResumenInteresados';
import { ESTILO_NIVEL } from './RelojVentana';
import TarjetaInteresado from './TarjetaInteresado';
import type { EstadoInteresados } from './useInteresados';

const DESHACER_MS = 8_000;
const AVISO_MS = 6_000;

const CHIPS: { valor: EstadoInteresado; texto: string }[] = [
  { valor: 'por_contactar', texto: 'Por contactar' },
  { valor: 'contactado', texto: 'Contactados' },
  { valor: 'descartado', texto: 'Descartados' },
];

const VACIO: Record<EstadoInteresado, string> = {
  por_contactar: 'No hay interesados esperando',
  contactado: 'Todavía no has marcado a nadie como contactado.',
  descartado: 'No has descartado a nadie.',
};

const SIN_PERMISO = 'Tu usuario no puede responder mensajes. Pídele acceso al administrador.';

function tutorial(umbralHoras: number) {
  return [
    {
      selector: '[data-tour="interesados-resumen"]',
      title: 'Clientes listos para comprar',
      body: `Aquí llegan las personas a las que el bot les notó ganas de comprar —preguntaron por el anticipo, pidieron reservar, preguntaron por una fecha o dejaron sus datos— y que llevan ${umbralHoras} horas sin cerrar. El bot las sigue atendiendo, pero tú puedes ayudar a cerrar.`,
    },
    {
      selector: '[data-tour="interesados-reloj"]',
      title: 'El reloj manda',
      body: 'WhatsApp te deja escribirle a alguien solo durante 24 horas desde su último mensaje. El reloj te dice cuánto te queda; la lista viene ordenada por eso, lo más urgente arriba.',
    },
    {
      selector: '[data-tour="interesados-fragmento"]',
      title: 'Lee lo que dijo',
      body: 'Debajo del nombre está la frase exacta que hizo saltar la alerta. Úsala para escribirle algo concreto, no un saludo genérico.',
    },
    {
      selector: '[data-tour="interesados-acciones"]',
      title: 'Toma la conversación o márcala',
      body: '"Tomar conversación" apaga al bot en ese chat y te lo pasa a ti. Si lo llamaste o le escribiste por fuera, usa "Ya lo contacté" y sale de tus pendientes; el bot sigue ahí.',
    },
  ];
}

function Esqueleto() {
  return (
    <div className="space-y-3" aria-busy="true">
      <span className="sr-only">Cargando interesados…</span>
      {[0, 1].map((i) => (
        <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 flex gap-4">
          <div className="w-28 md:w-32 space-y-2 shrink-0">
            <div className="h-6 w-24 rounded-md bg-gloma-soft-mint animate-pulse motion-reduce:animate-none" />
            <div className="h-1.5 w-full rounded-md bg-gloma-soft-mint animate-pulse motion-reduce:animate-none" />
          </div>
          <div className="flex-1 min-w-0 space-y-2">
            <div className="h-4 w-32 max-w-full rounded-md bg-gloma-soft-mint animate-pulse motion-reduce:animate-none" />
            <div className="h-4 w-56 max-w-full rounded-md bg-gloma-soft-mint animate-pulse motion-reduce:animate-none" />
            <div className="h-3 w-3/4 rounded-md bg-gloma-soft-mint animate-pulse motion-reduce:animate-none" />
          </div>
        </div>
      ))}
    </div>
  );
}

type Props = {
  s: EstadoInteresados;
  activo: boolean;
  onIrALlamadas: () => void;
};

export default function PanelInteresados({ s, activo, onIrALlamadas }: Props) {
  const router = useRouter();
  const [aviso, setAviso] = useState<Aviso | null>(null);
  const [aTomar, setATomar] = useState<Interesado | null>(null);
  const [tomando, setTomando] = useState(false);
  const [ocupados, setOcupados] = useState<Set<number>>(() => new Set());
  const avisoId = useRef(0);

  const avisar = useCallback((a: Omit<Aviso, 'id'>) => {
    avisoId.current += 1;
    setAviso({ ...a, id: avisoId.current });
  }, []);
  const cerrarAviso = useCallback(() => setAviso(null), []);

  const marcarOcupado = (id: number, si: boolean) =>
    setOcupados((o) => {
      const n = new Set(o);
      if (si) n.add(id);
      else n.delete(id);
      return n;
    });

  /**
   * Respuestas que significan "la lista cambió": se avisa y se refresca. Lo
   * demás es un error genérico (el backend ya lo sanitiza, regla 6).
   */
  const avisarError = (e: unknown, it: Interesado) => {
    const status = e instanceof ApiError ? e.status : 0;
    let texto: string;
    if (status === 409) texto = 'Ya la tomó otra persona del equipo.';
    else if (status === 410)
      texto = `${nombreVisible(it)} ya no está en la lista: la conversación se cerró o la tomó un asesor.`;
    else if (status === 403) texto = SIN_PERMISO;
    else texto = e instanceof Error && e.message ? e.message : 'No se pudo guardar el cambio.';
    avisar({ texto, tipo: 'error', ms: AVISO_MS });
    return status === 409 || status === 410;
  };

  const patch = (id: number, body: Record<string, string>) =>
    authedFetch<Interesado>(`/agendamientos/interesados/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });

  /** Deshacer: vuelve a "Por contactar". Si falla, se avisa; la lista se refresca igual. */
  const deshacer = (it: Interesado) => {
    s.mostrar(it.id, 'por_contactar');
    patch(it.id, { estado: 'por_contactar' })
      .catch((e) => {
        avisarError(e, it);
      })
      .finally(() => s.refrescar());
  };

  /** Contactado / descartado: sale de la lista al instante y vuelve si falla. */
  const gestionar = async (it: Interesado, body: { estado: 'contactado' | 'descartado'; motivo?: string }) => {
    marcarOcupado(it.id, true);
    s.ocultar(it.id);
    try {
      await patch(it.id, body);
      // Si antes se había sacado de ese filtro (contactado → reabierto → otra
      // vez contactado), ahí tiene que volver a verse.
      s.mostrar(it.id, body.estado);
      avisar({
        texto:
          body.estado === 'contactado'
            ? 'Marcado como contactado.'
            : `Descartado: ${textoMotivo(body.motivo).toLowerCase()}.`,
        tipo: 'ok',
        ms: DESHACER_MS,
        accion: { texto: 'Deshacer', onClick: () => deshacer(it) },
      });
      s.refrescar();
    } catch (e) {
      const cambio = avisarError(e, it);
      if (cambio) s.refrescar();
      else s.mostrar(it.id);
    } finally {
      marcarOcupado(it.id, false);
    }
  };

  const reabrir = async (it: Interesado) => {
    marcarOcupado(it.id, true);
    s.ocultar(it.id);
    try {
      await patch(it.id, { estado: 'por_contactar' });
      s.mostrar(it.id, 'por_contactar');
      avisar({ texto: `${nombreVisible(it)} volvió a "Por contactar".`, tipo: 'ok', ms: AVISO_MS });
      s.refrescar();
    } catch (e) {
      const cambio = avisarError(e, it);
      if (cambio) s.refrescar();
      else s.mostrar(it.id);
    } finally {
      marcarOcupado(it.id, false);
    }
  };

  const tomar = async () => {
    const it = aTomar;
    if (!it || tomando) return;
    setTomando(true);
    try {
      const r = await authedFetch<Interesado>(`/agendamientos/interesados/${it.id}/tomar`, {
        method: 'POST',
      });
      setATomar(null);
      avisar({ texto: 'Listo, la conversación es tuya.', tipo: 'ok', ms: AVISO_MS });
      router.push(`/mensajes?conversacion=${r?.conversation_id ?? it.conversation_id}`);
    } catch (e) {
      setATomar(null);
      if (avisarError(e, it)) {
        s.ocultar(it.id);
        s.refrescar();
      }
    } finally {
      setTomando(false);
    }
  };

  const datos = s.datos;
  const grupos = useMemo(
    () => (s.estado === 'por_contactar' ? agrupar(s.visibles, s.ahoraServidor) : []),
    [s.estado, s.visibles, s.ahoraServidor],
  );
  const puedeTomar = datos?.puede_tomar === true;
  const primeraId = s.visibles[0]?.id;

  const tarjeta = (it: Interesado) => (
    <TarjetaInteresado
      key={it.id}
      it={it}
      ahoraServidor={s.ahoraServidor}
      puedeTomar={puedeTomar}
      ocupado={ocupados.has(it.id)}
      primera={it.id === primeraId}
      onTomar={setATomar}
      onContactado={(x) => gestionar(x, { estado: 'contactado' })}
      onDescartar={(x, motivo) => gestionar(x, { estado: 'descartado', motivo })}
      onReabrir={reabrir}
    />
  );

  const msTomar = aTomar ? msRestantes(aTomar.ventana_cierra_at, s.ahoraServidor) : null;

  let cuerpo: ReactNode;
  if (s.cargando) {
    cuerpo = <Esqueleto />;
  } else if (s.error) {
    cuerpo = (
      <div role="alert" className="bg-white rounded-xl border border-red-200 px-6 py-8 text-center">
        <p className="font-semibold text-red-800">{s.error}</p>
        <p className="mt-1 text-sm text-gray-600">
          Revisa tu conexión e intenta de nuevo. Si sigue fallando, avísale a soporte.
        </p>
        <button
          type="button"
          onClick={s.reintentar}
          className="mt-4 min-h-[40px] px-4 rounded-lg bg-gloma-brown hover:bg-gloma-brown-dark text-white text-sm font-semibold"
        >
          Reintentar
        </button>
      </div>
    );
  } else if (s.visibles.length === 0) {
    cuerpo = (
      <div className="bg-white rounded-xl border border-gray-200 px-6 py-10 text-center">
        <div
          className="mx-auto w-12 h-12 rounded-full bg-gloma-soft-mint text-gloma-forest flex items-center justify-center text-xl"
          aria-hidden="true"
        >
          ✓
        </div>
        <p className="mt-3 font-semibold text-gloma-brown-darker">{VACIO[s.estado]}</p>
        {s.estado === 'por_contactar' && (
          <>
            <p className="mt-1 text-sm text-gray-500 max-w-sm mx-auto">
              Cuando el bot detecte a alguien listo para comprar, aparece aquí con el tiempo que te
              queda para escribirle.
            </p>
            <button
              type="button"
              onClick={onIrALlamadas}
              className="mt-4 min-h-[40px] px-4 rounded-lg border border-gray-300 text-sm font-medium hover:border-gloma-brown"
            >
              Ver llamadas agendadas
            </button>
          </>
        )}
      </div>
    );
  } else if (s.estado !== 'por_contactar') {
    cuerpo = <div className="space-y-3">{s.visibles.map(tarjeta)}</div>;
  } else {
    cuerpo = (
      <div className={`space-y-3 transition-opacity ${s.errorRefresco ? 'opacity-70' : ''}`}>
        {grupos.map((g) => {
          const estilo = ESTILO_NIVEL[g.nivel];
          if (g.nivel === 'cerrada') {
            return (
              <details key={g.nivel} className="pt-3 group">
                <summary className="cursor-pointer list-none flex flex-wrap items-center gap-x-2 text-xs font-semibold uppercase tracking-wide text-gray-500 min-h-[32px]">
                  <span className="group-open:rotate-90 transition-transform" aria-hidden="true">
                    ▸
                  </span>
                  {estilo.encabezado}
                  <span className="normal-case font-normal">
                    ({g.items.length}) · solo llamada o plantilla
                  </span>
                </summary>
                <div className="space-y-3 mt-3">{g.items.map(tarjeta)}</div>
              </details>
            );
          }
          return (
            <section key={g.nivel} aria-label={estilo.encabezado} className="space-y-3">
              <h3
                className={`font-body text-xs font-semibold uppercase tracking-wide pt-1 ${estilo.titulo}`}
              >
                {estilo.encabezado}{' '}
                <span className="text-gray-400 normal-case font-normal">({g.items.length})</span>
              </h3>
              {g.items.map(tarjeta)}
            </section>
          );
        })}
      </div>
    );
  }

  return (
    <>
      {datos && <ResumenInteresados resumen={datos.resumen} />}

      <div className="flex items-center gap-2 mb-4 overflow-x-auto">
        {CHIPS.map((c) => (
          <button
            key={c.valor}
            type="button"
            aria-pressed={s.estado === c.valor}
            onClick={() => s.setEstado(c.valor)}
            className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
              s.estado === c.valor
                ? 'bg-gloma-brown text-white border-gloma-brown'
                : 'bg-white text-gray-600 border-gray-300 hover:border-gloma-brown'
            }`}
          >
            {c.texto}
          </button>
        ))}
        {datos && !s.cargando && (
          <span className="ml-auto shrink-0 text-[11px] text-gray-400 hidden sm:inline">
            Actualizado {s.minutosDesdeOk < 1 ? 'hace un momento' : `hace ${s.minutosDesdeOk} min`}
          </span>
        )}
        <button
          type="button"
          onClick={s.refrescar}
          disabled={s.cargando || s.refrescando}
          className={`${datos && !s.cargando ? 'ml-auto sm:ml-0' : 'ml-auto'} shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border border-gray-300 bg-white text-gray-600 hover:border-gloma-brown disabled:opacity-50`}
        >
          {s.refrescando ? 'Actualizando…' : '↻ Actualizar'}
        </button>
      </div>

      {s.errorRefresco && !s.cargando && (
        <div
          role="status"
          className="mb-4 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 px-4 py-3 text-sm flex items-center gap-3"
        >
          <span className="flex-1">
            No pudimos actualizar la lista.
            {s.minutosDesdeOk > 0 &&
              ` Los tiempos pueden estar desfasados desde hace ${duracionCorta(s.minutosDesdeOk * 60_000)}.`}
          </span>
          <button type="button" onClick={s.reintentar} className="font-semibold underline shrink-0">
            Reintentar
          </button>
        </div>
      )}

      {datos && !puedeTomar && s.estado === 'por_contactar' && s.visibles.length > 0 && !s.cargando && (
        <p className="mb-4 text-xs text-gray-500">
          {SIN_PERMISO} Mientras tanto puedes llamar o marcar a quién ya contactaste.
        </p>
      )}

      {cuerpo}

      {datos && !s.cargando && !s.error && (
        <Paginacion
          pagina={s.pagina}
          porPagina={s.porPagina}
          total={datos.total}
          onPagina={s.setPagina}
          onPorPagina={s.setPorPagina}
          cargando={s.refrescando}
          etiqueta="interesados"
        />
      )}

      {aTomar && (
        <ModalTomar
          nombre={nombreVisible(aTomar)}
          tiempo={msTomar !== null && msTomar > 0 ? duracionCorta(msTomar) : null}
          tomando={tomando}
          onConfirmar={tomar}
          onCancelar={() => setATomar(null)}
        />
      )}

      <AvisoFlotante aviso={aviso} onCerrar={cerrarAviso} />

      {activo && datos && !s.cargando && (
        <TutorialOverlay
          moduleKey="agendamientos_interesados"
          steps={tutorial(datos.umbral_horas || 6)}
        />
      )}
    </>
  );
}
