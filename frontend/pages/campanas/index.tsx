/**
 * Dashboard de Campañas (Sprint 13 — tarea #164).
 *
 * Contrato visual: `identidad_gloma/diseno_campanas.html` pantalla 1.
 * Endpoints consumidos:
 *   - GET /campaigns/kpis    → KPIs globales del team
 *   - GET /campaigns         → listado con KPIs por campaña
 *   - POST /campaigns/{id}/cancel
 *
 * Auth: JWT en localStorage, fetch vía `lib/api.ts`.
 */
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import Layout from '../../components/Layout';
import { ApiError, authedFetch } from '../../lib/api';
import type { CampaignSummary, GlobalKPIs } from '../../types/campaigns';

type Tab = 'resumen' | 'plantillas' | 'programadas';
type SortMode = 'recent' | 'most_successful' | 'most_read';

const PAGE_SIZE = 10;

function fmtNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '0';
  return new Intl.NumberFormat('es-MX').format(n);
}

function fmtPct(part: number, total: number): string {
  if (!total) return '0%';
  return `${((part / total) * 100).toFixed(1)}%`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('es-MX', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  });
}

function statusBadge(status: string) {
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
  const entry = map[status] ?? { label: status, cls: 'bg-gray-100 text-gray-600' };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold ${entry.cls}`}
    >
      {entry.label}
    </span>
  );
}

interface KpiCardProps {
  label: string;
  value: number;
  icon: string;
  primary?: boolean;
  hint?: string;
}

function KpiCard({ label, value, icon, primary = false, hint }: KpiCardProps) {
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
      <p className="font-heading text-2xl font-bold mt-2 text-gloma-brown-dark">
        {fmtNumber(value)}
      </p>
      {hint && (
        <p className="text-[11px] text-gloma-brown-light mt-1">{hint}</p>
      )}
    </div>
  );
}

function KpiSkeleton({ primary = false }: { primary?: boolean }) {
  return (
    <div
      className={`rounded-2xl p-4 h-[110px] animate-pulse ${
        primary
          ? 'bg-gloma-brown/40'
          : 'bg-white border border-gloma-brown-light/20'
      }`}
    >
      <div
        className={`h-3 w-16 rounded ${primary ? 'bg-gloma-rose-soft/40' : 'bg-gloma-brown-light/20'}`}
      />
      <div
        className={`h-7 w-24 mt-3 rounded ${primary ? 'bg-gloma-cream/50' : 'bg-gloma-brown-light/20'}`}
      />
    </div>
  );
}

function OverviewCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl bg-white border border-gloma-brown-light/20 p-4 shadow-sm">
      <p className="text-[10px] uppercase tracking-widest text-gloma-brown-light">
        {label}
      </p>
      <p className="font-heading text-xl font-bold mt-1 text-gloma-brown-dark">
        {value}
      </p>
      {hint && (
        <p className="text-[11px] text-gloma-brown-light mt-1">{hint}</p>
      )}
    </div>
  );
}

export default function CampanasDashboard() {
  const [kpis, setKpis] = useState<GlobalKPIs | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('resumen');
  const [search, setSearch] = useState('');
  const [sortMode, setSortMode] = useState<SortMode>('recent');
  const [page, setPage] = useState(1);
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      authedFetch<GlobalKPIs>('/campaigns/kpis'),
      authedFetch<CampaignSummary[]>('/campaigns?limit=500'),
    ])
      .then(([k, c]) => {
        if (cancelled) return;
        setKpis(k);
        setCampaigns(c);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : 'No se pudieron cargar los datos.';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // Reset page when filter changes
  useEffect(() => {
    setPage(1);
  }, [search, tab, sortMode]);

  const filteredSorted = useMemo<CampaignSummary[]>(() => {
    if (!campaigns) return [];
    let list = campaigns.slice();
    if (tab === 'programadas') {
      list = list.filter((c) => c.status === 'scheduled');
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((c) => c.name.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      if (sortMode === 'most_successful') {
        return b.delivered - a.delivered;
      }
      if (sortMode === 'most_read') {
        return b.read - a.read;
      }
      // recent: created_at desc
      return (
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    });
    return list;
  }, [campaigns, search, sortMode, tab]);

  const totalPages = Math.max(1, Math.ceil(filteredSorted.length / PAGE_SIZE));
  const pageSafe = Math.min(page, totalPages);
  const pageItems = filteredSorted.slice(
    (pageSafe - 1) * PAGE_SIZE,
    pageSafe * PAGE_SIZE,
  );

  const handleCancel = async (id: number) => {
    if (!window.confirm('¿Cancelar esta campaña programada?')) return;
    setCancelingId(id);
    try {
      await authedFetch(`/campaigns/${id}/cancel`, { method: 'POST' });
      setReloadTick((t) => t + 1);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No se pudo cancelar la campaña.';
      window.alert(msg);
    } finally {
      setCancelingId(null);
    }
  };

  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-6">
          <div>
            <h1 className="font-heading text-2xl md:text-3xl font-extrabold text-gloma-brown-dark">
              Transmisiones masivas
            </h1>
            <p className="text-sm text-gloma-brown-light mt-1">
              Envíos masivos por WhatsApp Business — campañas y plantillas.
            </p>
          </div>
          <Link href="/campanas/nueva" legacyBehavior>
            <a className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark transition-colors">
              + Nueva campaña
            </a>
          </Link>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 text-sm border-b border-gloma-brown-light/20">
          <button
            type="button"
            onClick={() => setTab('resumen')}
            className={`px-4 py-2 border-b-2 transition-colors ${
              tab === 'resumen'
                ? 'border-gloma-brown text-gloma-brown-dark font-semibold'
                : 'border-transparent text-gloma-brown-light hover:text-gloma-brown'
            }`}
          >
            Resumen de campaña
          </button>
          <Link href="/campanas/plantillas" legacyBehavior>
            <a className="px-4 py-2 border-b-2 border-transparent text-gloma-brown-light hover:text-gloma-brown">
              Mensajes de plantilla
            </a>
          </Link>
          <button
            type="button"
            onClick={() => setTab('programadas')}
            className={`px-4 py-2 border-b-2 transition-colors ${
              tab === 'programadas'
                ? 'border-gloma-brown text-gloma-brown-dark font-semibold'
                : 'border-transparent text-gloma-brown-light hover:text-gloma-brown'
            }`}
          >
            Campañas programadas
          </button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm flex items-center justify-between">
            <span>
              No se pudieron cargar los datos.{' '}
              <span className="text-red-500/80">({error})</span>
            </span>
            <button
              type="button"
              onClick={() => setReloadTick((t) => t + 1)}
              className="ml-3 px-3 py-1 rounded-md bg-red-600 text-white text-xs font-semibold hover:bg-red-700"
            >
              Reintentar
            </button>
          </div>
        )}

        {/* Visión general (4 cards estáticos) */}
        <section className="mb-6">
          <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
            Visión general
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
            <OverviewCard label="Límite diario" value="1000" hint="mensajes/día" />
            <OverviewCard label="Días consecutivos" value="—" hint="histórico" />
            <OverviewCard label="Calidad" value="Alta" hint="estado Meta" />
            <OverviewCard label="Límite mensual" value="10 000" hint="mensajes/mes" />
          </div>
        </section>

        {/* KPI Grid */}
        <section className="mb-8">
          <h2 className="font-heading text-sm uppercase tracking-widest text-gloma-brown-light mb-3">
            Indicadores
          </h2>
          {loading && !kpis ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
              <KpiSkeleton primary />
              <KpiSkeleton />
              <KpiSkeleton />
              <KpiSkeleton />
              <KpiSkeleton />
              <KpiSkeleton />
              <KpiSkeleton />
              <KpiSkeleton />
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
              <KpiCard
                label="Enviado"
                value={kpis?.sent_count ?? 0}
                icon="✉️"
                primary
                hint={`${fmtNumber(kpis?.total_campaigns ?? 0)} campañas`}
              />
              <KpiCard
                label="Entregado"
                value={kpis?.delivered_count ?? 0}
                icon="✓"
                hint={
                  kpis?.delivery_rate_pct !== null &&
                  kpis?.delivery_rate_pct !== undefined
                    ? `${kpis.delivery_rate_pct.toFixed(1)}%`
                    : undefined
                }
              />
              <KpiCard
                label="Leído"
                value={kpis?.read_count ?? 0}
                icon="👁️"
                hint={
                  kpis?.read_rate_pct !== null &&
                  kpis?.read_rate_pct !== undefined
                    ? `${kpis.read_rate_pct.toFixed(1)}%`
                    : undefined
                }
              />
              <KpiCard
                label="Respondió"
                value={0}
                icon="💬"
                hint="próximamente"
              />
              <KpiCard
                label="Enviando"
                value={0}
                icon="📤"
                hint="en cola activa"
              />
              <KpiCard
                label="Fallido"
                value={kpis?.failed_count ?? 0}
                icon="⚠️"
              />
              <KpiCard
                label="Procesando"
                value={0}
                icon="⏳"
                hint="validando plantilla"
              />
              <KpiCard
                label="En cola"
                value={kpis?.queued_count ?? 0}
                icon="🕓"
                hint="agendadas a futuro"
              />
            </div>
          )}
        </section>

        {/* Tabla todas las campañas */}
        <section>
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-3">
            <h2 className="font-heading text-lg font-bold text-gloma-brown-dark">
              Todas las campañas
            </h2>
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nombre…"
                className="text-sm px-3 py-1.5 border border-gloma-brown-light/30 rounded-lg bg-white focus:outline-none focus:border-gloma-brown w-full sm:w-64"
              />
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as SortMode)}
                className="text-sm px-3 py-1.5 border border-gloma-brown-light/30 rounded-lg bg-white focus:outline-none focus:border-gloma-brown"
              >
                <option value="recent">Últimas</option>
                <option value="most_successful">Más exitosas</option>
                <option value="most_read">Más leídas</option>
              </select>
            </div>
          </div>

          <div className="bg-white border border-gloma-brown-light/20 rounded-2xl overflow-hidden shadow-sm">
            {loading && !campaigns ? (
              <div className="p-6 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-10 rounded-lg bg-gloma-brown-light/10 animate-pulse"
                  />
                ))}
              </div>
            ) : pageItems.length === 0 ? (
              <div className="p-10 text-center">
                <div className="w-14 h-14 mx-auto rounded-full bg-gloma-rose-soft flex items-center justify-center text-2xl mb-3">
                  📢
                </div>
                <h3 className="font-heading text-lg font-bold text-gloma-brown-dark mb-1">
                  Aún no tienes campañas
                </h3>
                <p className="text-sm text-gloma-brown-light max-w-sm mx-auto mb-4">
                  Crea la primera para empezar a enviar mensajes masivos por
                  WhatsApp a tus contactos.
                </p>
                <Link href="/campanas/nueva" legacyBehavior>
                  <a className="inline-flex items-center justify-center px-5 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark">
                    + Crear primera campaña
                  </a>
                </Link>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gloma-cream text-gloma-brown-light">
                    <tr>
                      <th className="text-left font-medium px-4 py-2">
                        Campaña
                      </th>
                      <th className="text-right font-medium px-4 py-2">
                        Destinatarios
                      </th>
                      <th className="text-right font-medium px-4 py-2">
                        Exitosa
                      </th>
                      <th className="text-right font-medium px-4 py-2">
                        Leído
                      </th>
                      <th className="text-right font-medium px-4 py-2">
                        Respondió
                      </th>
                      <th className="text-left font-medium px-4 py-2">
                        Estado
                      </th>
                      <th className="text-right font-medium px-4 py-2">
                        Acciones
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gloma-brown-light/10">
                    {pageItems.map((c) => (
                      <tr
                        key={c.id}
                        className="hover:bg-gloma-rose-soft/30 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div className="font-semibold text-gloma-brown-dark">
                            {c.name}
                          </div>
                          <div className="text-xs text-gloma-brown-light">
                            {fmtDate(c.created_at)}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right text-gloma-brown-dark font-mono">
                          {fmtNumber(c.total_recipients)}
                        </td>
                        <td className="px-4 py-3 text-right text-gloma-brown-dark">
                          {fmtNumber(c.delivered)}{' '}
                          <span className="text-gloma-brown-light text-xs">
                            ({fmtPct(c.delivered, c.total_recipients)})
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-gloma-brown-dark">
                          {fmtNumber(c.read)}{' '}
                          <span className="text-gloma-brown-light text-xs">
                            ({fmtPct(c.read, c.total_recipients)})
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-gloma-brown-light">
                          —
                        </td>
                        <td className="px-4 py-3">{statusBadge(c.status)}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-3">
                            <Link
                              href={`/campanas/${c.id}`}
                              legacyBehavior
                            >
                              <a className="text-gloma-brown hover:text-gloma-brown-dark hover:underline text-xs font-semibold">
                                Ver detalle
                              </a>
                            </Link>
                            {c.status === 'scheduled' && (
                              <button
                                type="button"
                                onClick={() => handleCancel(c.id)}
                                disabled={cancelingId === c.id}
                                className="text-red-600 hover:text-red-700 text-xs font-semibold disabled:opacity-50"
                              >
                                {cancelingId === c.id
                                  ? 'Cancelando…'
                                  : 'Cancelar'}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {/* Paginación */}
                <div className="px-4 py-3 border-t border-gloma-brown-light/15 flex items-center justify-between text-xs text-gloma-brown-light">
                  <span>
                    Mostrando {(pageSafe - 1) * PAGE_SIZE + 1}–
                    {Math.min(pageSafe * PAGE_SIZE, filteredSorted.length)} de{' '}
                    {filteredSorted.length} campañas
                  </span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={pageSafe <= 1}
                      className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
                    >
                      ← Anterior
                    </button>
                    <span className="px-3 py-1 rounded-md bg-gloma-brown text-gloma-cream font-semibold">
                      {pageSafe} / {totalPages}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setPage((p) => Math.min(totalPages, p + 1))
                      }
                      disabled={pageSafe >= totalPages}
                      className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
                    >
                      Siguiente →
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </Layout>
  );
}
