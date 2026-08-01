import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout';
import { authedFetch, ApiError } from '../lib/api';

/**
 * Citas — panel privado de la cuenta oficial de Gloma (Sprint 21 #283/#284).
 *
 * Muestra y edita `demo_bookings`: las demos que agenda el bot institucional
 * desde la landing, el simulador o WhatsApp. El backend (`/citas`) solo
 * responde a la cuenta de Gloma y a los miembros de su team; cualquier otra
 * sesión recibe 403 y aquí se ve el estado "sin acceso".
 */

type Cita = {
  id: number;
  created_at: string;
  source: string;
  nombre: string | null;
  empresa: string | null;
  correo: string;
  telefono: string | null;
  dia: string | null;
  hora: string | null;
  notas: string | null;
  estado: string;
};

type CitasResponse = {
  citas: Cita[];
  resumen: { total: number; solicitadas: number; confirmadas: number; realizadas: number };
  estados: string[];
  dias: string[];
};

const HORAS = ['2:00 p.m.', '3:00 p.m.', '4:00 p.m.', '5:00 p.m.', '6:00 p.m.'];

const ESTADO_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  solicitada: { bg: '#FEF3C7', color: '#92400E', label: 'Solicitada' },
  confirmada: { bg: '#E0F2F1', color: '#004D40', label: 'Confirmada' },
  realizada: { bg: '#DBEAFE', color: '#1E40AF', label: 'Realizada' },
  cancelada: { bg: '#F3F4F6', color: '#4B5563', label: 'Cancelada' },
  no_asistio: { bg: '#FEE2E2', color: '#991B1B', label: 'No asistió' },
};

const SOURCE_LABEL: Record<string, string> = {
  landing: '🌐 Landing',
  simulador: '🧪 Simulador',
  whatsapp: '💬 WhatsApp',
  manual: '✍️ Manual',
};

/** Fila vacía para el alta manual (#289). */
const CITA_NUEVA: Cita = {
  id: 0,
  created_at: '',
  source: 'manual',
  nombre: '',
  empresa: '',
  correo: '',
  telefono: '',
  dia: '',
  hora: '',
  notas: '',
  estado: 'solicitada',
};

