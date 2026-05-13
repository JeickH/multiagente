/**
 * Lista de plantillas de WhatsApp (Sprint 13 — tarea #167).
 *
 * Contrato visual: `identidad_gloma/diseno_campanas.html` pantalla 4
 * (sección `#p4` "Plantillas de WhatsApp").
 *
 * Endpoints consumidos:
 *   - GET    /templates                  → cache local del team
 *   - POST   /templates/sync             → refresca cache desde Meta (rate-limit 1/60s/user)
 *   - DELETE /templates/{id}             → soft-delete
 *
 * Reglas de Seguridad aplicadas (frontend):
 *   - regla 6: errores del backend ya vienen sanitizados; se muestran tal cual.
 *   - throttle cliente complementario al rate-limit del backend para "Refrescar".
 */
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import Layout from '../../../components/Layout';
import { ApiError, authedFetch } from '../../../lib/api';
import { fmtDate } from '../../../lib/format';
import type { TemplatePreview } from '../../../types/campaigns';

type SortMode = 'recent' | 'name';

const SYNC_THROTTLE_MS = 60_000; // coincide con backend SYNC_MIN_INTERVAL_SECONDS=60.

interface SyncResult {
  synced?: number;
  created?: number;
  updated?: number;
  deleted_upstream?: number;
  errors?: string[];
  sandbox?: boolean;
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 0) return 'hace un momento';
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'hace un momento';
  if (mins < 60) return `hace ${mins} min`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `hace ${hrs} h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `hace ${days} d`;
  return fmtDate(iso);
}

function statusBadge(status: string) {
  const s = (status || '').toUpperCase();
  const map: Record<string, { label: string; cls: string }> = {
    APPROVED: {
      label: 'APPROVED',
      cls: 'bg-green-50 text-green-800 border border-green-100',
    },
    PENDING: {
      label: 'PENDING',
      cls: 'bg-amber-50 text-amber-800 border border-amber-100',
    },
    REJECTED: {
      label: 'REJECTED',
      cls: 'bg-red-50 text-red-700 border border-red-100',
    },
    DISABLED: {
      label: 'DISABLED',
      cls: 'bg-gray-100 text-gray-600 border border-gray-200',
    },
    PAUSED: {
      label: 'PAUSED',
      cls: 'bg-gray-100 text-gray-600 border border-gray-200',
    },
    DELETED: {
      label: 'DELETED',
      cls: 'bg-gray-100 text-gray-500 line-through border border-gray-200',
    },
  };
  const entry = map[s] ?? {
    label: s || '—',
    cls: 'bg-gray-100 text-gray-600 border border-gray-200',
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide ${entry.cls}`}
    >
      {entry.label}
    </span>
  );
}

