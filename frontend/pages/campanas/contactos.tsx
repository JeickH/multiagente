/**
 * Contactos y Grupos (Sprint 13 — tarea #168).
 *
 * Contrato visual: `identidad_gloma/diseno_campanas.html` pantalla 6.
 *
 * Endpoints consumidos (backend Sprint 13 #159):
 *   - GET    /contacts?q=&group_id=&opt_in_only=&limit=&offset=
 *   - POST   /contacts
 *   - PATCH  /contacts/{id}
 *   - DELETE /contacts/{id}
 *   - POST   /contacts/import-csv (multipart)
 *   - GET    /contact-groups
 *   - POST   /contact-groups
 *   - GET    /contact-groups/{id}
 *   - PATCH  /contact-groups/{id}
 *   - DELETE /contact-groups/{id}
 *   - POST   /contact-groups/{id}/members
 *   - DELETE /contact-groups/{id}/members/{contact_id}
 *
 * SEGURIDAD:
 *   - Todo `phone_e164` se renderiza con `maskPhone()` (regla 1).
 *   - Errores al usuario son sanitizados (regla 6) — el detalle ya viene del
 *     backend; `authedFetch` lanza `ApiError` con `.message` genérico.
 *   - Los `errors` del CSV importer NO contienen teléfono crudo (regla 1 /
 *     S13-009 backend). Si llegara crudo, es bug del backend y debe reportarse.
 */
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import Layout from '../../components/Layout';
import { ApiError, authedFetch } from '../../lib/api';
import { fmtDate, maskPhone } from '../../lib/format';
import type {
  Contact,
  ContactCreatePayload,
  ContactGroup,
  ContactGroupCreatePayload,
  ContactGroupDetail,
  ContactGroupUpdatePayload,
  ContactImportResult,
  ContactUpdatePayload,
} from '../../types/contacts';

type Tab = 'contactos' | 'grupos';
type OptInFilter = 'all' | 'only_opt_in';

const PAGE_SIZE = 50;

// ─── Utilities ──────────────────────────────────────────────────────────

function classNames(...xs: (string | false | null | undefined)[]): string {
  return xs.filter(Boolean).join(' ');
}

/**
 * Wrapper alrededor de fetch para multipart (CSV). Reutiliza el JWT en
 * localStorage. NO usa `authedFetch` porque ese helper inyecta
 * `Content-Type: application/json` cuando hay body, lo que rompe el boundary
 * que el browser genera para FormData.
 */
async function uploadCsv(file: File): Promise<ContactImportResult> {
  const token =
    typeof window === 'undefined' ? null : localStorage.getItem('token');
  if (!token) {
    if (typeof window !== 'undefined') window.location.assign('/login');
    throw new ApiError('No autenticado', 401);
  }
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/contacts/import-csv', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: fd,
  });
  if (res.status === 401) {
    try {
      localStorage.removeItem('token');
    } catch {
      /* no-op */
    }
    window.location.assign('/login');
    throw new ApiError('Sesión expirada', 401);
  }
  if (!res.ok) {
    let detail = 'No se pudo importar el archivo.';
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      /* no-op */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as ContactImportResult;
}

// ─── Sub-components ─────────────────────────────────────────────────────

function ModalShell({
  title,
  onClose,
  children,
  size = 'md',
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}) {
  const widthCls =
    size === 'sm'
      ? 'max-w-sm'
      : size === 'lg'
      ? 'max-w-2xl'
      : size === 'xl'
      ? 'max-w-3xl'
      : 'max-w-md';
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}
    >
      <div
        className={classNames(
          'w-full bg-gloma-cream border border-gloma-brown-light/20 rounded-2xl shadow-xl flex flex-col max-h-[90vh]',
          widthCls,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gloma-brown-light/15">
          <h3 className="font-heading text-lg font-bold text-gloma-brown-dark">
            {title}
          </h3>
          <button
            type="button"
            aria-label="Cerrar"
            onClick={onClose}
            className="text-gloma-brown-light hover:text-gloma-brown-dark text-lg leading-none"
          >
            ×
          </button>
        </div>
        <div className="overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}

function OptInBadge({ optIn }: { optIn: boolean }) {
  if (optIn) {
    return (
      <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gloma-rose-soft/40 text-gloma-brown-dark">
        ✓ opt-in
      </span>
    );
  }
  return (
    <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gray-100 text-gray-500">
      ✕ opt-out
    </span>
  );
}

function GroupChips({
  groups,
  max = 3,
}: {
  groups: ContactGroup[];
  max?: number;
}) {
  if (!groups.length)
    return <span className="text-gloma-brown-light text-xs">—</span>;
  const visible = groups.slice(0, max);
  const rest = groups.length - visible.length;
  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((g) => (
        <span
          key={g.id}
          className="text-[10px] px-1.5 py-0.5 rounded bg-gloma-cream border border-gloma-brown-light/30 text-gloma-brown"
        >
          {g.name}
        </span>
      ))}
      {rest > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gloma-brown-light/15 text-gloma-brown-light">
          +{rest} más
        </span>
      )}
    </div>
  );
}

