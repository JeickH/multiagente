/**
 * Suscripción mensual: activarla, verla y desactivarla.
 *
 * Vive dentro de la pantalla de pagos y es el único sitio de la app donde se
 * pide un número de tarjeta.
 *
 * ===========================================================================
 * LA TARJETA NO PASA POR NUESTRO SERVIDOR
 * ===========================================================================
 *
 * `tokenizar()` hace `POST` **directo a Wompi** con la llave pública. El
 * número de la tarjeta va del navegador a Wompi y de ahí no sale: nuestro
 * backend recibe únicamente el `tok_...` resultante. Es deliberado y no es
 * negociable —
 *
 *   - si el PAN pasara por `/api/...`, quedaría en los logs de acceso, en el
 *     cuerpo del request y en cualquier traza de error, y la plataforma
 *     entera entraría en alcance PCI-DSS;
 *   - el backend además **rechaza** cualquier cosa con forma de número de
 *     tarjeta, así que mandarlo por ahí ni siquiera funcionaría.
 *
 * Por eso este es el único `fetch` de la app que no usa `authedFetch`: va a
 * otro dominio y no lleva nuestro JWT. Y por eso el estado con los datos de
 * la tarjeta se limpia (`limpiarFormulario`) apenas Wompi devuelve el token.
 *
 * El cobro tampoco se da por bueno al cerrar el modal: Wompi responde
 * `PENDING` y la confirmación llega por el webhook. La pantalla muestra
 * "estamos confirmando" y refresca sola hasta que el estado cambie.
 */
import { useCallback, useEffect, useState } from 'react';

import { ApiError, authedFetch } from '../lib/api';
import { fechaHoraLarga } from '../lib/fechas';

type Tarjeta = { brand: string | null; last_four: string | null };

type Cobro = {
  id: number;
  reference: string;
  amount_cents: number;
  currency: string;
  status: string;
  attempt: number;
  scheduled_for: string;
  paid_at: string | null;
  created_at: string;
};

export type Suscripcion = {
  status: 'pending' | 'active' | 'past_due' | 'canceled';
  plan_key: string;
  plan_nombre: string;
  plan_descripcion: string;
  amount_cents: number;
  amount_cop: number;
  currency: string;
  tarjeta: Tarjeta | null;
  next_charge_at: string | null;
  last_charge_at: string | null;
  activated_at: string | null;
  canceled_at: string | null;
  habilitada: boolean;
  cobro_en_curso: boolean;
  cobros: Cobro[];
};

type Config = {
  public_key: string;
  tokens_url: string;
  acceptance_token: string;
  acceptance_permalink: string | null;
  personal_auth_token: string | null;
  personal_auth_permalink: string | null;
  sandbox: boolean;
};

const COP = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
});

/** Cómo se ve cada estado en el botón y en la etiqueta. */
const ESTADOS: Record<Suscripcion['status'], { etiqueta: string; cls: string }> = {
  pending: { etiqueta: 'Pendiente por activar', cls: 'bg-amber-100 text-amber-800' },
  active: { etiqueta: 'Suscripción activa', cls: 'bg-emerald-50 text-emerald-700' },
  past_due: { etiqueta: 'Cobro pendiente', cls: 'bg-red-50 text-red-700' },
  canceled: { etiqueta: 'Desactivada', cls: 'bg-gray-100 text-gray-600' },
};

/** Solo dígitos, en grupos de cuatro: "4242 4242 4242 4242". */
function formatearNumero(valor: string): string {
  const digitos = valor.replace(/\D/g, '').slice(0, 19);
  return digitos.replace(/(.{4})/g, '$1 ').trim();
}

/** "MM/AA" mientras se escribe. */
function formatearVencimiento(valor: string): string {
  const d = valor.replace(/\D/g, '').slice(0, 4);
  return d.length <= 2 ? d : `${d.slice(0, 2)}/${d.slice(2)}`;
}

