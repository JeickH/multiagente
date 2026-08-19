/**
 * Pagos: saldo de mensajes y compra de paquetes (módulo de administrador).
 *
 * Es la ventana que abre el dueño de la cuenta para recargar antes de un envío
 * masivo. El asesor no la ve: el botón del menú solo aparece si
 * `GET /pagos/access` dice que sí, y aunque alguien escriba la URL a mano el
 * backend responde 403 en cada endpoint.
 *
 * El pago sale de aquí hacia Wompi por un `<form>` que se envía solo: el
 * backend arma los campos (incluida la firma de integridad) y esta página solo
 * los pone en el DOM. La firma NO se calcula en el navegador a propósito —
 * exige el secreto de integridad, y un secreto en el frontend es un secreto
 * publicado.
 *
 * Los créditos NO se suman al volver de Wompi: los suma el webhook cuando la
 * transacción queda aprobada. Por eso al regresar se ve "estamos confirmando":
 * quien controla la URL de retorno podría regalarse mensajes.
 */
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/router';

import Layout from '../components/Layout';
import { ApiError, authedFetch } from '../lib/api';

type Desglose = {
  costo_cop: number;
  margen_objetivo_cop: number;
  comision_wompi_cop: number;
  neto_real_cop: number;
  trm?: number;
  trm_fecha?: string;
};

type Paquete = {
  key: string;
  nombre: string;
  descripcion: string;
  messages: number;
  amount_cents: number;
  amount_cop: number;
  precio_por_mensaje_cop: number;
  currency: string;
  /** Link de pago creado a mano en Wompi. Si viene, manda ahí directo. */
  link_pago: string | null;
  desglose: Desglose;
};

type Compra = {
  id: number;
  package_key: string;
  messages: number;
  amount_cents: number;
  currency: string;
  reference: string;
  status: string;
  provider_tx_id: string | null;
  credited_at: string | null;
  created_at: string;
};

type Saldo = { message_credits: number; compras: Compra[] };

type CheckoutForm = { url: string; method: string; fields: Record<string, string> };
type Checkout = { reference: string; checkout: CheckoutForm };

const COP = new Intl.NumberFormat('es-CO', {
  style: 'currency',
  currency: 'COP',
  maximumFractionDigits: 0,
});

const ESTADOS: Record<string, { label: string; cls: string }> = {
  approved: { label: 'Pagada', cls: 'bg-emerald-50 text-emerald-700' },
  pending: { label: 'Pendiente', cls: 'bg-amber-100 text-amber-700' },
  declined: { label: 'Rechazada', cls: 'bg-red-50 text-red-700' },
  error: { label: 'Con error', cls: 'bg-red-50 text-red-700' },
  voided: { label: 'Anulada', cls: 'bg-gray-100 text-gray-500' },
};

function fechaCorta(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('es-CO', { year: 'numeric', month: 'short', day: '2-digit' });
}

/** Envía el form de Wompi creando un `<form>` real: es una navegación, no fetch. */
function irAWompi(form: CheckoutForm) {
  const el = document.createElement('form');
  el.method = form.method || 'GET';
  el.action = form.url;
  Object.entries(form.fields).forEach(([nombre, valor]) => {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = nombre;
    input.value = String(valor);
    el.appendChild(input);
  });
  document.body.appendChild(el);
  el.submit();
}