// ─── Modal: Crear/Editar contacto ───────────────────────────────────────

function ContactFormModal({
  initial,
  onClose,
  onSaved,
}: {
  initial: Contact | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!initial;
  const [phone, setPhone] = useState(initial?.phone_e164 ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [email, setEmail] = useState(initial?.email ?? '');
  const [optIn, setOptIn] = useState<boolean>(initial?.opt_in ?? true);
  const [attrsText, setAttrsText] = useState(
    initial?.attributes && Object.keys(initial.attributes).length
      ? JSON.stringify(initial.attributes, null, 2)
      : '',
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    let attrs: Record<string, unknown> | null = null;
    const trimmed = attrsText.trim();
    if (trimmed) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          attrs = parsed as Record<string, unknown>;
        } else {
          throw new Error('object expected');
        }
      } catch {
        setErr('Atributos: debe ser un objeto JSON válido.');
        setSaving(false);
        return;
      }
    }
    try {
      if (isEdit && initial) {
        const payload: ContactUpdatePayload = {
          name: name.trim() || null,
          email: email.trim() || null,
          attributes: attrs ?? undefined,
          opt_in: optIn,
        };
        await authedFetch(`/contacts/${initial.id}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
      } else {
        const payload: ContactCreatePayload = {
          phone_e164: phone.trim(),
          name: name.trim() || null,
          email: email.trim() || null,
          attributes: attrs ?? undefined,
          opt_in: optIn,
        };
        await authedFetch('/contacts', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (e2) {
      setErr(
        e2 instanceof ApiError ? e2.message : 'No se pudo guardar el contacto.',
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell
      title={isEdit ? 'Editar contacto' : 'Nuevo contacto'}
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-3 text-sm">
        <div>
          <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
            Teléfono (E.164) {isEdit && '· no editable'}
          </label>
          <input
            type="text"
            required
            disabled={isEdit}
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+5215512345678"
            className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white disabled:bg-gloma-brown-light/10 disabled:text-gloma-brown-light focus:outline-none focus:border-gloma-brown"
          />
          {!isEdit && (
            <p className="text-[11px] text-gloma-brown-light mt-1">
              Formato internacional con &quot;+&quot; y código de país.
            </p>
          )}
        </div>
        <div>
          <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
            Nombre
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="María Pérez"
            className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
            Email
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="maria@ejemplo.com"
            className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
          />
        </div>
        <div>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={optIn}
              onChange={(e) => setOptIn(e.target.checked)}
              className="rounded border-gloma-brown-light/40 text-gloma-brown focus:ring-gloma-brown"
            />
            <span className="text-xs font-semibold text-gloma-brown-dark">
              Acepta recibir mensajes (opt-in)
            </span>
          </label>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
            Atributos (JSON opcional)
          </label>
          <textarea
            rows={3}
            value={attrsText}
            onChange={(e) => setAttrsText(e.target.value)}
            placeholder='{"ciudad":"Cali","tier":"VIP"}'
            className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white font-mono text-xs focus:outline-none focus:border-gloma-brown"
          />
        </div>
        {err && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {err}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white text-gloma-brown-dark"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark disabled:opacity-50"
          >
            {saving ? 'Guardando…' : isEdit ? 'Guardar' : 'Crear contacto'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ─── Modal: Asignar contacto a un grupo ─────────────────────────────────

function AssignToGroupModal({
  contact,
  groups,
  onClose,
  onAssigned,
}: {
  contact: Contact;
  groups: ContactGroup[];
  onClose: () => void;
  onAssigned: () => void;
}) {
  const [groupId, setGroupId] = useState<number | null>(
    groups.length ? groups[0].id : null,
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!groupId) return;
    setBusy(true);
    setErr(null);
    try {
      await authedFetch(`/contact-groups/${groupId}/members`, {
        method: 'POST',
        body: JSON.stringify({ contact_ids: [contact.id] }),
      });
      onAssigned();
      onClose();
    } catch (e2) {
      setErr(
        e2 instanceof ApiError ? e2.message : 'No se pudo asignar al grupo.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell title="Asignar a grupo" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3 text-sm">
        <p className="text-xs text-gloma-brown-light">
          Añadirás <strong>{contact.name || maskPhone(contact.phone_e164)}</strong> al
          grupo seleccionado.
        </p>
        {groups.length === 0 ? (
          <div className="text-xs text-gloma-brown-light bg-gloma-brown-light/10 rounded-md p-3">
            Aún no tienes grupos. Crea uno desde la pestaña Grupos.
          </div>
        ) : (
          <div>
            <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
              Grupo
            </label>
            <select
              value={groupId ?? ''}
              onChange={(e) => setGroupId(Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
            >
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} · {g.member_count} miembros
                </option>
              ))}
            </select>
          </div>
        )}
        {err && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {err}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white text-gloma-brown-dark"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={busy || !groupId}
            className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark disabled:opacity-50"
          >
            {busy ? 'Asignando…' : 'Asignar'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ─── Modal: Importar CSV ────────────────────────────────────────────────

function ImportCsvModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ContactImportResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErr('Selecciona un archivo .csv');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await uploadCsv(file);
      setResult(r);
    } catch (e2) {
      setErr(
        e2 instanceof ApiError
          ? e2.message
          : 'No se pudo importar el archivo.',
      );
    } finally {
      setBusy(false);
    }
  };

  const closeAndRefresh = () => {
    if (result) onImported();
    onClose();
  };

  return (
    <ModalShell title="Importar contactos desde CSV" onClose={closeAndRefresh} size="lg">
      {result ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-lg border border-gloma-brown-light/20 bg-white p-4">
            <p className="font-heading font-bold text-gloma-brown-dark mb-3">
              Importación completada
            </p>
            <div className="grid grid-cols-4 gap-3">
              <div className="rounded-md bg-gloma-cream p-3 text-center">
                <p className="text-[10px] uppercase tracking-widest text-gloma-brown-light">
                  Total
                </p>
                <p className="font-heading text-xl font-bold text-gloma-brown-dark">
                  {result.total}
                </p>
              </div>
              <div className="rounded-md bg-green-50 border border-green-200 p-3 text-center">
                <p className="text-[10px] uppercase tracking-widest text-green-700">
                  Creados
                </p>
                <p className="font-heading text-xl font-bold text-green-700">
                  {result.created}
                </p>
              </div>
              <div className="rounded-md bg-blue-50 border border-blue-200 p-3 text-center">
                <p className="text-[10px] uppercase tracking-widest text-blue-700">
                  Actualizados
                </p>
                <p className="font-heading text-xl font-bold text-blue-700">
                  {result.updated}
                </p>
              </div>
              <div className="rounded-md bg-gray-50 border border-gray-200 p-3 text-center">
                <p className="text-[10px] uppercase tracking-widest text-gray-500">
                  Omitidos
                </p>
                <p className="font-heading text-xl font-bold text-gray-500">
                  {result.skipped}
                </p>
              </div>
            </div>
          </div>
          {result.errors && result.errors.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="text-xs font-semibold text-red-700 mb-2">
                {result.errors.length} fila(s) con errores:
              </p>
              <ul className="max-h-48 overflow-y-auto text-xs text-red-700 space-y-1 list-disc list-inside">
                {result.errors.map((m, i) => (
                  <li key={i}>{m}</li>
                ))}
              </ul>
              <p className="text-[10px] text-red-700/70 mt-2">
                Si ves un teléfono crudo en algún mensaje, reporta — el backend
                debería redactarlo.
              </p>
            </div>
          )}
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={closeAndRefresh}
              className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark"
            >
              Cerrar y refrescar
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3 text-sm">
          <p className="text-xs text-gloma-brown-light">
            Formato esperado: encabezado opcional{' '}
            <code className="bg-gloma-cream px-1 rounded">
              phone_e164,name,email,opt_in
            </code>
            . Tamaño máximo 2 MB.
          </p>
          <div className="rounded-lg border-2 border-dashed border-gloma-brown-light/30 bg-white p-6 text-center">
            <input
              id="csv-file"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block mx-auto text-xs"
            />
            {file && (
              <p className="text-[11px] text-gloma-brown-light mt-2">
                Seleccionado: <strong>{file.name}</strong> ·{' '}
                {Math.ceil(file.size / 1024)} KB
              </p>
            )}
          </div>
          {err && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {err}
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white text-gloma-brown-dark"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={busy || !file}
              className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark disabled:opacity-50"
            >
              {busy ? 'Importando…' : 'Importar'}
            </button>
          </div>
        </form>
      )}
    </ModalShell>
  );
}

// ─── Modal: Crear/Editar grupo ──────────────────────────────────────────

function GroupFormModal({
  initial,
  onClose,
  onSaved,
}: {
  initial: ContactGroup | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setErr('El nombre es obligatorio.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      if (isEdit && initial) {
        const payload: ContactGroupUpdatePayload = {
          name: name.trim(),
          description: description.trim() || null,
        };
        await authedFetch(`/contact-groups/${initial.id}`, {
          method: 'PATCH',
          body: JSON.stringify(payload),
        });
      } else {
        const payload: ContactGroupCreatePayload = {
          name: name.trim(),
          description: description.trim() || null,
        };
        await authedFetch('/contact-groups', {
          method: 'POST',
          body: JSON.stringify(payload),
        });
      }
      onSaved();
      onClose();
    } catch (e2) {
      setErr(
        e2 instanceof ApiError ? e2.message : 'No se pudo guardar el grupo.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title={isEdit ? 'Editar grupo' : 'Nuevo grupo'}
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-3 text-sm">
        <div>
          <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
            Nombre
          </label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Clientes Cali"
            className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
            Descripción
          </label>
          <textarea
            rows={2}
            value={description ?? ''}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Opcional"
            className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
          />
        </div>
        {err && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {err}
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white text-gloma-brown-dark"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={busy}
            className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark disabled:opacity-50"
          >
            {busy ? 'Guardando…' : isEdit ? 'Guardar' : 'Crear grupo'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ─── Drawer: Detalle de grupo (miembros) ────────────────────────────────

function GroupDetailDrawer({
  groupId,
  onClose,
  onChanged,
}: {
  groupId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<ContactGroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    authedFetch<ContactGroupDetail>(`/contact-groups/${groupId}`)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled)
          setErr(
            e instanceof ApiError
              ? e.message
              : 'No se pudo cargar el grupo.',
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [groupId, reloadTick]);

  const filteredMembers = useMemo(() => {
    if (!detail) return [];
    const q = search.trim().toLowerCase();
    if (!q) return detail.members;
    return detail.members.filter((c) => {
      return (
        (c.name ?? '').toLowerCase().includes(q) ||
        c.phone_e164.includes(q) ||
        (c.email ?? '').toLowerCase().includes(q)
      );
    });
  }, [detail, search]);

  const removeMember = async (contactId: number) => {
    if (!detail) return;
    if (!window.confirm('¿Quitar este miembro del grupo?')) return;
    setRemovingId(contactId);
    try {
      await authedFetch(
        `/contact-groups/${detail.id}/members/${contactId}`,
        { method: 'DELETE' },
      );
      reload();
      onChanged();
    } catch (e) {
      window.alert(
        e instanceof ApiError ? e.message : 'No se pudo quitar el miembro.',
      );
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex" onClick={onClose}>
      <div className="flex-1 bg-black/40" />
      <div
        className="w-full md:w-[460px] bg-gloma-cream border-l border-gloma-brown-light/20 shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gloma-brown-light/15">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-gloma-brown-light">
              Grupo
            </p>
            <h3 className="font-heading text-lg font-bold text-gloma-brown-dark">
              {detail?.name ?? '…'}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="text-gloma-brown-light hover:text-gloma-brown-dark text-lg leading-none"
          >
            ×
          </button>
        </div>

        <div className="px-5 py-3 border-b border-gloma-brown-light/15 text-xs text-gloma-brown-light">
          {detail?.description ? (
            <p>{detail.description}</p>
          ) : (
            <p className="italic">Sin descripción.</p>
          )}
          <p className="mt-1">
            <strong className="text-gloma-brown-dark">
              {detail?.member_count ?? 0}
            </strong>{' '}
            miembros
          </p>
        </div>

        <div className="px-5 py-3 flex gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar miembro…"
            className="flex-1 px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
          />
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="px-3 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark"
          >
            + Añadir
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 pb-5">
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-10 rounded-md bg-gloma-brown-light/10 animate-pulse"
                />
              ))}
            </div>
          ) : err ? (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {err}
            </div>
          ) : filteredMembers.length === 0 ? (
            <div className="text-xs text-gloma-brown-light text-center py-6">
              {detail?.member_count === 0
                ? 'Este grupo aún no tiene miembros.'
                : 'Sin resultados.'}
            </div>
          ) : (
            <ul className="divide-y divide-gloma-brown-light/15 bg-white rounded-lg border border-gloma-brown-light/15">
              {filteredMembers.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between px-3 py-2 text-xs"
                >
                  <div>
                    <p className="font-semibold text-gloma-brown-dark">
                      {m.name || '—'}
                    </p>
                    <p className="text-gloma-brown-light">
                      {maskPhone(m.phone_e164)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeMember(m.id)}
                    disabled={removingId === m.id}
                    className="text-red-600 hover:text-red-700 text-[11px] font-semibold disabled:opacity-50"
                  >
                    {removingId === m.id ? 'Quitando…' : 'Quitar'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {adding && detail && (
          <AddMembersModal
            groupId={detail.id}
            existingIds={new Set(detail.members.map((m) => m.id))}
            onClose={() => setAdding(false)}
            onAdded={() => {
              reload();
              onChanged();
            }}
          />
        )}
      </div>
    </div>
  );
}

// ─── Modal: Añadir miembros a un grupo ──────────────────────────────────

function AddMembersModal({
  groupId,
  existingIds,
  onClose,
  onAdded,
}: {
  groupId: number;
  existingIds: Set<number>;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({
      limit: '200',
      offset: '0',
    });
    if (search.trim()) params.set('q', search.trim());
    authedFetch<Contact[]>(`/contacts?${params.toString()}`)
      .then((d) => {
        if (!cancelled) setContacts(d);
      })
      .catch((e) => {
        if (!cancelled)
          setErr(
            e instanceof ApiError
              ? e.message
              : 'No se pudieron cargar los contactos.',
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search]);

  const toggle = (id: number) => {
    setSelected((s) => {
      const ns = new Set(s);
      if (ns.has(id)) ns.delete(id);
      else ns.add(id);
      return ns;
    });
  };

  const submit = async () => {
    if (selected.size === 0) return;
    setSaving(true);
    setErr(null);
    try {
      await authedFetch(`/contact-groups/${groupId}/members`, {
        method: 'POST',
        body: JSON.stringify({ contact_ids: Array.from(selected) }),
      });
      onAdded();
      onClose();
    } catch (e) {
      setErr(
        e instanceof ApiError
          ? e.message
          : 'No se pudieron añadir miembros.',
      );
    } finally {
      setSaving(false);
    }
  };

  const available = (contacts ?? []).filter((c) => !existingIds.has(c.id));

  return (
    <ModalShell title="Añadir miembros" onClose={onClose} size="lg">
      <div className="space-y-3 text-sm">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar por nombre, teléfono o email…"
          className="w-full px-3 py-2 rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
        />
        <div className="max-h-72 overflow-y-auto bg-white border border-gloma-brown-light/15 rounded-lg">
          {loading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="h-8 rounded-md bg-gloma-brown-light/10 animate-pulse"
                />
              ))}
            </div>
          ) : available.length === 0 ? (
            <p className="text-xs text-gloma-brown-light text-center py-6">
              No hay más contactos para añadir.
            </p>
          ) : (
            <ul className="divide-y divide-gloma-brown-light/15">
              {available.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center gap-3 px-3 py-2 text-xs cursor-pointer hover:bg-gloma-rose-soft/30"
                  onClick={() => toggle(c.id)}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggle(c.id)}
                    onClick={(e) => e.stopPropagation()}
                    className="rounded border-gloma-brown-light/40"
                  />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-gloma-brown-dark truncate">
                      {c.name || '—'}
                    </p>
                    <p className="text-gloma-brown-light truncate">
                      {maskPhone(c.phone_e164)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
        {err && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {err}
          </div>
        )}
        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-gloma-brown-light">
            {selected.size} seleccionado(s)
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white text-gloma-brown-dark"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={saving || selected.size === 0}
              className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark disabled:opacity-50"
            >
              {saving ? 'Añadiendo…' : `Añadir (${selected.size})`}
            </button>
          </div>
        </div>
      </div>
    </ModalShell>
  );
}

// ─── Página ─────────────────────────────────────────────────────────────

export default function ContactosPage() {
  const [tab, setTab] = useState<Tab>('contactos');

  // Lista de grupos (compartida entre tabs: chips, filtros, asignar).
  const [groups, setGroups] = useState<ContactGroup[] | null>(null);
  const [groupsErr, setGroupsErr] = useState<string | null>(null);
  const [groupsReload, setGroupsReload] = useState(0);

  // Estado de contactos.
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [contactsLoading, setContactsLoading] = useState(true);
  const [contactsErr, setContactsErr] = useState<string | null>(null);
  const [contactsReload, setContactsReload] = useState(0);

  // Filtros tab contactos.
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [groupFilter, setGroupFilter] = useState<number | 'all'>('all');
  const [optInFilter, setOptInFilter] = useState<OptInFilter>('all');
  const [page, setPage] = useState(0); // offset = page * PAGE_SIZE

  // Modales / drawers.
  const [showContactForm, setShowContactForm] = useState<Contact | 'new' | null>(
    null,
  );
  const [showAssign, setShowAssign] = useState<Contact | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [showGroupForm, setShowGroupForm] = useState<ContactGroup | 'new' | null>(
    null,
  );
  const [openGroupId, setOpenGroupId] = useState<number | null>(null);

  // Cache de membresías por contacto (lazy load por chip — solo grupos vistos).
  // El backend NO devuelve grupos por contacto, así que mostramos chips solo
  // cuando filtramos por grupo. Si no, los chips se omiten (consistente con
  // el contrato actual del endpoint `/contacts`).
  const debouncedQRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(() => {
    if (debouncedQRef.current) clearTimeout(debouncedQRef.current);
    debouncedQRef.current = setTimeout(() => {
      setDebouncedQ(q.trim());
      setPage(0);
    }, 250);
    return () => {
      if (debouncedQRef.current) clearTimeout(debouncedQRef.current);
    };
  }, [q]);

  // Cargar grupos.
  useEffect(() => {
    let cancelled = false;
    authedFetch<ContactGroup[]>('/contact-groups')
      .then((g) => {
        if (!cancelled) setGroups(g);
      })
      .catch((e) => {
        if (!cancelled)
          setGroupsErr(
            e instanceof ApiError
              ? e.message
              : 'No se pudieron cargar los grupos.',
          );
      });
    return () => {
      cancelled = true;
    };
  }, [groupsReload]);

  // Cargar contactos según filtros.
  useEffect(() => {
    let cancelled = false;
    setContactsLoading(true);
    setContactsErr(null);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (debouncedQ) params.set('q', debouncedQ);
    if (groupFilter !== 'all') params.set('group_id', String(groupFilter));
    if (optInFilter === 'only_opt_in') params.set('opt_in_only', 'true');
    authedFetch<Contact[]>(`/contacts?${params.toString()}`)
      .then((c) => {
        if (!cancelled) setContacts(c);
      })
      .catch((e) => {
        if (!cancelled)
          setContactsErr(
            e instanceof ApiError
              ? e.message
              : 'No se pudieron cargar los contactos.',
          );
      })
      .finally(() => {
        if (!cancelled) setContactsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [contactsReload, debouncedQ, groupFilter, optInFilter, page]);

  const reloadContacts = () => setContactsReload((t) => t + 1);
  const reloadGroups = () => setGroupsReload((t) => t + 1);

  const deleteContact = async (c: Contact) => {
    if (
      !window.confirm(
        `¿Eliminar el contacto ${c.name || maskPhone(c.phone_e164)}? Esta acción no se puede deshacer.`,
      )
    )
      return;
    try {
      await authedFetch(`/contacts/${c.id}`, { method: 'DELETE' });
      reloadContacts();
      reloadGroups(); // member_count puede cambiar
    } catch (e) {
      window.alert(
        e instanceof ApiError ? e.message : 'No se pudo eliminar el contacto.',
      );
    }
  };

  const deleteGroup = async (g: ContactGroup) => {
    if (
      !window.confirm(
        `¿Eliminar el grupo "${g.name}"? Los contactos no se borran, pero perderán la pertenencia.`,
      )
    )
      return;
    try {
      await authedFetch(`/contact-groups/${g.id}`, { method: 'DELETE' });
      reloadGroups();
    } catch (e) {
      window.alert(
        e instanceof ApiError ? e.message : 'No se pudo eliminar el grupo.',
      );
    }
  };

  const totalContacts = contacts?.length ?? 0;
  const onLastPage = totalContacts < PAGE_SIZE;

  return (
    <Layout variant="fullscreen">
      <div className="p-6 md:p-8 w-full bg-gloma-cream min-h-screen font-body">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-6">
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-gloma-brown-light">
              <Link href="/campanas" legacyBehavior>
                <a className="hover:text-gloma-brown">Campañas</a>
              </Link>{' '}
              · /campanas/contactos
            </p>
            <h1 className="font-heading text-2xl md:text-3xl font-extrabold text-gloma-brown-dark">
              Contactos y Grupos
            </h1>
            <p className="text-sm text-gloma-brown-light mt-1 max-w-2xl">
              Directorio de la cuenta. Crea grupos para reutilizarlos al armar
              campañas masivas.
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 text-sm border-b border-gloma-brown-light/20">
          <button
            type="button"
            onClick={() => setTab('contactos')}
            className={classNames(
              'px-4 py-2 border-b-2 transition-colors',
              tab === 'contactos'
                ? 'border-gloma-brown text-gloma-brown-dark font-semibold'
                : 'border-transparent text-gloma-brown-light hover:text-gloma-brown',
            )}
          >
            Contactos
          </button>
          <button
            type="button"
            onClick={() => setTab('grupos')}
            className={classNames(
              'px-4 py-2 border-b-2 transition-colors',
              tab === 'grupos'
                ? 'border-gloma-brown text-gloma-brown-dark font-semibold'
                : 'border-transparent text-gloma-brown-light hover:text-gloma-brown',
            )}
          >
            Grupos
            {groups && (
              <span className="ml-1 text-gloma-brown-light">
                · {groups.length}
              </span>
            )}
          </button>
        </div>

        {tab === 'contactos' ? (
          <section>
            {/* Toolbar */}
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
              <div className="flex gap-2 flex-wrap text-xs">
                <input
                  type="text"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Buscar por nombre, teléfono o email…"
                  className="px-3 py-2 border border-gloma-brown-light/30 rounded-md w-60 bg-white focus:outline-none focus:border-gloma-brown"
                />
                <select
                  value={groupFilter === 'all' ? 'all' : String(groupFilter)}
                  onChange={(e) => {
                    const v = e.target.value;
                    setGroupFilter(v === 'all' ? 'all' : Number(v));
                    setPage(0);
                  }}
                  className="px-2 py-2 border border-gloma-brown-light/30 rounded-md bg-white focus:outline-none focus:border-gloma-brown"
                >
                  <option value="all">Todos los grupos</option>
                  {(groups ?? []).map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
                <label className="inline-flex items-center gap-2 px-2 py-2 border border-gloma-brown-light/30 rounded-md bg-white">
                  <input
                    type="checkbox"
                    checked={optInFilter === 'only_opt_in'}
                    onChange={(e) => {
                      setOptInFilter(e.target.checked ? 'only_opt_in' : 'all');
                      setPage(0);
                    }}
                    className="rounded border-gloma-brown-light/40"
                  />
                  <span className="text-xs text-gloma-brown-dark">
                    Sólo con opt-in
                  </span>
                </label>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowImport(true)}
                  className="px-3 py-2 text-xs rounded-lg border border-gloma-brown-light/30 bg-white text-gloma-brown-dark hover:bg-gloma-brown-light/10"
                >
                  ⤒ Importar CSV
                </button>
                <button
                  type="button"
                  onClick={() => setShowContactForm('new')}
                  className="px-4 py-2 text-xs rounded-lg bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark"
                >
                  + Nuevo contacto
                </button>
              </div>
            </div>

            {/* Error banner */}
            {contactsErr && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm flex items-center justify-between">
                <span>{contactsErr}</span>
                <button
                  type="button"
                  onClick={reloadContacts}
                  className="ml-3 px-3 py-1 rounded-md bg-red-600 text-white text-xs font-semibold hover:bg-red-700"
                >
                  Reintentar
                </button>
              </div>
            )}

            <div className="bg-white border border-gloma-brown-light/20 rounded-2xl overflow-hidden shadow-sm">
              {contactsLoading && !contacts ? (
                <div className="p-6 space-y-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div
                      key={i}
                      className="h-10 rounded-lg bg-gloma-brown-light/10 animate-pulse"
                    />
                  ))}
                </div>
              ) : !contacts || contacts.length === 0 ? (
                page === 0 && !debouncedQ && groupFilter === 'all' && optInFilter === 'all' ? (
                  <div className="p-10 text-center">
                    <div className="w-14 h-14 mx-auto rounded-full bg-gloma-rose-soft flex items-center justify-center text-2xl mb-3">
                      📇
                    </div>
                    <h3 className="font-heading text-lg font-bold text-gloma-brown-dark mb-1">
                      Aún no tienes contactos
                    </h3>
                    <p className="text-sm text-gloma-brown-light max-w-sm mx-auto mb-4">
                      Importa un CSV o crea uno manualmente para empezar.
                    </p>
                    <div className="flex justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => setShowImport(true)}
                        className="px-4 py-2 rounded-lg border border-gloma-brown-light/30 bg-white text-gloma-brown-dark text-sm hover:bg-gloma-brown-light/10"
                      >
                        ⤒ Importar CSV
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowContactForm('new')}
                        className="px-4 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark"
                      >
                        + Crear contacto
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="p-8 text-center text-sm text-gloma-brown-light">
                    Sin resultados con los filtros actuales.
                  </div>
                )
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="bg-gloma-cream text-gloma-brown-light">
                      <tr>
                        <th className="text-left font-medium px-4 py-2">
                          Teléfono
                        </th>
                        <th className="text-left font-medium px-4 py-2">
                          Nombre
                        </th>
                        <th className="text-left font-medium px-4 py-2">
                          Email
                        </th>
                        <th className="text-left font-medium px-4 py-2">
                          Opt-in
                        </th>
                        {groupFilter !== 'all' && (
                          <th className="text-left font-medium px-4 py-2">
                            Grupo
                          </th>
                        )}
                        <th className="text-left font-medium px-4 py-2">
                          Última actualización
                        </th>
                        <th className="text-right font-medium px-4 py-2">
                          Acciones
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gloma-brown-light/10">
                      {contacts.map((c) => (
                        <tr
                          key={c.id}
                          className="hover:bg-gloma-rose-soft/30 transition-colors"
                        >
                          <td className="px-4 py-3 font-mono text-xs text-gloma-brown-dark">
                            {maskPhone(c.phone_e164)}
                          </td>
                          <td className="px-4 py-3 text-gloma-brown-dark">
                            {c.name || (
                              <span className="text-gloma-brown-light">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-gloma-brown-light">
                            {c.email || '—'}
                          </td>
                          <td className="px-4 py-3">
                            <OptInBadge optIn={c.opt_in} />
                          </td>
                          {groupFilter !== 'all' && (
                            <td className="px-4 py-3">
                              <GroupChips
                                groups={
                                  groups?.filter(
                                    (g) => g.id === groupFilter,
                                  ) ?? []
                                }
                              />
                            </td>
                          )}
                          <td className="px-4 py-3 text-gloma-brown-light text-xs">
                            {fmtDate(c.updated_at)}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex justify-end gap-3 text-xs font-semibold">
                              <button
                                type="button"
                                onClick={() => setShowContactForm(c)}
                                className="text-gloma-brown hover:text-gloma-brown-dark hover:underline"
                              >
                                Editar
                              </button>
                              <button
                                type="button"
                                onClick={() => setShowAssign(c)}
                                className="text-gloma-brown hover:text-gloma-brown-dark hover:underline"
                              >
                                Asignar a grupo
                              </button>
                              <button
                                type="button"
                                onClick={() => deleteContact(c)}
                                className="text-red-600 hover:text-red-700"
                              >
                                Eliminar
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {/* Paginación */}
                  <div className="px-4 py-3 border-t border-gloma-brown-light/15 flex items-center justify-between text-xs text-gloma-brown-light">
                    <span>
                      Mostrando {page * PAGE_SIZE + 1}–
                      {page * PAGE_SIZE + totalContacts} contactos
                    </span>
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                        disabled={page === 0}
                        className="px-3 py-1 rounded-md border border-gloma-brown-light/30 bg-white disabled:opacity-40"
                      >
                        ← Anterior
                      </button>
                      <span className="px-3 py-1 rounded-md bg-gloma-brown text-gloma-cream font-semibold">
                        Página {page + 1}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPage((p) => p + 1)}
                        disabled={onLastPage}
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
        ) : (
          <section>
            {/* Toolbar grupos */}
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
              <p className="text-sm text-gloma-brown-light">
                Crea grupos reutilizables para campañas a múltiples contactos.
              </p>
              <button
                type="button"
                onClick={() => setShowGroupForm('new')}
                className="px-4 py-2 text-xs rounded-lg bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark"
              >
                + Nuevo grupo
              </button>
            </div>

            {groupsErr && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm flex items-center justify-between">
                <span>{groupsErr}</span>
                <button
                  type="button"
                  onClick={reloadGroups}
                  className="ml-3 px-3 py-1 rounded-md bg-red-600 text-white text-xs font-semibold hover:bg-red-700"
                >
                  Reintentar
                </button>
              </div>
            )}

            {!groups ? (
              <div className="grid md:grid-cols-3 gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-32 rounded-2xl bg-white border border-gloma-brown-light/20 animate-pulse"
                  />
                ))}
              </div>
            ) : groups.length === 0 ? (
              <div className="bg-white border border-gloma-brown-light/20 rounded-2xl p-10 text-center">
                <div className="w-14 h-14 mx-auto rounded-full bg-gloma-rose-soft flex items-center justify-center text-2xl mb-3">
                  👥
                </div>
                <h3 className="font-heading text-lg font-bold text-gloma-brown-dark mb-1">
                  No tienes grupos
                </h3>
                <p className="text-sm text-gloma-brown-light max-w-md mx-auto mb-4">
                  Crea uno para enviar campañas a varios contactos a la vez.
                </p>
                <button
                  type="button"
                  onClick={() => setShowGroupForm('new')}
                  className="px-4 py-2 rounded-lg bg-gloma-brown text-gloma-cream font-semibold text-sm hover:bg-gloma-brown-dark"
                >
                  + Crear primer grupo
                </button>
              </div>
            ) : (
              <div className="grid md:grid-cols-3 gap-3">
                {groups.map((g) => (
                  <div
                    key={g.id}
                    className="bg-white border border-gloma-brown-light/20 rounded-2xl p-4 shadow-sm cursor-pointer hover:border-gloma-brown/40 transition-colors"
                    onClick={() => setOpenGroupId(g.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="min-w-0">
                        <h5 className="font-heading font-bold text-gloma-brown-dark truncate">
                          {g.name}
                        </h5>
                        <p
                          className="text-xs text-gloma-brown-light line-clamp-2"
                          title={g.description ?? ''}
                        >
                          {g.description || 'Sin descripción'}
                        </p>
                      </div>
                    </div>
                    <p className="mt-3 text-xs">
                      <span className="font-heading text-2xl font-bold text-gloma-brown-dark">
                        {g.member_count}
                      </span>{' '}
                      <span className="text-gloma-brown-light">miembros</span>
                    </p>
                    <div
                      className="flex gap-2 mt-3 text-[11px]"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        onClick={() => setOpenGroupId(g.id)}
                        className="px-2 py-1 rounded bg-gloma-rose-soft/40 text-gloma-brown-dark font-semibold hover:bg-gloma-rose-soft"
                      >
                        Ver miembros
                      </button>
                      <button
                        type="button"
                        onClick={() => setShowGroupForm(g)}
                        className="px-2 py-1 rounded border border-gloma-brown-light/30 text-gloma-brown-dark"
                      >
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteGroup(g)}
                        className="px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50"
                      >
                        Eliminar
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </div>

      {/* Modales */}
      {showContactForm !== null && (
        <ContactFormModal
          initial={showContactForm === 'new' ? null : showContactForm}
          onClose={() => setShowContactForm(null)}
          onSaved={() => {
            reloadContacts();
            reloadGroups();
          }}
        />
      )}
      {showAssign && (
        <AssignToGroupModal
          contact={showAssign}
          groups={groups ?? []}
          onClose={() => setShowAssign(null)}
          onAssigned={() => {
            reloadGroups();
            reloadContacts();
          }}
        />
      )}
      {showImport && (
        <ImportCsvModal
          onClose={() => setShowImport(false)}
          onImported={() => {
            reloadContacts();
            reloadGroups();
          }}
        />
      )}
      {showGroupForm !== null && (
        <GroupFormModal
          initial={showGroupForm === 'new' ? null : showGroupForm}
          onClose={() => setShowGroupForm(null)}
          onSaved={() => reloadGroups()}
        />
      )}
      {openGroupId !== null && (
        <GroupDetailDrawer
          groupId={openGroupId}
          onClose={() => setOpenGroupId(null)}
          onChanged={() => reloadGroups()}
        />
      )}
    </Layout>
  );
}
