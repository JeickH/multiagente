/**
 * Detalle de Campaña (Sprint 13 — tarea #166).
 *
 * Contrato visual: `identidad_gloma/diseno_campanas.html` Pantalla 3.
 * Endpoints consumidos:
 *   - GET  /campaigns/{id}                          → detalle + KPIs
 *   - GET  /campaigns/{id}/recipients?limit&offset&status → paginado
 *   - POST /campaigns/{id}/cancel                   → cancela (draft|scheduled)
 *
 * Auth: JWT en localStorage via `lib/api.ts`.
 *
 * Polling: si `status ∈ {scheduled, running}` se refrescan detalle y
 * página actual de destinatarios cada 5s. El intervalo se limpia al
 * cambiar de status terminal (`completed|cancelled|failed`) o al unmount.
 */
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import Layout from '../../components/Layout';
import { ApiError, authedFetch } from '../../lib/api';
import {
  fmtDateTime,
  fmtNumber,
  fmtPct,
  fmtTime,
  maskPhone,
} from '../../lib/format';
import type {
  CampaignDetail,
  CampaignRecipient,
  CampaignRecipientsPage,
  RecipientStatus,
} from '../../types/campaigns';

const PAGE_SIZE = 50;

const RECIPIENT_STATUSES: { value: '' | RecipientStatus; label: string }[] = [
  { value: '', label: 'Todos los estados' },
  { value: 'queued', label: 'En cola' },
  { value: 'sending', label: 'Enviando' },
  { value: 'sent', label: 'Enviados' },
  { value: 'delivered', label: 'Entregados' },
  { value: 'read', label: 'Leídos' },
  { value: 'failed', label: 'Fallidos' },
  { value: 'skipped', label: 'Omitidos' },
];

function campaignStatusBadge(status: string) {
  const map: Record<string, { label: string; cls: string }> = {
    completed: {
      label: 'Terminado',
      cls: 'bg-gloma-rose-soft/40 text-gloma-brown-dark',
    },
    running: { label: 'En curso', cls: 'bg-blue-100 text-blue-700' },
    scheduled: { label: 'Programada', cls: 'bg-amber-100 text-amber-700' },
    cancelled: { label: 'Cancelada', cls: 'bg-gray-100 text-gray-500' },
    failed: { label: 'Fallida', cls: 'bg-red-100 text-red-700' },
    draft: { label: 'Borrador', cls: 'bg-gray-100 text-gray-500' },
  };
  const entry = map[status] ?? {
    label: status,
    cls: 'bg-gray-100 text-gray-600',
  };
  return (
    <span
      className={`inline-block px-3 py-1 rounded-full text-[11px] font-semibold ${entry.cls}`}
    >
      {entry.label}
    </span>
  );
}