export default function SuscripcionPanel() {
  const [sub, setSub] = useState<Suscripcion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fallóLaCarga, setFallóLaCarga] = useState(false);
  const [abriendo, setAbriendo] = useState(false);
  const [modalTarjeta, setModalTarjeta] = useState<Config | null>(null);
  const [modalCancelar, setModalCancelar] = useState(false);

  /**
   * Trae el estado de la suscripción, **reintentando una vez**.
   *
   * El reintento no es paranoia: el rewrite `/api/*` lo sirve el SSR de
   * Amplify, y su primera petición tras un rato de inactividad puede fallar
   * con 500 por arranque en frío. Se comprobó en producción — el backend
   * respondía 200 a todo y el 500 lo devolvía Next. Sin reintento, esa
   * primera carga del día deja la sección inservible hasta que el usuario
   * recargue, que es justo cuando nadie sabe que hay que recargar.
   *
   * Un 403 no se reintenta ni se muestra como error: significa que esta
   * sesión no administra la caja, y la pantalla que la contiene ya se
   * encarga de decirlo.
   */
  const cargar = useCallback(async (reintentar = true) => {
    try {
      setSub(await authedFetch<Suscripcion>('/pagos/suscripcion'));
      setFallóLaCarga(false);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) return;
      if (reintentar) {
        await new Promise((r) => setTimeout(r, 1500));
        return cargar(false);
      }
      setFallóLaCarga(true);
      setError('No se pudo cargar la suscripción.');
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Mientras un cobro está sin confirmar, el estado lo cambia el webhook por
  // detrás: se refresca sola en vez de dejar al cliente recargando la página.
  useEffect(() => {
    if (!sub?.cobro_en_curso) return;
    const t = window.setInterval(cargar, 5000);
    return () => window.clearInterval(t);
  }, [sub?.cobro_en_curso, cargar]);

  /** Pide la config a nuestro backend y abre el formulario de tarjeta. */
  const abrirFormulario = async () => {
    setAbriendo(true);
    setError(null);
    try {
      setModalTarjeta(await authedFetch<Config>('/pagos/suscripcion/config'));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'No se pudo abrir el registro de la tarjeta.',
      );
    } finally {
      setAbriendo(false);
    }
  };

  const cancelar = async () => {
    setModalCancelar(false);
    setError(null);
    try {
      setSub(
        await authedFetch<Suscripcion>('/pagos/suscripcion/cancelar', {
          method: 'POST',
        }),
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'No se pudo desactivar la suscripción.',
      );
    }
  };

  if (!sub) {
    return (
      <section className="mb-10">
        <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
          Suscripción
        </h2>
        {/* Sin esta rama, un fallo de carga se veía igual que estar cargando:
            "Cargando…" para siempre, sin decir qué pasó ni cómo salir de ahí. */}
        {fallóLaCarga ? (
          <div className="rounded-2xl bg-white border border-gloma-brown-light/20 p-6 shadow-sm max-w-3xl">
            <p className="text-sm text-gloma-brown-dark">
              No pudimos cargar tu suscripción. Puede ser algo momentáneo.
            </p>
            <button
              type="button"
              onClick={() => {
                setFallóLaCarga(false);
                cargar();
              }}
              className="mt-3 px-4 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark transition-colors"
            >
              Reintentar
            </button>
          </div>
        ) : (
          <p className="text-sm text-gloma-brown-light">Cargando…</p>
        )}
      </section>
    );
  }

  const estado = ESTADOS[sub.status] ?? ESTADOS.pending;
  const activa = sub.status === 'active';
  const enMora = sub.status === 'past_due';

  return (
    <section className="mb-10">
      <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
        Suscripción
      </h2>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      <div className="rounded-2xl bg-white border border-gloma-brown-light/20 p-6 shadow-sm max-w-3xl">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-heading text-xl font-bold text-gloma-brown-dark">
              {sub.plan_nombre}
            </p>
            <p className="text-sm text-gloma-brown-light mt-1">{sub.plan_descripcion}</p>
          </div>
          <span
            className={`inline-block px-3 py-1 rounded-full text-[11px] font-semibold whitespace-nowrap ${estado.cls}`}
          >
            {estado.etiqueta}
          </span>
        </div>

        <p className="font-heading text-3xl font-extrabold text-gloma-brown mt-4">
          {COP.format(sub.amount_cop)}
          <span className="text-sm font-body font-normal text-gloma-brown-light">
            {' '}
            / mes
          </span>
        </p>

        {/* Estado del cobro en curso: el webhook todavía no confirma. */}
        {sub.cobro_en_curso && (
          <div className="mt-4 bg-gloma-rose-soft/50 border border-gloma-mint/40 text-gloma-brown-dark px-4 py-3 rounded-lg text-sm">
            <strong>Estamos confirmando tu pago.</strong> Puede tardar unos
            segundos. Esta sección se actualiza sola.
          </div>
        )}

        {enMora && !sub.cobro_en_curso && (
          <div className="mt-4 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg text-sm">
            <strong>No pudimos hacer el cobro de este mes.</strong> Lo intentamos
            tres veces. Registra otra tarjeta para reactivar el cobro automático;
            no se hizo ningún cargo.
          </div>
        )}

        {/* Datos del ciclo */}
        {(activa || enMora) && (
          <dl className="mt-4 text-sm text-gloma-brown-dark space-y-1">
            {sub.tarjeta?.last_four && (
              <div className="flex justify-between max-w-sm">
                <dt className="text-gloma-brown-light">Tarjeta</dt>
                <dd className="font-medium">
                  {sub.tarjeta.brand || 'Tarjeta'} ····{sub.tarjeta.last_four}
                </dd>
              </div>
            )}
            {sub.next_charge_at && (
              <div className="flex justify-between max-w-sm">
                <dt className="text-gloma-brown-light">Próximo cobro</dt>
                <dd className="font-medium">{fechaHoraLarga(sub.next_charge_at, '—')}</dd>
              </div>
            )}
            {sub.last_charge_at && (
              <div className="flex justify-between max-w-sm">
                <dt className="text-gloma-brown-light">Último cobro</dt>
                <dd className="font-medium">{fechaHoraLarga(sub.last_charge_at, '—')}</dd>
              </div>
            )}
          </dl>
        )}

        {sub.status === 'canceled' && (
          <p className="mt-4 text-sm text-gloma-brown-light">
            El cobro automático está apagado desde el{' '}
            {fechaHoraLarga(sub.canceled_at, '—')}. Puedes volver a activarlo
            cuando quieras.
          </p>
        )}

        {/* Acciones */}
        <div className="mt-6 flex flex-wrap gap-3">
          {!activa && (
            <button
              type="button"
              onClick={abrirFormulario}
              disabled={!sub.habilitada || abriendo || sub.cobro_en_curso}
              className="px-5 py-2.5 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {abriendo ? 'Abriendo…' : 'Activar suscripción'}
            </button>
          )}
          {activa && (
            <button
              type="button"
              onClick={() => setModalCancelar(true)}
              className="px-5 py-2.5 rounded-lg border border-red-300 text-red-700 font-semibold text-sm hover:bg-red-50 transition-colors"
            >
              Desactivar suscripción
            </button>
          )}
        </div>

        {!sub.habilitada && (
          <p className="mt-3 text-xs text-gloma-brown-light">
            El medio de pago no está disponible por ahora. Intenta más tarde.
          </p>
        )}
      </div>

      {modalTarjeta && (
        <ModalTarjeta
          config={modalTarjeta}
          monto={sub.amount_cop}
          onCerrar={() => setModalTarjeta(null)}
          onListo={(actualizada) => {
            setModalTarjeta(null);
            setSub(actualizada);
          }}
        />
      )}

      {modalCancelar && (
        <ModalCancelar
          proximoCobro={sub.next_charge_at}
          onCerrar={() => setModalCancelar(false)}
          onConfirmar={cancelar}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Modal: registrar la tarjeta
// ---------------------------------------------------------------------------

function ModalTarjeta({
  config,
  monto,
  onCerrar,
  onListo,
}: {
  config: Config;
  monto: number;
  onCerrar: () => void;
  onListo: (sub: Suscripcion) => void;
}) {
  const [numero, setNumero] = useState('');
  const [vencimiento, setVencimiento] = useState('');
  const [cvc, setCvc] = useState('');
  const [titular, setTitular] = useState('');
  const [acepta, setAcepta] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Borra los datos de la tarjeta del estado de React. */
  const limpiarFormulario = () => {
    setNumero('');
    setVencimiento('');
    setCvc('');
  };

  /**
   * Cambia la tarjeta por un token, hablando **directo con Wompi**.
   *
   * No usa `authedFetch` a propósito: va a otro dominio y no debe llevar
   * nuestro JWT. La llave pública es pública por definición — es la única que
   * puede viajar al navegador.
   */
  const tokenizar = async (): Promise<string> => {
    const [mes, año] = vencimiento.split('/');
    const respuesta = await fetch(config.tokens_url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.public_key}`,
      },
      body: JSON.stringify({
        number: numero.replace(/\s/g, ''),
        cvc: cvc.trim(),
        exp_month: (mes || '').padStart(2, '0'),
        exp_year: (año || '').trim(),
        card_holder: titular.trim(),
      }),
    });

    const cuerpo = await respuesta.json().catch(() => null);
    const token = cuerpo?.data?.id;
    if (!respuesta.ok || !token) {
      // El detalle de Wompi no se muestra tal cual: puede traer texto en
      // inglés y detalles del emisor que no le sirven de nada al cliente.
      throw new Error('Revisa los datos de la tarjeta e intenta de nuevo.');
    }
    return token as string;
  };

  const enviar = async (evento: React.FormEvent) => {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      const card_token = await tokenizar();
      limpiarFormulario(); // el PAN no sigue en memoria más de lo necesario
      const actualizada = await authedFetch<Suscripcion>(
        '/pagos/suscripcion/activar',
        {
          method: 'POST',
          body: JSON.stringify({ card_token, acepta_terminos: true }),
        },
      );
      onListo(actualizada);
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error
          ? err.message
          : 'No se pudo registrar la tarjeta.',
      );
      setEnviando(false);
    }
  };

  const completo =
    numero.replace(/\s/g, '').length >= 13 &&
    /^\d{2}\/\d{2}$/.test(vencimiento) &&
    cvc.trim().length >= 3 &&
    titular.trim().length > 2 &&
    acepta;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="titulo-tarjeta"
    >
      <form
        onSubmit={enviar}
        className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl my-8"
      >
        <h3
          id="titulo-tarjeta"
          className="font-heading text-xl font-bold text-gloma-brown-dark"
        >
          Registrar tarjeta
        </h3>
        <p className="text-sm text-gloma-brown-light mt-1">
          Se cobrará <strong>{COP.format(monto)}</strong> ahora y el mismo día
          de cada mes. Puedes desactivarlo cuando quieras.
        </p>

        {config.sandbox && (
          <div className="mt-4 bg-amber-50 border border-amber-200 text-amber-900 px-3 py-2 rounded-lg text-xs">
            <strong>Modo de prueba.</strong> No se cobra dinero real. Tarjeta de
            prueba: <code>4242 4242 4242 4242</code>, cualquier fecha futura y
            cualquier CVC de 3 dígitos.
          </div>
        )}

        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="text-xs font-semibold text-gloma-brown-dark">
              Número de la tarjeta
            </span>
            <input
              value={numero}
              onChange={(e) => setNumero(formatearNumero(e.target.value))}
              inputMode="numeric"
              autoComplete="cc-number"
              placeholder="4242 4242 4242 4242"
              className="mt-1 w-full border border-gloma-brown-light/30 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gloma-mint"
            />
          </label>

          <div className="flex gap-3">
            <label className="block flex-1">
              <span className="text-xs font-semibold text-gloma-brown-dark">
                Vence (MM/AA)
              </span>
              <input
                value={vencimiento}
                onChange={(e) => setVencimiento(formatearVencimiento(e.target.value))}
                inputMode="numeric"
                autoComplete="cc-exp"
                placeholder="08/30"
                className="mt-1 w-full border border-gloma-brown-light/30 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gloma-mint"
              />
            </label>
            <label className="block w-24">
              <span className="text-xs font-semibold text-gloma-brown-dark">CVC</span>
              <input
                value={cvc}
                onChange={(e) => setCvc(e.target.value.replace(/\D/g, '').slice(0, 4))}
                inputMode="numeric"
                autoComplete="cc-csc"
                placeholder="123"
                className="mt-1 w-full border border-gloma-brown-light/30 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gloma-mint"
              />
            </label>
          </div>

          <label className="block">
            <span className="text-xs font-semibold text-gloma-brown-dark">
              Nombre como aparece en la tarjeta
            </span>
            <input
              value={titular}
              onChange={(e) => setTitular(e.target.value)}
              autoComplete="cc-name"
              className="mt-1 w-full border border-gloma-brown-light/30 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gloma-mint"
            />
          </label>

          {/* Habeas data: Wompi exige el consentimiento explícito y los enlaces
              a los documentos vigentes antes de guardar la tarjeta. */}
          <label className="flex items-start gap-2 text-xs text-gloma-brown-dark">
            <input
              type="checkbox"
              checked={acepta}
              onChange={(e) => setAcepta(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Acepto el{' '}
              <a
                href={config.acceptance_permalink || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                reglamento del servicio
              </a>
              {config.personal_auth_permalink && (
                <>
                  {' '}y la{' '}
                  <a
                    href={config.personal_auth_permalink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline"
                  >
                    autorización de tratamiento de datos
                  </a>
                </>
              )}
              , y autorizo el cobro automático mensual.
            </span>
          </label>
        </div>

        {error && (
          <div className="mt-3 bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-sm">
            {error}
          </div>
        )}

        <p className="mt-4 text-[11px] text-gloma-brown-light">
          Los datos de tu tarjeta viajan cifrados directamente a Wompi, la
          pasarela de pagos. Gloma no los recibe ni los almacena.
        </p>

        <div className="mt-5 flex gap-3 justify-end">
          <button
            type="button"
            onClick={onCerrar}
            disabled={enviando}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-gloma-brown-light hover:text-gloma-brown-dark disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={!completo || enviando}
            className="px-5 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {enviando ? 'Procesando…' : `Pagar ${COP.format(monto)}`}
          </button>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal: segunda confirmación para desactivar
// ---------------------------------------------------------------------------

/**
 * La segunda confirmación que pidió el CEO. Desactivar apaga el cobro y borra
 * la tarjeta guardada, así que se dice **qué pasa exactamente** en vez de un
 * "¿estás seguro?" — y el botón que confirma dice lo que hace, no "Sí".
 */
function ModalCancelar({
  proximoCobro,
  onCerrar,
  onConfirmar,
}: {
  proximoCobro: string | null;
  onCerrar: () => void;
  onConfirmar: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="titulo-cancelar"
    >
      <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl">
        <h3
          id="titulo-cancelar"
          className="font-heading text-xl font-bold text-gloma-brown-dark"
        >
          ¿Desactivar la suscripción?
        </h3>
        <div className="text-sm text-gloma-brown-dark mt-3 space-y-2">
          <p>Si continúas:</p>
          <ul className="list-disc pl-5 space-y-1 text-gloma-brown-light">
            <li>
              No se hará el cobro
              {proximoCobro ? ` del ${fechaHoraLarga(proximoCobro, '')}` : ''} ni
              ninguno posterior.
            </li>
            <li>Se elimina la tarjeta guardada.</li>
            <li>
              El mes que ya pagaste no se reembolsa y sigue vigente hasta que
              termine.
            </li>
          </ul>
          <p className="text-gloma-brown-light">
            Para volver a activarla tendrás que registrar la tarjeta de nuevo.
          </p>
        </div>

        <div className="mt-6 flex gap-3 justify-end">
          <button
            type="button"
            onClick={onCerrar}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-gloma-brown-dark hover:bg-gloma-cream"
          >
            No, mantenerla
          </button>
          <button
            type="button"
            onClick={onConfirmar}
            className="px-5 py-2 rounded-lg bg-red-600 text-white font-semibold text-sm hover:bg-red-700 transition-colors"
          >
            Sí, desactivar
          </button>
        </div>
      </div>
    </div>
  );
}