export default function PlantillasIndexPage() {
  const [templates, setTemplates] = useState<TemplatePreview[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [search, setSearch] = useState('');
  const [sortMode, setSortMode] = useState<SortMode>('recent');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncCooldownUntil, setSyncCooldownUntil] = useState<number>(0);
  const [now, setNow] = useState<number>(() => Date.now());

  const [deletingId, setDeletingId] = useState<number | null>(null);

  // Auto-sync una vez si la lista llega vacía (sandbox: backend siembra 3 mock).
  const [didAutoSync, setDidAutoSync] = useState(false);

  // Tick para countdown del botón sync.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  // Carga inicial / recarga.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const qs = statusFilter !== 'ALL' ? `?status=${statusFilter}` : '';
    authedFetch<TemplatePreview[]>(`/templates${qs}`)
      .then((rows) => {
        if (cancelled) return;
        setTemplates(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : 'No se pudieron cargar las plantillas.';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick, statusFilter]);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const result = await authedFetch<SyncResult>('/templates/sync', {
        method: 'POST',
      });
      const parts = [
        `Sincronizado: ${result.synced ?? 0}`,
        `creadas: ${result.created ?? 0}`,
        `actualizadas: ${result.updated ?? 0}`,
      ];
      if (result.sandbox) parts.push('(sandbox)');
      setSyncMsg(parts.join(' · '));
      setSyncCooldownUntil(Date.now() + SYNC_THROTTLE_MS);
      setReloadTick((t) => t + 1);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No se pudo sincronizar con Meta.';
      setSyncMsg(msg);
      if (err instanceof ApiError && err.status === 429) {
        // Backend nos rebotó: respetamos su cooldown 60s.
        setSyncCooldownUntil(Date.now() + SYNC_THROTTLE_MS);
      }
    } finally {
      setSyncing(false);
    }
  }, []);

  // Auto-sync inicial si la lista llega vacía y no hay error.
  useEffect(() => {
    if (didAutoSync) return;
    if (loading) return;
    if (error) return;
    if (templates === null) return;
    if (templates.length > 0) {
      setDidAutoSync(true);
      return;
    }
    // Vacío: dispara un sync silencioso una sola vez para poblar sandbox/mock.
    setDidAutoSync(true);
    void handleSync();
  }, [didAutoSync, loading, error, templates, handleSync]);

  const handleDelete = async (t: TemplatePreview) => {
    const ok = window.confirm(
      `¿Eliminar la plantilla "${t.name}"? Esta acción es definitiva en Meta.`,
    );
    if (!ok) return;
    setDeletingId(t.id);
    try {
      await authedFetch(`/templates/${t.id}`, { method: 'DELETE' });
      setReloadTick((tick) => tick + 1);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'No se pudo eliminar la plantilla.';
      window.alert(msg);
    } finally {
      setDeletingId(null);
    }
  };

  const filteredSorted = useMemo<TemplatePreview[]>(() => {
    if (!templates) return [];
    let list = templates.slice();
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter((t) => t.name.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      if (sortMode === 'name') return a.name.localeCompare(b.name);
      // recent: created_at desc; fallback last_synced_at.
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      return tb - ta;
    });
    return list;
  }, [templates, search, sortMode]);

  // Última sincronización: tomamos el `last_synced_at` más reciente.
  const lastSyncedAt = useMemo<string | null>(() => {
    if (!templates || templates.length === 0) return null;
    let max = 0;
    let raw: string | null = null;
    for (const t of templates) {
      if (!t.last_synced_at) continue;
      const ms = new Date(t.last_synced_at).getTime();
      if (Number.isNaN(ms)) continue;
      if (ms > max) {
        max = ms;
        raw = t.last_synced_at;
      }
    }
    return raw;
  }, [templates]);

  const cooldownSecsLeft = Math.max(
    0,
    Math.ceil((syncCooldownUntil - now) / 1000),
  );
  const syncDisabled = syncing || cooldownSecsLeft > 0;

  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        {/* Header + breadcrumb */}
        <div className="mb-6">
          <p className="text-[11px] text-gloma-brown-light mb-1">
            <Link href="/campanas" legacyBehavior>
              <a className="hover:text-gloma-brown hover:underline">
                Transmisiones masivas
              </a>
            </Link>
            <span className="mx-1">/</span>
            <span>Plantillas</span>
          </p>
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <h1 className="font-heading text-2xl md:text-3xl font-extrabold text-gloma-brown-dark">
                Tus plantillas
              </h1>
              <p className="text-sm text-gloma-brown-light mt-1 max-w-2xl">
                Selecciona o crea tu plantilla y envíala para la aprobación de
                WhatsApp. Todas las plantillas deben cumplir con las{' '}
                <a
                  href="https://developers.facebook.com/docs/whatsapp/message-templates/guidelines"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-gloma-brown underline hover:text-gloma-brown-dark"
                >
                  pautas de WhatsApp
                </a>
                .
              </p>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={handleSync}
                disabled={syncDisabled}
                className="px-3 py-2 text-xs rounded-lg border border-gloma-brown-light/30 bg-white hover:bg-gloma-rose-soft disabled:opacity-50 disabled:cursor-not-allowed font-semibold text-gloma-brown-dark"
                title={
                  cooldownSecsLeft > 0
                    ? `Espera ${cooldownSecsLeft}s antes de refrescar de nuevo`
                    : 'Sincronizar con Meta'
                }
              >
                {syncing
                  ? 'Sincronizando…'
                  : cooldownSecsLeft > 0
                    ? `↻ Refrescar (${cooldownSecsLeft}s)`
                    : '↻ Refrescar desde Meta'}
              </button>
              <Link href="/campanas/plantillas/nueva" legacyBehavior>
                <a className="px-4 py-2 text-xs rounded-lg bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark">
                  + Nuevo Mensaje de Plantilla
                </a>
              </Link>
            </div>
          </div>
        </div>

        {/* Aviso de sync + mensaje resultado */}
        <div className="mb-4 flex items-start gap-2 text-xs bg-white border border-gloma-brown-light/20 rounded-lg px-3 py-2 text-gloma-brown-light">
          <span aria-hidden>🔄</span>
          <div className="flex-1">
            <p>
              Última sincronización:{' '}
              <strong className="text-gloma-brown-dark">
                {relativeTime(lastSyncedAt)}
              </strong>
              . Las plantillas PENDING se reconsultan automáticamente cada 30
              min.
            </p>
            {syncMsg && (
              <p className="mt-1 text-gloma-brown-dark">{syncMsg}</p>
            )}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm flex items-center justify-between">
            <span>
              No se pudieron cargar las plantillas.{' '}
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

        {/* Toolbar (buscador + filtros + sort) */}
        <div className="flex flex-col md:flex-row md:items-center gap-2 mb-3">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar plantilla por nombre…"
            className="text-sm px-3 py-1.5 border border-gloma-brown-light/30 rounded-lg bg-white focus:outline-none focus:border-gloma-brown w-full md:w-72"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-sm px-3 py-1.5 border border-gloma-brown-light/30 rounded-lg bg-white focus:outline-none focus:border-gloma-brown"
          >
            <option value="ALL">Todos los estados</option>
            <option value="APPROVED">APPROVED</option>
            <option value="PENDING">PENDING</option>
            <option value="REJECTED">REJECTED</option>
            <option value="DISABLED">DISABLED</option>
            <option value="PAUSED">PAUSED</option>
          </select>
          <select
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value as SortMode)}
            className="text-sm px-3 py-1.5 border border-gloma-brown-light/30 rounded-lg bg-white focus:outline-none focus:border-gloma-brown"
          >
            <option value="recent">Ordenar: Último</option>
            <option value="name">Ordenar: Nombre</option>
          </select>
        </div>

        {/* Tabla */}
        <div className="bg-white border border-gloma-brown-light/20 rounded-2xl overflow-hidden shadow-sm">
          {loading && !templates ? (
            <div className="p-6 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-10 rounded-lg bg-gloma-brown-light/10 animate-pulse"
                />
              ))}
            </div>
          ) : filteredSorted.length === 0 ? (
            <div className="p-10 text-center">
              <div className="w-14 h-14 mx-auto rounded-full bg-gloma-rose-soft flex items-center justify-center text-2xl mb-3">
                ✉️
              </div>
              <h3 className="font-heading text-lg font-bold text-gloma-brown-dark mb-1">
                {search || statusFilter !== 'ALL'
                  ? 'Sin resultados'
                  : 'No tienes plantillas'}
              </h3>
              <p className="text-sm text-gloma-brown-light max-w-sm mx-auto mb-4">
                {search || statusFilter !== 'ALL'
                  ? 'Ajusta los filtros o limpia la búsqueda.'
                  : 'Crea la primera y envíala a aprobación.'}
              </p>
              {!(search || statusFilter !== 'ALL') && (
                <Link href="/campanas/plantillas/nueva" legacyBehavior>
                  <a className="inline-flex items-center justify-center px-5 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark">
                    + Crear plantilla
                  </a>
                </Link>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gloma-cream text-gloma-brown-light">
                  <tr>
                    <th className="text-left font-medium px-4 py-2">Nombre</th>
                    <th className="text-left font-medium px-4 py-2">
                      Categoría
                    </th>
                    <th className="text-left font-medium px-4 py-2">Estado</th>
                    <th className="text-left font-medium px-4 py-2">Idioma</th>
                    <th className="text-left font-medium px-4 py-2">
                      Última actualización
                    </th>
                    <th className="text-right font-medium px-4 py-2">
                      Acciones
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gloma-brown-light/10">
                  {filteredSorted.map((t) => {
                    const isDeleted =
                      (t.status || '').toUpperCase() === 'DELETED';
                    const isApproved =
                      (t.status || '').toUpperCase() === 'APPROVED';
                    return (
                      <tr
                        key={t.id}
                        className="hover:bg-gloma-rose-soft/30 transition-colors"
                      >
                        <td className="px-4 py-3">
                          <div
                            className={`font-semibold ${
                              isDeleted
                                ? 'line-through text-gray-400'
                                : 'text-gloma-brown-dark'
                            }`}
                          >
                            {t.name}
                          </div>
                          {t.rejection_reason && (
                            <div className="text-[11px] text-red-700 mt-0.5">
                              {t.rejection_reason}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-gloma-brown-light">
                          {t.category || '—'}
                        </td>
                        <td className="px-4 py-3">{statusBadge(t.status)}</td>
                        <td className="px-4 py-3 text-gloma-brown-light font-mono text-xs">
                          {t.language}
                        </td>
                        <td className="px-4 py-3 text-gloma-brown-light text-xs">
                          {relativeTime(t.last_synced_at ?? t.created_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex justify-end gap-3 text-xs">
                            <span
                              className="text-gloma-brown-light cursor-not-allowed"
                              title="Próximamente"
                            >
                              Editar
                            </span>
                            {isApproved && (
                              <Link
                                href={`/campanas/nueva?template_id=${t.id}`}
                                legacyBehavior
                              >
                                <a className="text-gloma-brown hover:text-gloma-brown-dark hover:underline font-semibold">
                                  Enviar campaña
                                </a>
                              </Link>
                            )}
                            {!isDeleted && (
                              <button
                                type="button"
                                onClick={() => handleDelete(t)}
                                disabled={deletingId === t.id}
                                className="text-red-600 hover:text-red-700 font-semibold disabled:opacity-50"
                              >
                                {deletingId === t.id
                                  ? 'Eliminando…'
                                  : 'Eliminar'}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