function recipientStatusBadge(status: string) {
  const map: Record<string, { label: string; cls: string }> = {
    queued: { label: 'En cola', cls: 'bg-gray-100 text-gray-600' },
    sending: { label: 'Enviando', cls: 'bg-blue-100 text-blue-700' },
    sent: { label: 'Enviado', cls: 'bg-amber-50 text-amber-800' },
    delivered: {
      label: 'Entregado',
      cls: 'bg-gloma-rose-soft text-gloma-brown-dark',
    },
    read: { label: 'Leído', cls: 'bg-green-50 text-green-800' },
    failed: { label: 'Fallido', cls: 'bg-red-50 text-red-800' },
    skipped: { label: 'Omitido', cls: 'bg-yellow-50 text-yellow-800' },
  };
  const entry = map[status] ?? {
    label: status,
    cls: 'bg-gray-100 text-gray-600',
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold ${entry.cls}`}
    >
      {entry.label}
    </span>
  );
}

interface DetailKpiCardProps {
  label: string;
  value: number;
  icon: string;
  primary?: boolean;
  hint?: string;
  emphasizeRed?: boolean;
}

function DetailKpiCard({
  label,
  value,
  icon,
  primary = false,
  hint,
  emphasizeRed = false,
}: DetailKpiCardProps) {
  if (primary) {
    return (
      <div className="rounded-2xl bg-gloma-brown text-gloma-cream p-4 shadow-sm flex flex-col">
        <div className="flex items-center justify-between">
          <p className="text-[10px] uppercase tracking-widest text-gloma-rose">
            {label}
          </p>
          <span className="text-lg opacity-80">{icon}</span>
        </div>
        <p className="font-heading text-3xl font-extrabold mt-2">
          {fmtNumber(value)}
        </p>
        {hint && (
          <p className="text-[11px] text-gloma-rose-soft mt-1">{hint}</p>
        )}
      </div>
    );
  }
  return (
    <div className="rounded-2xl bg-white border border-gloma-brown-light/20 p-4 shadow-sm flex flex-col">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-widest text-gloma-brown-light">
          {label}
        </p>
        <span className="text-base opacity-50">{icon}</span>
      </div>
      <p
        className={`font-heading text-2xl font-bold mt-2 ${
          emphasizeRed && value > 0
            ? 'text-red-700'
            : 'text-gloma-brown-dark'
        }`}
      >
        {fmtNumber(value)}
      </p>
      {hint && (
        <p className="text-[11px] text-gloma-brown-light mt-1">{hint}</p>
      )}
    </div>
  );
}

function ConfirmCancelModal({
  campaignName,
  busy,
  onCancel,
  onConfirm,
}: {
  campaignName: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 px-4"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6 border border-gloma-brown-light/20"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-heading text-xl font-bold text-gloma-brown-dark mb-2">
          Cancelar campaña
        </h3>
        <p className="text-sm text-gloma-brown-light mb-5">
          Estás a punto de cancelar la campaña{' '}
          <span className="font-semibold text-gloma-brown-dark">
            {campaignName}
          </span>
          . Los destinatarios que aún estén en cola no recibirán el mensaje.
          Esta acción no se puede deshacer.
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 rounded-lg border border-gloma-brown-light/30 text-gloma-brown-dark text-sm font-semibold hover:bg-gloma-cream disabled:opacity-50"
          >
            Volver
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm font-semibold hover:bg-red-700 disabled:opacity-50"
          >
            {busy ? 'Cancelando…' : 'Sí, cancelar'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function CampaignDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const campaignId = useMemo(() => {
    if (typeof id !== 'string') return null;
    const n = Number(id);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [id]);

  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [recipientsPage, setRecipientsPage] =
    useState<CampaignRecipientsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingRecipients, setLoadingRecipients] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recipientsError, setRecipientsError] = useState<string | null>(null);
  const [page, setPage] = useState(1); // 1-indexed
  const [filterStatus, setFilterStatus] = useState<'' | RecipientStatus>('');
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  // ref to keep latest detail status without retriggering polling effect
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadDetail = useCallback(async () => {
    if (!campaignId) return;
    try {
      const data = await authedFetch<CampaignDetail>(
        `/campaigns/${campaignId}`,
      );
      if (!isMountedRef.current) return;
      setDetail(data);
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) return;
      const msg =
        err instanceof ApiError
          ? err.status === 404
            ? 'Campaña no encontrada.'
            : err.message
          : 'No se pudo cargar la campaña.';
      setError(msg);
    }
  }, [campaignId]);

  const loadRecipients = useCallback(async () => {
    if (!campaignId) return;
    setLoadingRecipients(true);
    setRecipientsError(null);
    try {
      const offset = (page - 1) * PAGE_SIZE;
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (filterStatus) params.set('status', filterStatus);
      const data = await authedFetch<CampaignRecipientsPage>(
        `/campaigns/${campaignId}/recipients?${params.toString()}`,
      );
      if (!isMountedRef.current) return;
      setRecipientsPage(data);
    } catch (err) {
      if (!isMountedRef.current) return;
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No se pudieron cargar los destinatarios.';
      setRecipientsError(msg);
    } finally {
      if (isMountedRef.current) setLoadingRecipients(false);
    }
  }, [campaignId, page, filterStatus]);

  // Carga inicial (detalle + primera página de recipients)
  useEffect(() => {
    if (!campaignId) return;
    setLoading(true);
    Promise.all([loadDetail(), loadRecipients()]).finally(() => {
      if (isMountedRef.current) setLoading(false);
    });
  }, [campaignId, loadDetail, loadRecipients]);

  // Reset paginación cuando cambia filtro
  useEffect(() => {
    setPage(1);
  }, [filterStatus]);

  // Refrescar lista cuando cambian filtro o página (skip primera carga porque
  // la cubre el efecto anterior — usamos guard `detail` para evitar doble fetch).
  useEffect(() => {
    if (!campaignId || !detail) return;
    loadRecipients();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filterStatus]);

  // Polling 5s solo si la campaña está activa.
  const pollingActive =
    detail?.status === 'scheduled' || detail?.status === 'running';

  useEffect(() => {
    if (!campaignId || !pollingActive) return;
    const id = window.setInterval(() => {
      loadDetail();
      loadRecipients();
    }, 5000);
    return () => window.clearInterval(id);
  }, [campaignId, pollingActive, loadDetail, loadRecipients]);

  const canCancel =
    detail?.status === 'scheduled' || detail?.status === 'draft';

  const handleConfirmCancel = async () => {
    if (!campaignId) return;
    setCanceling(true);
    setCancelError(null);
    try {
      await authedFetch(`/campaigns/${campaignId}/cancel`, { method: 'POST' });
      setShowCancelModal(false);
      await loadDetail();
      await loadRecipients();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No se pudo cancelar la campaña.';
      setCancelError(msg);
    } finally {
      setCanceling(false);
    }
  };

  // Render principal
  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        {/* Breadcrumb + back */}
        <div className="flex items-center gap-2 text-xs text-gloma-brown-light mb-3">
          <Link href="/campanas" legacyBehavior>
            <a className="hover:text-gloma-brown-dark hover:underline">
              ← Volver
            </a>
          </Link>
          <span className="opacity-50">/</span>
          <Link href="/campanas" legacyBehavior>
            <a className="hover:text-gloma-brown-dark">
              Transmisiones masivas
            </a>
          </Link>
          <span className="opacity-50">/</span>
          <span className="text-gloma-brown-dark font-semibold truncate max-w-[40ch]">
            {detail?.name ?? (loading ? 'Cargando…' : 'Campaña')}
          </span>
        </div>

        {/* Error global */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm flex items-center justify-between">
            <span>{error}</span>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setLoading(true);
                Promise.all([loadDetail(), loadRecipients()]).finally(() => {
                  if (isMountedRef.current) setLoading(false);
                });
              }}
              className="ml-3 px-3 py-1 rounded-md bg-red-600 text-white text-xs font-semibold hover:bg-red-700"
            >
              Reintentar
            </button>
          </div>
        )}

        {/* Loader esqueleto inicial */}
        {loading && !detail ? (
          <div className="space-y-4">
            <div className="h-32 rounded-2xl bg-gloma-brown/20 animate-pulse" />
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-24 rounded-2xl bg-white border border-gloma-brown-light/20 animate-pulse"
                />
              ))}
            </div>
            <div className="h-64 rounded-2xl bg-white border border-gloma-brown-light/20 animate-pulse" />
          </div>
        ) : detail ? (
          <>
            {/* Cabecera de campaña */}
            <div className="rounded-2xl bg-gloma-brown text-gloma-cream px-6 py-5 mb-4 shadow-sm">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div className="min-w-0">
                  <h1 className="font-heading text-2xl md:text-3xl font-extrabold truncate">
                    {detail.name}
                  </h1>
                  <p className="text-xs text-gloma-rose-soft mt-2">
                    Plantilla{' '}
                    <span className="font-semibold text-gloma-cream">
                      {detail.template_name ?? '—'}
                    </span>
                    {detail.template_language && (
                      <span className="text-gloma-rose">
                        {' '}
                        ({detail.template_language})
                      </span>
                    )}
                  </p>
                  <p className="text-[11px] text-gloma-rose mt-1">
                    Creada {fmtDateTime(detail.created_at)}
                    {detail.scheduled_at &&
                      ` · Programada para ${fmtDateTime(detail.scheduled_at)}`}
                    {detail.started_at &&
                      ` · Iniciada ${fmtDateTime(detail.started_at)}`}
                    {detail.completed_at &&
                      ` · Finalizada ${fmtDateTime(detail.completed_at)}`}
                  </p>
                </div>
                <div className="flex flex-col md:items-end gap-3">
                  {campaignStatusBadge(detail.status)}
                  <div className="flex flex-wrap gap-2">
                    {canCancel && (
                      <button
                        type="button"
                        onClick={() => setShowCancelModal(true)}
                        className="px-3 py-1.5 text-xs rounded-lg bg-red-600 text-white font-semibold hover:bg-red-700"
                      >
                        Cancelar campaña
                      </button>
                    )}
                    <button
                      type="button"
                      disabled
                      title="Próximamente"
                      className="px-3 py-1.5 text-xs rounded-lg bg-white/90 text-gloma-brown-dark font-semibold opacity-50 cursor-not-allowed"
                    >
                      Duplicar
                    </button>
                    <button
                      type="button"
                      disabled
                      title="Próximamente"
                      className="px-3 py-1.5 text-xs rounded-lg bg-white/90 text-gloma-brown-dark font-semibold opacity-50 cursor-not-allowed"
                    >
                      Exportar CSV
                    </button>
                  </div>
                  {cancelError && (
                    <p className="text-[11px] text-red-200 max-w-xs text-right">
                      {cancelError}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Banners de estado */}
            {detail.skipped > 0 && (
              <div className="bg-yellow-50 border border-yellow-200 text-yellow-900 px-4 py-3 rounded-lg mb-4 text-sm flex items-start gap-2">
                <span aria-hidden>ℹ️</span>
                <span>
                  <strong>{fmtNumber(detail.skipped)} contacto(s)</strong>{' '}
                  fueron omitidos porque no tenían opt-in activo o lo
                  revocaron antes del envío.
                </span>
              </div>
            )}
            {detail.status === 'failed' && (
              <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg mb-4 text-sm flex items-start gap-2">
                <span aria-hidden>⚠️</span>
                <span>
                  Esta campaña falló de forma global. Revisa la columna
                  &quot;Error&quot; de los destinatarios para más detalles
                  o consulta los registros de la integración con Meta.
                </span>
              </div>
            )}
            {pollingActive && (
              <p className="text-[11px] text-gloma-brown-light mb-3">
                Actualizando KPIs cada 5 segundos…
              </p>
            )}

            {/* KPIs (6 cards) */}
            <section className="mb-6">
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3 md:gap-4">
                <DetailKpiCard
                  label="Total destinatarios"
                  value={detail.total_recipients}
                  icon="👥"
                  primary
                  hint={
                    detail.pending > 0
                      ? `${fmtNumber(detail.pending)} pendientes`
                      : undefined
                  }
                />
                <DetailKpiCard
                  label="Enviado"
                  value={detail.sent}
                  icon="✉️"
                  hint={fmtPct(detail.sent, detail.total_recipients)}
                />
                <DetailKpiCard
                  label="Entregado"
                  value={detail.delivered}
                  icon="✓"
                  hint={fmtPct(detail.delivered, detail.total_recipients)}
                />
                <DetailKpiCard
                  label="Leído"
                  value={detail.read}
                  icon="👁️"
                  hint={
                    detail.delivered > 0
                      ? `${fmtPct(detail.read, detail.delivered)} de entregados`
                      : '—'
                  }
                />
                <DetailKpiCard
                  label="Fallido"
                  value={detail.failed}
                  icon="⚠️"
                  hint={fmtPct(detail.failed, detail.total_recipients)}
                  emphasizeRed
                />
                <DetailKpiCard
                  label="Omitidos"
                  value={detail.skipped}
                  icon="🚫"
                  hint={fmtPct(detail.skipped, detail.total_recipients)}
                />
              </div>
            </section>

            {/* Tabla destinatarios */}
            <section>
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-3">
                <h2 className="font-heading text-lg font-bold text-gloma-brown-dark">
                  Destinatarios
                  {recipientsPage && (
                    <span className="text-xs text-gloma-brown-light font-normal ml-2">
                      ({fmtNumber(recipientsPage.total)} en total)
                    </span>
                  )}
                </h2>
                <div className="flex gap-2">
                  <select
                    value={filterStatus}
                    onChange={(e) =>
                      setFilterStatus(
                        e.target.value as '' | RecipientStatus,
                      )
                    }
                    className="text-sm px-3 py-1.5 border border-gloma-brown-light/30 rounded-lg bg-white focus:outline-none focus:border-gloma-brown"
                  >
                    {RECIPIENT_STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="bg-white border border-gloma-brown-light/20 rounded-2xl overflow-hidden shadow-sm">
                {recipientsError ? (
                  <div className="p-6 text-sm text-red-700 bg-red-50 border-b border-red-200">
                    {recipientsError}
                    <button
                      type="button"
                      onClick={() => loadRecipients()}
                      className="ml-3 underline font-semibold"
                    >
                      Reintentar
                    </button>
                  </div>
                ) : loadingRecipients && !recipientsPage ? (
                  <div className="p-6 space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <div
                        key={i}
                        className="h-9 rounded-lg bg-gloma-brown-light/10 animate-pulse"
                      />
                    ))}
                  </div>
                ) : !recipientsPage || recipientsPage.items.length === 0 ? (
                  <div className="p-10 text-center">
                    <div className="w-14 h-14 mx-auto rounded-full bg-gloma-rose-soft flex items-center justify-center text-2xl mb-3">
                      📭
                    </div>
                    <h3 className="font-heading text-lg font-bold text-gloma-brown-dark mb-1">
                      Sin destinatarios
                    </h3>
                    <p className="text-sm text-gloma-brown-light max-w-sm mx-auto">
                      {filterStatus
                        ? 'No hay destinatarios con ese estado en esta campaña.'
                        : 'Esta campaña aún no tiene destinatarios registrados.'}
                    </p>
                  </div>
                ) : (
                  <RecipientsTable
                    items={recipientsPage.items}
                    page={page}
                    pageSize={PAGE_SIZE}
                    total={recipientsPage.total}
                    onPageChange={setPage}
                    refreshing={loadingRecipients}
                  />
                )}
              </div>
            </section>
          </>
        ) : null}

        {showCancelModal && detail && (
          <ConfirmCancelModal
            campaignName={detail.name}
            busy={canceling}
            onCancel={() => {
              if (!canceling) setShowCancelModal(false);
            }}
            onConfirm={handleConfirmCancel}
          />
        )}
      </div>
    </Layout>
  );
}

interface RecipientsTableProps {
  items: CampaignRecipient[];
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (next: number) => void;
  refreshing: boolean;
}

function RecipientsTable({
  items,
  page,
  pageSize,
  total,
  onPageChange,
  refreshing,
}: RecipientsTableProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);
  const from = (safePage - 1) * pageSize + 1;
  const to = Math.min(safePage * pageSize, total);

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="bg-gloma-cream text-gloma-brown-light">
          <tr>
            <th className="text-left font-medium px-4 py-2">Teléfono</th>
            <th className="text-left font-medium px-4 py-2">Estado</th>
            <th className="text-left font-medium px-4 py-2">Enviado</th>
            <th className="text-left font-medium px-4 py-2">Entregado</th>
            <th className="text-left font-medium px-4 py-2">Leído</th>
            <th className="text-left font-medium px-4 py-2">Error</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gloma-brown-light/10">
          {items.map((r) => (
            <tr
              key={r.id}
              className="hover:bg-gloma-rose-soft/30 transition-colors"
            >
              <td className="px-4 py-2 font-mono text-xs text-gloma-brown-dark">
                {maskPhone(r.phone_e164)}
              </td>
              <td className="px-4 py-2">{recipientStatusBadge(r.status)}</td>
              <td className="px-4 py-2 text-gloma-brown-light text-xs">
                {fmtTime(r.sent_at)}
              </td>
              <td className="px-4 py-2 text-gloma-brown-light text-xs">
                {fmtTime(r.delivered_at)}
              </td>
              <td className="px-4 py-2 text-gloma-brown-light text-xs">
                {fmtTime(r.read_at)}
              </td>
              <td className="px-4 py-2 text-xs">
                {r.error_code ? (
                  <span
                    className="text-red-700 truncate inline-block max-w-[18ch]"
                    title={r.error_code}
                  >
                    {r.error_code}
                  </span>
                ) : (
                  <span className="text-gloma-brown-light">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-4 py-3 border-t border-gloma-brown-light/15 flex items-center justify-between text-xs text-gloma-brown-light">
        <span>
          Mostrando {fmtNumber(from)}–{fmtNumber(to)} de {fmtNumber(total)}{' '}
          destinatarios
          {refreshing && (
            <span className="ml-2 text-gloma-brown">· actualizando…</span>
          )}
        </span>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, safePage - 1))}
            disabled={safePage <= 1}
            className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
          >
            ← Anterior
          </button>
          <span className="px-3 py-1 rounded-md bg-gloma-brown text-gloma-cream font-semibold">
            {safePage} / {totalPages}
          </span>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, safePage + 1))}
            disabled={safePage >= totalPages}
            className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
          >
            Siguiente →
          </button>
        </div>
      </div>
    </div>
  );
}