export default function Pagos() {
  const router = useRouter();
  const [permitido, setPermitido] = useState<boolean | null>(null);
  const [paquetes, setPaquetes] = useState<Paquete[] | null>(null);
  const [saldo, setSaldo] = useState<Saldo | null>(null);
  const [comprando, setComprando] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verDetalle, setVerDetalle] = useState<string | null>(null);

  // ¿Volvemos de Wompi? El id de la transacción llega por query string.
  const volviendoDePago = Boolean(router.query.id || router.query.ref);
  const [estadoPago, setEstadoPago] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      const acceso = await authedFetch<{ allowed: boolean }>('/pagos/access');
      if (!acceso?.allowed) {
        setPermitido(false);
        return;
      }
      setPermitido(true);
      const [cat, sal] = await Promise.all([
        authedFetch<{ paquetes: Paquete[] }>('/pagos/paquetes'),
        authedFetch<Saldo>('/pagos/saldo'),
      ]);
      setPaquetes(cat.paquetes);
      setSaldo(sal);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setPermitido(false);
        return;
      }
      setError('No se pudieron cargar los datos de pagos.');
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Al volver de Wompi el webhook puede tardar unos segundos en llegar:
  // refrescamos el saldo un par de veces en vez de dejar al usuario recargando.
  useEffect(() => {
    if (!volviendoDePago || permitido !== true) return;
    const t1 = window.setTimeout(cargar, 4000);
    const t2 = window.setTimeout(cargar, 12000);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [volviendoDePago, permitido, cargar]);

  // ¿Entró el pago? Se le pregunta a Wompi por el id que trae la URL. Es solo
  // para informar: los créditos no dependen de esto.
  useEffect(() => {
    const id = router.query.id;
    if (!id || typeof id !== 'string' || permitido !== true) return;
    let cancelado = false;
    authedFetch<{ estado: string }>(`/pagos/transaccion/${encodeURIComponent(id)}`)
      .then((r) => {
        if (!cancelado) setEstadoPago(r?.estado ?? 'desconocido');
      })
      .catch(() => {
        if (!cancelado) setEstadoPago('desconocido');
      });
    return () => {
      cancelado = true;
    };
  }, [router.query.id, permitido]);

  const comprar = async (key: string) => {
    setComprando(key);
    setError(null);
    try {
      const res = await authedFetch<Checkout>('/pagos/checkout', {
        method: 'POST',
        body: JSON.stringify({ package_key: key }),
      });
      irAWompi(res.checkout);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'No se pudo iniciar el pago.';
      setError(msg);
      setComprando(null);
    }
  };

  if (permitido === false) {
    return (
      <Layout variant="fullscreen">
        <div className="p-8 w-full bg-gloma-cream min-h-screen font-body">
          <div className="max-w-lg mx-auto mt-16 bg-white border border-gloma-brown-light/20 rounded-2xl p-8 text-center shadow-sm">
            <div className="text-5xl mb-4">🔒</div>
            <h1 className="font-heading text-xl font-bold text-gloma-brown-dark">
              Sección de administrador
            </h1>
            <p className="text-sm text-gloma-brown-light mt-2">
              Los pagos y el saldo de mensajes los maneja el dueño de la cuenta.
              Si necesitas recargar, pídeselo a quien administra tu cuenta de Gloma.
            </p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        <div className="mb-6">
          <h1 className="font-heading text-2xl md:text-3xl font-extrabold text-gloma-brown-dark">
            Pagos y créditos
          </h1>
          <p className="text-sm text-gloma-brown-light mt-1">
            Cada mensaje de un envío masivo consume un crédito. Aquí recargas.
          </p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm">
            {error}
          </div>
        )}

        {volviendoDePago && (
          <div
            className={`px-4 py-3 rounded-lg mb-6 text-sm border ${
              estadoPago === 'aprobado'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
                : estadoPago === 'rechazado'
                ? 'bg-red-50 border-red-200 text-red-800'
                : 'bg-gloma-rose-soft/50 border-gloma-mint/40 text-gloma-brown-dark'
            }`}
          >
            {estadoPago === 'aprobado' && (
              <>
                <strong>✅ Recibimos tu pago.</strong> Tus mensajes quedan
                habilitados en <strong>aproximadamente 1 hora</strong>. Mientras
                tanto puedes seguir usando la plataforma con normalidad; el saldo
                de arriba se actualiza cuando queden cargados.
              </>
            )}
            {estadoPago === 'rechazado' && (
              <>
                <strong>❌ No recibimos el pago.</strong> La transacción no se
                completó, así que no se hizo ningún cobro. Puedes intentarlo de
                nuevo con el botón Comprar, o con otro medio de pago.
              </>
            )}
            {(estadoPago === null ||
              estadoPago === 'pendiente' ||
              estadoPago === 'desconocido') && (
              <>
                <strong>Estamos confirmando tu pago.</strong> Si quedó aprobado,
                tus mensajes se habilitan en{' '}
                <strong>aproximadamente 1 hora</strong>. Esta página se actualiza
                sola.
              </>
            )}
          </div>
        )}

        {/* Saldo */}
        <section className="mb-8">
          <div className="rounded-2xl bg-gloma-brown text-gloma-cream p-6 shadow-sm max-w-sm">
            <p className="text-[10px] uppercase tracking-widest text-gloma-rose">
              Saldo disponible
            </p>
            <p className="font-heading text-4xl font-extrabold mt-2">
              {saldo ? saldo.message_credits.toLocaleString('es-CO') : '—'}
            </p>
            <p className="text-[11px] text-gloma-rose-soft mt-1">
              mensajes para envíos masivos
            </p>
          </div>
        </section>

        {/* Paquetes */}
        <section className="mb-10">
          <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
            Recargar
          </h2>
          {!paquetes ? (
            <p className="text-sm text-gloma-brown-light">Cargando paquetes…</p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 max-w-3xl">
              {paquetes.map((p) => (
                <div
                  key={p.key}
                  className="rounded-2xl bg-white border border-gloma-brown-light/20 p-6 shadow-sm flex flex-col"
                >
                  <p className="font-heading text-xl font-bold text-gloma-brown-dark">
                    {p.nombre}
                  </p>
                  <p className="text-sm text-gloma-brown-light mt-1">{p.descripcion}</p>

                  <p className="font-heading text-3xl font-extrabold text-gloma-brown mt-4">
                    {COP.format(p.amount_cop)}
                  </p>
                  <p className="text-xs text-gloma-brown-light">
                    {p.messages.toLocaleString('es-CO')} mensajes ·{' '}
                    {COP.format(p.precio_por_mensaje_cop)} c/u
                  </p>

                  {/* Dos caminos: el link de pago que se crea a mano en Wompi
                      (no necesita llaves y funciona desde el día uno) o el
                      checkout por API. Si hay link, gana el link. */}
                  {p.link_pago ? (
                    <a
                      href={p.link_pago}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-5 px-4 py-2.5 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark transition-colors text-center"
                    >
                      Comprar
                    </a>
                  ) : (
                    <button
                      type="button"
                      onClick={() => comprar(p.key)}
                      disabled={comprando !== null}
                      className="mt-5 px-4 py-2.5 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {comprando === p.key ? 'Abriendo el pago…' : 'Comprar'}
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => setVerDetalle(verDetalle === p.key ? null : p.key)}
                    className="mt-2 text-xs underline text-gloma-brown-light hover:text-gloma-brown-dark"
                  >
                    {verDetalle === p.key ? 'Ocultar detalle' : 'Ver en qué se va el valor'}
                  </button>

                  {verDetalle === p.key && (
                    <dl className="mt-3 text-xs text-gloma-brown-dark bg-gloma-cream rounded-lg p-3 space-y-1">
                      <div className="flex justify-between">
                        <dt>Costo de los mensajes</dt>
                        <dd>{COP.format(p.desglose.costo_cop)}</dd>
                      </div>
                      <div className="flex justify-between">
                        <dt>Comisión de la pasarela</dt>
                        <dd>{COP.format(p.desglose.comision_wompi_cop)}</dd>
                      </div>
                      <div className="flex justify-between font-semibold border-t border-gloma-brown-light/20 pt-1">
                        <dt>Total que pagas</dt>
                        <dd>{COP.format(p.amount_cop)}</dd>
                      </div>
                      {p.desglose.trm_fecha && (
                        <p className="text-[10px] text-gloma-brown-light pt-1">
                          Calculado con la TRM del {p.desglose.trm_fecha}.
                        </p>
                      )}
                    </dl>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Historial */}
        <section>
          <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
            Compras
          </h2>
          {!saldo || saldo.compras.length === 0 ? (
            <p className="text-sm text-gloma-brown-light">
              Todavía no has comprado paquetes.
            </p>
          ) : (
            <div className="bg-white rounded-2xl border border-gloma-brown-light/20 overflow-hidden max-w-3xl">
              <table className="w-full text-sm">
                <thead className="bg-gloma-brown text-gloma-cream">
                  <tr>
                    <th className="text-left py-2.5 px-4 font-semibold text-xs">Fecha</th>
                    <th className="text-left py-2.5 px-4 font-semibold text-xs">Paquete</th>
                    <th className="text-right py-2.5 px-4 font-semibold text-xs">Valor</th>
                    <th className="text-left py-2.5 px-4 font-semibold text-xs">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {saldo.compras.map((c) => {
                    const est = ESTADOS[c.status] ?? {
                      label: c.status,
                      cls: 'bg-gray-100 text-gray-600',
                    };
                    return (
                      <tr key={c.id} className="border-t border-gloma-brown-light/10">
                        <td className="py-2.5 px-4 text-gloma-brown-dark">
                          {fechaCorta(c.created_at)}
                        </td>
                        <td className="py-2.5 px-4 text-gloma-brown-dark">
                          {c.messages.toLocaleString('es-CO')} mensajes
                        </td>
                        <td className="py-2.5 px-4 text-right text-gloma-brown-dark">
                          {COP.format(Math.round(c.amount_cents / 100))}
                        </td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold ${est.cls}`}
                          >
                            {est.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </Layout>
  );
}