function fechaCorta(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('es-CO', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function EstadoBadge({ estado }: { estado: string }) {
  const s = ESTADO_STYLE[estado] || { bg: '#F3F4F6', color: '#4B5563', label: estado };
  return (
    <span
      className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap"
      style={{ backgroundColor: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

export default function CitasPage() {
  const [data, setData] = useState<CitasResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<string>('');

  const [editing, setEditing] = useState<Cita | null>(null);
  const [form, setForm] = useState<Partial<Cita>>({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = filtro ? `?estado=${encodeURIComponent(filtro)}` : '';
      const res = await authedFetch<CitasResponse>(`/citas${qs}`);
      setData(res);
      setDenied(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setDenied(true);
      else setError(err instanceof Error ? err.message : 'Error al cargar las citas');
    } finally {
      setLoading(false);
    }
  }, [filtro]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const abrirEdicion = (c: Cita) => {
    setEditing(c);
    setForm({
      nombre: c.nombre ?? '',
      empresa: c.empresa ?? '',
      correo: c.correo,
      telefono: c.telefono ?? '',
      dia: c.dia ?? '',
      hora: c.hora ?? '',
      notas: c.notas ?? '',
      estado: c.estado,
    });
    setFormError(null);
  };

  /** Alta manual: la misma ventana de edición, pero sin id (#289). */
  const abrirNueva = () => abrirEdicion(CITA_NUEVA);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    setSaving(true);
    setFormError(null);
    try {
      const body: Record<string, unknown> = {};
      (['nombre', 'empresa', 'correo', 'telefono', 'dia', 'hora', 'notas', 'estado'] as const)
        .forEach((k) => {
          const v = (form[k] ?? '') as string;
          body[k] = v === '' ? null : v;
        });
      // El correo no puede quedar vacío (es la llave de contacto).
      if (!body.correo) {
        setFormError('El correo es obligatorio.');
        setSaving(false);
        return;
      }
      const esNueva = editing.id === 0;
      await authedFetch<Cita>(esNueva ? '/citas' : `/citas/${editing.id}`, {
        method: esNueva ? 'POST' : 'PATCH',
        body: JSON.stringify(body),
      });
      setEditing(null);
      await cargar();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'No se pudo guardar');
    } finally {
      setSaving(false);
    }
  };

  const cambiarEstado = async (c: Cita, estado: string) => {
    try {
      await authedFetch<Cita>(`/citas/${c.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ estado }),
      });
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo cambiar el estado');
    }
  };

  const eliminar = async (c: Cita) => {
    if (!window.confirm(`¿Eliminar la cita de ${c.correo}? Esta acción no se puede deshacer.`)) {
      return;
    }
    try {
      await authedFetch(`/citas/${c.id}`, { method: 'DELETE' });
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo eliminar');
    }
  };

  const estados = data?.estados ?? Object.keys(ESTADO_STYLE);
  const dias = data?.dias ?? ['lunes', 'martes', 'miércoles', 'jueves', 'viernes'];
  const citas = useMemo(() => data?.citas ?? [], [data]);

  return (
    <Layout variant="fullscreen">
      <div className="flex-1 overflow-auto p-8 font-body">
        <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-heading font-bold text-gloma-brown">Citas</h1>
            <p className="text-sm text-gloma-brown-light mt-1">
              Demos que agendó el agente de Gloma desde la landing, el simulador o
              WhatsApp — y las que agregues a mano.
            </p>
          </div>
          {!denied && (
            <button
              type="button"
              onClick={abrirNueva}
              className="px-4 py-2 rounded-full text-sm font-semibold bg-gloma-brown text-white hover:opacity-90 whitespace-nowrap"
            >
              + Nueva cita
            </button>
          )}
        </header>

        {denied && (
          <div className="bg-white border border-gloma-rose rounded-xl p-8 text-center">
            <p className="text-4xl mb-3">🔒</p>
            <h2 className="font-heading text-xl text-gloma-brown mb-2">Módulo privado</h2>
            <p className="text-sm text-gloma-brown-light">
              Las citas del agente institucional solo son visibles para la cuenta de Gloma.
            </p>
          </div>
        )}

        {!denied && (
          <>
            {/* Resumen */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6" data-tour="citas-resumen">
              {[
                { label: 'Total', value: data?.resumen.total ?? 0 },
                { label: 'Solicitadas', value: data?.resumen.solicitadas ?? 0 },
                { label: 'Confirmadas', value: data?.resumen.confirmadas ?? 0 },
                { label: 'Realizadas', value: data?.resumen.realizadas ?? 0 },
              ].map((k) => (
                <div
                  key={k.label}
                  className="bg-white rounded-xl border border-gloma-rose px-5 py-4"
                >
                  <div className="text-2xl font-heading font-bold text-gloma-brown">
                    {k.value}
                  </div>
                  <div className="text-xs text-gloma-brown-light">{k.label}</div>
                </div>
              ))}
            </div>

            {/* Filtros */}
            <div className="flex items-center gap-2 mb-4 flex-wrap">
              <button
                type="button"
                onClick={() => setFiltro('')}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  filtro === ''
                    ? 'bg-gloma-brown text-white border-gloma-brown'
                    : 'bg-white text-gloma-brown border-gloma-rose hover:bg-gloma-rose-soft'
                }`}
              >
                Todas
              </button>
              {estados.map((e) => (
                <button
                  key={e}
                  type="button"
                  onClick={() => setFiltro(e)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    filtro === e
                      ? 'bg-gloma-brown text-white border-gloma-brown'
                      : 'bg-white text-gloma-brown border-gloma-rose hover:bg-gloma-rose-soft'
                  }`}
                >
                  {ESTADO_STYLE[e]?.label || e}
                </button>
              ))}
              <button
                type="button"
                onClick={() => void cargar()}
                className="ml-auto px-3 py-1.5 rounded-full text-xs font-medium bg-white border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft"
              >
                ↻ Actualizar
              </button>
            </div>

            {error && (
              <p className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
                {error}
              </p>
            )}

            {/* Tabla */}
            <div className="bg-white rounded-xl border border-gloma-rose overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-tour="citas-tabla">
                  <thead>
                    <tr className="bg-gloma-rose-soft text-gloma-brown text-left">
                      <th className="px-4 py-3 font-semibold whitespace-nowrap">Agendada</th>
                      <th className="px-4 py-3 font-semibold">Prospecto</th>
                      <th className="px-4 py-3 font-semibold">Contacto</th>
                      <th className="px-4 py-3 font-semibold whitespace-nowrap">Franja</th>
                      <th className="px-4 py-3 font-semibold whitespace-nowrap">Canal</th>
                      <th className="px-4 py-3 font-semibold">Estado</th>
                      <th className="px-4 py-3 font-semibold text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={7} className="px-4 py-10 text-center text-gloma-brown-light">
                          Cargando…
                        </td>
                      </tr>
                    )}
                    {!loading && citas.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-4 py-12 text-center text-gloma-brown-light">
                          <p className="text-3xl mb-2">📅</p>
                          Todavía no hay demos agendadas
                          {filtro ? ' con este estado.' : '.'}
                          {!filtro && (
                            <button
                              type="button"
                              onClick={abrirNueva}
                              className="block mx-auto mt-3 px-4 py-2 rounded-full text-xs font-semibold bg-gloma-brown text-white hover:opacity-90"
                            >
                              + Agregar una a mano
                            </button>
                          )}
                        </td>
                      </tr>
                    )}
                    {!loading &&
                      citas.map((c) => (
                        <tr
                          key={c.id}
                          className="border-t border-gloma-rose-soft hover:bg-gloma-cream/60"
                        >
                          <td className="px-4 py-3 whitespace-nowrap text-gloma-brown-light">
                            {fechaCorta(c.created_at)}
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-medium text-gloma-brown">
                              {c.nombre || '—'}
                            </div>
                            <div className="text-xs text-gloma-brown-light">
                              {c.empresa || ''}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <a
                              href={`mailto:${c.correo}`}
                              className="text-gloma-brown underline decoration-gloma-rose"
                            >
                              {c.correo}
                            </a>
                            {c.telefono && (
                              <div className="text-xs text-gloma-brown-light">{c.telefono}</div>
                            )}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-gloma-brown">
                            {c.dia ? (
                              <>
                                <span className="capitalize">{c.dia}</span>
                                {c.hora ? ` · ${c.hora}` : ''}
                              </>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap text-xs text-gloma-brown-light">
                            {SOURCE_LABEL[c.source] || c.source}
                          </td>
                          <td className="px-4 py-3">
                            <select
                              value={c.estado}
                              onChange={(e) => void cambiarEstado(c, e.target.value)}
                              aria-label={`Estado de la cita de ${c.correo}`}
                              className="text-xs border border-gloma-rose rounded-full px-2 py-1 bg-white text-gloma-brown focus:outline-none"
                            >
                              {estados.map((e) => (
                                <option key={e} value={e}>
                                  {ESTADO_STYLE[e]?.label || e}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="px-4 py-3 text-right whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => abrirEdicion(c)}
                              className="px-3 py-1.5 rounded-full text-xs font-medium bg-gloma-brown text-white hover:opacity-90"
                            >
                              Editar
                            </button>
                            <button
                              type="button"
                              onClick={() => void eliminar(c)}
                              className="ml-2 px-3 py-1.5 rounded-full text-xs font-medium border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft"
                            >
                              Eliminar
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>

            {citas.some((c) => c.notas) && (
              <p className="text-xs text-gloma-brown-light mt-3">
                Tip: las notas que tomó el agente (industria, caso de uso) se ven al editar
                cada cita.
              </p>
            )}
          </>
        )}
      </div>

      {/* Modal de edición */}
      {editing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
        >
          <form
            onSubmit={guardar}
            className="bg-white rounded-2xl w-full max-w-lg p-6 font-body max-h-[90vh] overflow-y-auto"
          >
            <h2 className="font-heading text-xl font-bold text-gloma-brown mb-1">
              {editing.id === 0 ? 'Nueva cita' : `Editar cita #${editing.id}`}
            </h2>
            <p className="text-xs text-gloma-brown-light mb-5">
              {editing.id === 0
                ? 'Registro manual: para las demos que se agendaron por fuera del agente (llamada, correo, evento). El correo es obligatorio.'
                : `Agendada el ${fechaCorta(editing.created_at)} · ${
                    SOURCE_LABEL[editing.source] || editing.source
                  }`}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {([
                ['nombre', 'Nombre'],
                ['empresa', 'Empresa'],
                ['correo', 'Correo'],
                ['telefono', 'Teléfono'],
              ] as const).map(([campo, label]) => (
                <label key={campo} className="block text-sm">
                  <span className="text-gloma-brown font-medium">{label}</span>
                  <input
                    type={campo === 'correo' ? 'email' : 'text'}
                    value={(form[campo] as string) ?? ''}
                    onChange={(e) => setForm({ ...form, [campo]: e.target.value })}
                    className="mt-1 w-full border border-gloma-rose rounded-lg px-3 py-2 text-sm text-gloma-brown focus:outline-none"
                  />
                </label>
              ))}

              <label className="block text-sm">
                <span className="text-gloma-brown font-medium">Día</span>
                <select
                  value={(form.dia as string) ?? ''}
                  onChange={(e) => setForm({ ...form, dia: e.target.value })}
                  className="mt-1 w-full border border-gloma-rose rounded-lg px-3 py-2 text-sm text-gloma-brown bg-white focus:outline-none"
                >
                  <option value="">—</option>
                  {dias.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block text-sm">
                <span className="text-gloma-brown font-medium">Hora</span>
                <select
                  value={(form.hora as string) ?? ''}
                  onChange={(e) => setForm({ ...form, hora: e.target.value })}
                  className="mt-1 w-full border border-gloma-rose rounded-lg px-3 py-2 text-sm text-gloma-brown bg-white focus:outline-none"
                >
                  <option value="">—</option>
                  {HORAS.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block text-sm sm:col-span-2">
                <span className="text-gloma-brown font-medium">Estado</span>
                <select
                  value={(form.estado as string) ?? 'solicitada'}
                  onChange={(e) => setForm({ ...form, estado: e.target.value })}
                  className="mt-1 w-full border border-gloma-rose rounded-lg px-3 py-2 text-sm text-gloma-brown bg-white focus:outline-none"
                >
                  {estados.map((e) => (
                    <option key={e} value={e}>
                      {ESTADO_STYLE[e]?.label || e}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block text-sm sm:col-span-2">
                <span className="text-gloma-brown font-medium">Notas</span>
                <textarea
                  value={(form.notas as string) ?? ''}
                  onChange={(e) => setForm({ ...form, notas: e.target.value })}
                  rows={3}
                  maxLength={500}
                  className="mt-1 w-full border border-gloma-rose rounded-lg px-3 py-2 text-sm text-gloma-brown focus:outline-none"
                />
              </label>
            </div>

            {formError && (
              <p className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {formError}
              </p>
            )}

            <div className="flex justify-end gap-2 mt-6">
              <button
                type="button"
                disabled={saving}
                onClick={() => setEditing(null)}
                className="px-4 py-2 rounded-full text-sm border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft disabled:opacity-60"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 rounded-full text-sm font-semibold bg-gloma-brown text-white hover:opacity-90 disabled:opacity-60"
              >
                {saving
                  ? 'Guardando…'
                  : editing.id === 0
                  ? 'Crear cita'
                  : 'Guardar cambios'}
              </button>
            </div>
          </form>
        </div>
      )}
    </Layout>
  );
}
