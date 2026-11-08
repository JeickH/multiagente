import { useState } from 'react';
import { fechaHoraCorta, fechaHoraLarga } from '../lib/fechas';
import {
  MOTIVO_MAX,
  VENTA_NOTA_MAX,
  Venta,
  formatearPesos,
  leerValorPesos,
  problemaConMotivo,
} from '../lib/venta';

/**
 * «Venta cerrada» de la conversación abierta en la bandeja (Sprint 36).
 *
 * Tres estados en la misma franja, debajo de la cabecera del chat:
 *   - hay venta activa → se ve el valor, quién vendió y cuándo, con «Anular»;
 *   - `abierto` (la asesora pulsó el botón de la cabecera) → el formulario;
 *   - si no, nada (o solo el rastro de las anuladas, plegado).
 *
 * La venta no se edita: para corregir un valor se anula con motivo y se
 * registra otra. El backend es quien decide permisos y team; ocultar el botón a
 * quien no puede responder es solo para no mostrar un control que daría 403.
 *
 * La nota y el motivo se pintan como TEXTO (React escapa): los escribe una
 * persona y pueden traer cualquier cosa.
 */
export default function VentaCerrada({
  conversationId,
  venta,
  anuladas,
  asesores,
  puedeRegistrar,
  abierto,
  onCerrar,
  authHeaders,
  onCambio,
}: {
  conversationId: number;
  venta: Venta | null;
  anuladas: Venta[];
  asesores: string[];
  puedeRegistrar: boolean;
  abierto: boolean;
  onCerrar: () => void;
  authHeaders: () => HeadersInit;
  /** Se llama tras registrar o anular, con el valor activo que quedó. */
  onCambio: (valorActivo: number | null) => void;
}) {
  const [valorTexto, setValorTexto] = useState('');
  const [vendidaPor, setVendidaPor] = useState('');
  const [nota, setNota] = useState('');
  const [anulando, setAnulando] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verAnuladas, setVerAnuladas] = useState(false);

  /** El mensaje del backend si es texto; si es la lista de errores de
      validación, uno genérico (no se le muestra JSON técnico a la asesora). */
  const mensajeDeError = async (res: Response, generico: string) => {
    const data = await res.json().catch(() => ({}));
    return typeof data?.detail === 'string' ? data.detail : generico;
  };

  const registrar = async () => {
    if (enviando) return;
    const leido = leerValorPesos(valorTexto);
    if (!leido.ok || leido.valor == null) {
      setError(leido.motivo || 'Revisa el valor de la venta.');
      return;
    }
    if (!vendidaPor) {
      setError('Elige quién hizo la venta.');
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const res = await fetch(`/api/mensajes/conversaciones/${conversationId}/venta`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          valor_cop: leido.valor,
          vendida_por: vendidaPor,
          nota: nota.trim() || null,
        }),
      });
      if (!res.ok) {
        throw new Error(await mensajeDeError(res, 'Revisa los datos de la venta e inténtalo de nuevo.'));
      }
      setValorTexto('');
      setVendidaPor('');
      setNota('');
      onCerrar();
      onCambio(leido.valor);
    } catch (e: any) {
      setError(e?.message || 'No se pudo registrar la venta. Inténtalo de nuevo.');
    } finally {
      setEnviando(false);
    }
  };

  const anular = async () => {
    if (enviando) return;
    const problema = problemaConMotivo(motivo);
    if (problema) {
      setError(problema);
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      const res = await fetch(`/api/mensajes/conversaciones/${conversationId}/venta/anular`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ motivo: motivo.trim() }),
      });
      if (!res.ok) {
        throw new Error(await mensajeDeError(res, 'No se pudo anular la venta.'));
      }
      setMotivo('');
      setAnulando(false);
      onCambio(null);
    } catch (e: any) {
      setError(e?.message || 'No se pudo anular la venta. Inténtalo de nuevo.');
    } finally {
      setEnviando(false);
    }
  };

  const leido = valorTexto ? leerValorPesos(valorTexto) : null;
  const rastro =
    anuladas.length > 0 ? (
      <div className="mt-2">
        <button
          type="button"
          onClick={() => setVerAnuladas((v) => !v)}
          className="text-[11px] text-gloma-brown-light underline hover:text-gloma-forest"
        >
          {verAnuladas ? 'Ocultar' : 'Ver'} {anuladas.length}{' '}
          {anuladas.length === 1 ? 'venta anulada' : 'ventas anuladas'}
        </button>
        {verAnuladas && (
          <ul className="mt-1 space-y-1">
            {anuladas.map((v) => (
              <li key={v.id} className="text-[11px] text-gray-500">
                <span className="line-through">{formatearPesos(v.valor_cop)}</span>
                {v.vendida_por && <> · {v.vendida_por}</>}
                {' · anulada '}
                <span title={fechaHoraLarga(v.anulada_at)}>{fechaHoraCorta(v.anulada_at)}</span>
                {v.motivo_anulacion && (
                  <span className="block whitespace-pre-wrap break-words italic">
                    Motivo: {v.motivo_anulacion}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    ) : null;

  // ── Hay venta activa ──────────────────────────────────────────────────
  if (venta) {
    return (
      <div className="bg-gloma-soft-mint border-b border-gloma-mint/40 px-6 py-3">
        <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gloma-forest">
              💰 Venta cerrada · {formatearPesos(venta.valor_cop)}
            </div>
            <div className="text-xs text-gloma-brown-light">
              {venta.vendida_por ? <>Vendió {venta.vendida_por} · </> : null}
              <span title={fechaHoraLarga(venta.registrada_at)}>
                {fechaHoraCorta(venta.registrada_at)}
              </span>
              {venta.registrada_por_nombre ? <> · registrada por {venta.registrada_por_nombre}</> : null}
            </div>
            {venta.nota && (
              <div className="mt-1 text-xs text-gray-700 whitespace-pre-wrap break-words">{venta.nota}</div>
            )}
          </div>
          {puedeRegistrar && !anulando && (
            <button
              type="button"
              onClick={() => {
                setAnulando(true);
                setError(null);
              }}
              className="ml-auto px-2.5 py-1 text-xs rounded-full border border-gray-300 bg-white text-gray-600 font-medium hover:bg-gray-50"
              title="Anular esta venta (por ejemplo, si el valor quedó mal). Se puede registrar otra después."
            >
              Anular
            </button>
          )}
        </div>

        {anulando && (
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="flex-1 min-w-[16rem]">
              <span className="text-[11px] text-gray-600">¿Por qué se anula? (queda registrado)</span>
              <input
                type="text"
                value={motivo}
                maxLength={MOTIVO_MAX}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder="Ej.: el valor quedó mal digitado"
                className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-gloma-mint"
                autoFocus
              />
            </label>
            <button
              type="button"
              onClick={() => void anular()}
              disabled={enviando}
              className="px-3 py-1.5 text-xs rounded-lg bg-red-600 text-white font-medium hover:bg-red-700 disabled:opacity-50"
            >
              {enviando ? 'Anulando…' : 'Anular venta'}
            </button>
            <button
              type="button"
              onClick={() => {
                setAnulando(false);
                setMotivo('');
                setError(null);
              }}
              disabled={enviando}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
            >
              Cancelar
            </button>
          </div>
        )}
        {error && <div className="mt-2 text-xs text-red-600" role="alert">{error}</div>}
        {rastro}
      </div>
    );
  }

  // ── Formulario ────────────────────────────────────────────────────────
  if (abierto && puedeRegistrar) {
    return (
      <div className="bg-gloma-soft-mint border-b border-gloma-mint/40 px-6 py-3">
        <div className="text-sm font-semibold text-gloma-forest mb-2">💰 Registrar venta cerrada</div>
        <div className="flex flex-wrap items-start gap-3">
          <label className="w-44">
            <span className="text-[11px] text-gray-600">Valor en pesos</span>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              value={valorTexto}
              onChange={(e) => setValorTexto(e.target.value.replace(/[^\d.$\s]/g, ''))}
              placeholder="1.250.000"
              className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-gloma-mint"
              autoFocus
            />
            {leido?.ok && leido.valor != null && (
              <span className="block text-[11px] text-gloma-brown-light mt-0.5">
                {formatearPesos(leido.valor)}
              </span>
            )}
          </label>
          <label className="w-48">
            <span className="text-[11px] text-gray-600">¿Quién vendió?</span>
            <select
              value={vendidaPor}
              onChange={(e) => setVendidaPor(e.target.value)}
              className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:border-gloma-mint"
            >
              <option value="">Elige…</option>
              {asesores.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </label>
          <label className="flex-1 min-w-[14rem]">
            <span className="text-[11px] text-gray-600">Nota (opcional)</span>
            <textarea
              rows={1}
              value={nota}
              maxLength={VENTA_NOTA_MAX}
              onChange={(e) => setNota(e.target.value)}
              placeholder="Ej.: pagó en la oficina"
              className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white resize-y focus:outline-none focus:border-gloma-mint"
            />
            {nota.length > VENTA_NOTA_MAX - 40 && (
              <span className="block text-right text-[11px] text-gray-500">
                {nota.length}/{VENTA_NOTA_MAX}
              </span>
            )}
          </label>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void registrar()}
            disabled={enviando}
            className="px-4 py-1.5 text-sm rounded-lg bg-gloma-forest text-white font-medium hover:bg-gloma-brown-dark disabled:opacity-50"
          >
            {enviando ? 'Guardando…' : 'Guardar venta'}
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null);
              onCerrar();
            }}
            disabled={enviando}
            className="px-4 py-1.5 text-sm rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
          >
            Cancelar
          </button>
          {error && <span className="text-xs text-red-600" role="alert">{error}</span>}
        </div>
        {rastro}
      </div>
    );
  }

  // ── Sin venta: solo el rastro de las anuladas, si hay ─────────────────
  return rastro ? <div className="bg-white border-b border-gloma-rose-soft px-6 pb-2">{rastro}</div> : null;
}
