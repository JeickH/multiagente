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
 *   - GET    /contacts/plantilla      (xlsx de guía)
 *   - POST   /contacts/import-excel   (multipart + país por defecto)
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
 *   - Los `errors` del importador NO contienen teléfono crudo (regla 1 /
 *     S13-009 backend). Si llegara crudo, es bug del backend y debe reportarse.
 */
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import Layout from '../../components/Layout';
import { ApiError, authedFetch } from '../../lib/api';
import { fmtDate, maskPhone } from '../../lib/format';
import { cerrarSesion, getToken } from '../../lib/session';
import type {
  Contact,
  ContactCreatePayload,
  ContactExcelImportResult,
  ContactGroup,
  ContactGroupCreatePayload,
  ContactGroupDetail,
  ContactGroupUpdatePayload,
  ContactUpdatePayload,
} from '../../types/contacts';

type Tab = 'contactos' | 'grupos';
type OptInFilter = 'all' | 'only_opt_in';

const PAGE_SIZE = 50;

/**
 * Países que aparecen en el desplegable "si mi lista no trae código de país".
 * Colombia primero porque es donde opera la agencia; la lista es corta a
 * propósito — quien tenga otro país escribe el `+` en el Excel y listo.
 */
const PAISES = [
  { codigo: '57', nombre: 'Colombia (+57)' },
  { codigo: '52', nombre: 'México (+52)' },
  { codigo: '51', nombre: 'Perú (+51)' },
  { codigo: '56', nombre: 'Chile (+56)' },
  { codigo: '54', nombre: 'Argentina (+54)' },
  { codigo: '593', nombre: 'Ecuador (+593)' },
  { codigo: '507', nombre: 'Panamá (+507)' },
  { codigo: '1', nombre: 'EE. UU. / Canadá (+1)' },
  { codigo: '34', nombre: 'España (+34)' },
];

// ─── Utilities ──────────────────────────────────────────────────────────

function classNames(...xs: (string | false | null | undefined)[]): string {
  return xs.filter(Boolean).join(' ');
}

/** El JWT para las llamadas que no pasan por `authedFetch` (regla 7). */
function tokenOMuere(): string {
  const token = getToken();
  if (!token) {
    cerrarSesion();
    throw new ApiError('No autenticado', 401);
  }
  return token;
}

/** Traduce una respuesta no-OK al `ApiError` con el detalle ya sanitizado. */
async function comoApiError(res: Response, fallback: string): Promise<ApiError> {
  if (res.status === 401) {
    cerrarSesion();
    return new ApiError('Sesión expirada', 401);
  }
  let detail = fallback;
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') detail = body.detail;
  } catch {
    /* no-op: la respuesta no era JSON */
  }
  return new ApiError(detail, res.status);
}

/**
 * Descarga la plantilla .xlsx. No puede ser un `<a href>` a secas: el endpoint
 * pide `Authorization`, así que se baja el archivo y se dispara la descarga
 * desde un blob.
 */
async function descargarPlantilla(): Promise<void> {
  const res = await fetch('/api/contacts/plantilla', {
    headers: { Authorization: `Bearer ${tokenOMuere()}` },
  });
  if (!res.ok) {
    throw await comoApiError(res, 'No se pudo descargar la plantilla.');
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'plantilla-contactos-gloma.xlsx';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Sube el .xlsx. NO usa `authedFetch` porque ese helper inyecta
 * `Content-Type: application/json` cuando hay body, lo que rompe el boundary
 * que el browser genera para FormData.
 */
async function subirExcel(
  file: File,
  paisDefault: string,
): Promise<ContactExcelImportResult> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('pais_default', paisDefault);
  const res = await fetch('/api/contacts/import-excel', {
    method: 'POST',
    headers: { Authorization: `Bearer ${tokenOMuere()}` },
    body: fd,
  });
  if (!res.ok) {
    throw await comoApiError(res, 'No se pudo importar el archivo.');
  }
  return (await res.json()) as ContactExcelImportResult;
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

// ─── Editor de datos extra (antes: un textarea con JSON) ────────────────

interface FilaAtributo {
  campo: string;
  valor: string;
}

function aFilas(attrs: Record<string, unknown> | null | undefined): FilaAtributo[] {
  if (!attrs) return [];
  return Object.entries(attrs).map(([campo, valor]) => ({
    campo,
    valor:
      valor === null || valor === undefined
        ? ''
        : typeof valor === 'object'
          ? JSON.stringify(valor)
          : String(valor),
  }));
}

/**
 * Convierte las filas de vuelta a objeto. Las filas sin nombre de campo se
 * descartan; si el mismo campo se repite, gana el último (que es lo que la
 * usuaria acaba de escribir).
 */
function aObjeto(filas: FilaAtributo[]): Record<string, string> {
  const salida: Record<string, string> = {};
  for (const f of filas) {
    const campo = f.campo.trim();
    if (!campo) continue;
    salida[campo] = f.valor.trim();
  }
  return salida;
}

/**
 * Tabla campo → valor. Antes esto era un `<textarea>` donde había que escribir
 * `{"ciudad":"Cali"}` a mano: una llave mal puesta y el formulario no
 * guardaba. Aquí no hay JSON que escribir ni que leer.
 */
function EditorAtributos({
  filas,
  onChange,
}: {
  filas: FilaAtributo[];
  onChange: (filas: FilaAtributo[]) => void;
}) {
  const editar = (i: number, parche: Partial<FilaAtributo>) => {
    onChange(filas.map((f, idx) => (idx === i ? { ...f, ...parche } : f)));
  };
  const quitar = (i: number) => onChange(filas.filter((_, idx) => idx !== i));
  const agregar = () => onChange([...filas, { campo: '', valor: '' }]);

  const duplicados = new Set(
    filas
      .map((f) => f.campo.trim().toLowerCase())
      .filter((c, i, arr) => c && arr.indexOf(c) !== i),
  );

  return (
    <div>
      <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
        Datos extra del contacto
      </label>
      <p className="text-[11px] text-gloma-brown-light mb-2">
        Lo que quieras guardar de esta persona (ciudad, destino favorito,
        idioma…). Después puedes usar estos datos para personalizar el mensaje
        de una campaña.
      </p>

      {filas.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gloma-brown-light/30 bg-white px-3 py-4 text-center text-[11px] text-gloma-brown-light">
          Este contacto no tiene datos extra todavía.
        </div>
      ) : (
        <div className="rounded-lg border border-gloma-brown-light/20 bg-white overflow-hidden">
          <div className="grid grid-cols-[1fr_1fr_auto] gap-2 px-3 py-1.5 bg-gloma-cream text-[10px] uppercase tracking-widest text-gloma-brown-light">
            <span>Campo</span>
            <span>Valor</span>
            <span className="w-6" />
          </div>
          <div className="divide-y divide-gloma-brown-light/10">
            {filas.map((f, i) => (
              <div
                key={i}
                className="grid grid-cols-[1fr_1fr_auto] gap-2 px-3 py-2 items-center"
              >
                <input
                  type="text"
                  value={f.campo}
                  onChange={(e) => editar(i, { campo: e.target.value })}
                  placeholder="Ciudad"
                  aria-label={`Nombre del dato ${i + 1}`}
                  className={classNames(
                    'px-2 py-1 text-xs rounded-md border bg-white focus:outline-none focus:border-gloma-brown',
                    duplicados.has(f.campo.trim().toLowerCase())
                      ? 'border-amber-400'
                      : 'border-gloma-brown-light/30',
                  )}
                />
                <input
                  type="text"
                  value={f.valor}
                  onChange={(e) => editar(i, { valor: e.target.value })}
                  placeholder="Cali"
                  aria-label={`Valor del dato ${i + 1}`}
                  className="px-2 py-1 text-xs rounded-md border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
                />
                <button
                  type="button"
                  onClick={() => quitar(i)}
                  aria-label={`Quitar el dato ${f.campo || i + 1}`}
                  title="Quitar"
                  className="w-6 h-6 rounded-md border border-red-200 text-red-600 hover:bg-red-50 text-xs leading-none"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mt-2">
        <button
          type="button"
          onClick={agregar}
          className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown text-gloma-brown bg-white hover:bg-gloma-rose-soft/50 font-semibold"
        >
          + Agregar dato
        </button>
        {duplicados.size > 0 && (
          <span className="text-[11px] text-amber-700">
            Hay campos repetidos: se guardará el último.
          </span>
        )}
      </div>
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
  const [filasAttrs, setFilasAttrs] = useState<FilaAtributo[]>(
    aFilas(initial?.attributes),
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    // Se manda siempre el diccionario completo: es la vía para BORRAR un dato
    // (el importador de Excel, en cambio, fusiona y nunca borra).
    const attrs: Record<string, string> = aObjeto(filasAttrs);
    try {
      if (isEdit && initial) {
        const payload: ContactUpdatePayload = {
          name: name.trim() || null,
          email: email.trim() || null,
          attributes: attrs,
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
          attributes: attrs,
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
        <EditorAtributos filas={filasAttrs} onChange={setFilasAttrs} />
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

// ─── Modal: Importar contactos desde Excel ──────────────────────────────

function ResumenImportacion({ result }: { result: ContactExcelImportResult }) {
  const tarjetas = [
    {
      etiqueta: 'Leídos',
      valor: result.total,
      clase: 'bg-gloma-cream text-gloma-brown-dark',
      sub: 'text-gloma-brown-light',
    },
    {
      etiqueta: 'Creados',
      valor: result.created,
      clase: 'bg-green-50 border border-green-200 text-green-700',
      sub: 'text-green-700',
    },
    {
      etiqueta: 'Actualizados',
      valor: result.updated,
      clase: 'bg-blue-50 border border-blue-200 text-blue-700',
      sub: 'text-blue-700',
    },
    {
      etiqueta: 'Con problemas',
      valor: result.rejected,
      clase:
        result.rejected > 0
          ? 'bg-amber-50 border border-amber-200 text-amber-800'
          : 'bg-gray-50 border border-gray-200 text-gray-500',
      sub: result.rejected > 0 ? 'text-amber-800' : 'text-gray-500',
    },
  ];

  return (
    <div className="space-y-4 text-sm">
      <div className="rounded-lg border border-gloma-brown-light/20 bg-white p-4">
        <p className="font-heading font-bold text-gloma-brown-dark mb-3">
          {result.created + result.updated > 0
            ? '✓ Listo, tus contactos ya están cargados'
            : 'No se cargó ningún contacto'}
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {tarjetas.map((t) => (
            <div key={t.etiqueta} className={classNames('rounded-md p-3 text-center', t.clase)}>
              <p className={classNames('text-[10px] uppercase tracking-widest', t.sub)}>
                {t.etiqueta}
              </p>
              <p className="font-heading text-xl font-bold">{t.valor}</p>
            </div>
          ))}
        </div>
        {result.detected_attributes.length > 0 && (
          <p className="text-[11px] text-gloma-brown-light mt-3">
            Datos extra guardados de cada contacto:{' '}
            {result.detected_attributes.map((a) => (
              <span
                key={a}
                className="inline-block px-1.5 py-0.5 mr-1 rounded bg-gloma-rose-soft text-gloma-brown-dark"
              >
                {a}
              </span>
            ))}
          </p>
        )}
      </div>

      {result.notice && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          {result.notice}
        </div>
      )}

      {result.errors.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-white overflow-hidden">
          <p className="text-xs font-semibold text-amber-900 bg-amber-50 px-3 py-2">
            {result.errors.length} fila(s) que no se pudieron cargar — corrígelas
            en el Excel y vuelve a subirlo (lo ya cargado no se duplica):
          </p>
          <div className="max-h-56 overflow-y-auto">
            <table className="min-w-full text-xs">
              <thead className="bg-gloma-cream text-gloma-brown-light">
                <tr>
                  <th className="text-left font-medium px-3 py-1.5 w-20">Fila</th>
                  <th className="text-left font-medium px-3 py-1.5">Qué pasó</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gloma-brown-light/10">
                {result.errors.map((e, i) => (
                  <tr key={`${e.row}-${i}`}>
                    <td className="px-3 py-1.5 font-semibold text-gloma-brown-dark">
                      {e.row}
                    </td>
                    <td className="px-3 py-1.5 text-gloma-brown-dark">{e.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function ImportExcelModal({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [pais, setPais] = useState('57');
  const [busy, setBusy] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [result, setResult] = useState<ContactExcelImportResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const bajarPlantilla = async () => {
    setDescargando(true);
    setErr(null);
    try {
      await descargarPlantilla();
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message : 'No se pudo descargar la plantilla.',
      );
    } finally {
      setDescargando(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setErr('Elige el archivo de Excel que quieres subir.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      setResult(await subirExcel(file, pais));
    } catch (e2) {
      setErr(
        e2 instanceof ApiError ? e2.message : 'No se pudo importar el archivo.',
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
    <ModalShell
      title="Cargar contactos desde Excel"
      onClose={closeAndRefresh}
      size="lg"
    >
      {result ? (
        <div className="space-y-4">
          <ResumenImportacion result={result} />
          <div className="flex justify-between pt-1">
            <button
              type="button"
              onClick={() => {
                setResult(null);
                setFile(null);
              }}
              className="px-3 py-1.5 text-xs rounded-md border border-gloma-brown-light/30 bg-white text-gloma-brown-dark"
            >
              Subir otro archivo
            </button>
            <button
              type="button"
              onClick={closeAndRefresh}
              className="px-4 py-1.5 text-xs rounded-md bg-gloma-brown text-gloma-cream font-semibold hover:bg-gloma-brown-dark"
            >
              Ver mis contactos
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4 text-sm">
          {/* Paso 1 */}
          <div className="rounded-lg border border-gloma-brown-light/20 bg-white p-4">
            <p className="text-xs font-semibold text-gloma-brown-dark mb-1">
              <span className="inline-flex w-5 h-5 mr-1.5 rounded-full bg-gloma-brown text-gloma-cream items-center justify-center text-[10px] font-bold">
                1
              </span>
              Descarga la plantilla
            </p>
            <p className="text-[11px] text-gloma-brown-light mb-3 ml-6">
              Trae los títulos correctos, un ejemplo lleno y una hoja con las
              instrucciones. Ábrela en Excel, escribe tus contactos y guárdala.
            </p>
            <div className="ml-6">
              <button
                type="button"
                onClick={bajarPlantilla}
                disabled={descargando}
                className="px-4 py-2 text-xs rounded-lg border border-gloma-brown text-gloma-brown bg-white font-semibold hover:bg-gloma-rose-soft/50 disabled:opacity-50"
              >
                {descargando ? 'Descargando…' : '↓ Descargar plantilla (.xlsx)'}
              </button>
            </div>
          </div>

          {/* Paso 2 */}
          <div className="rounded-lg border border-gloma-brown-light/20 bg-white p-4">
            <p className="text-xs font-semibold text-gloma-brown-dark mb-1">
              <span className="inline-flex w-5 h-5 mr-1.5 rounded-full bg-gloma-brown text-gloma-cream items-center justify-center text-[10px] font-bold">
                2
              </span>
              Sube tu archivo lleno
            </p>
            <div className="ml-6 mt-3">
              <div className="rounded-lg border-2 border-dashed border-gloma-brown-light/30 bg-gloma-cream p-5 text-center">
                <input
                  id="excel-file"
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block mx-auto text-xs"
                />
                {file ? (
                  <p className="text-[11px] text-gloma-brown-dark mt-2">
                    Seleccionado: <strong>{file.name}</strong> ·{' '}
                    {Math.ceil(file.size / 1024)} KB
                  </p>
                ) : (
                  <p className="text-[11px] text-gloma-brown-light mt-2">
                    Archivos .xlsx de hasta 2 MB (unos 5.000 contactos).
                  </p>
                )}
              </div>

              <div className="mt-3">
                <label className="block text-xs font-semibold text-gloma-brown-dark mb-1">
                  Si tus teléfonos no tienen código de país, ¿de dónde son?
                </label>
                <select
                  value={pais}
                  onChange={(e) => setPais(e.target.value)}
                  className="w-full md:w-72 px-3 py-2 text-sm rounded-lg border border-gloma-brown-light/30 bg-white focus:outline-none focus:border-gloma-brown"
                >
                  {PAISES.map((p) => (
                    <option key={p.codigo} value={p.codigo}>
                      {p.nombre}
                    </option>
                  ))}
                  <option value="">Todos ya traen su código (+57, +52…)</option>
                </select>
                <p className="text-[11px] text-gloma-brown-light mt-1">
                  Solo se usa para los números que vengan sin el «+». Los que ya
                  lo traen se respetan tal cual.
                </p>
              </div>
            </div>
          </div>

          {err && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
              {err}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
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
              {busy ? 'Cargando…' : 'Cargar contactos'}
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
                  ⤒ Cargar desde Excel
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
                      Carga tu lista desde un archivo de Excel o crea uno a mano.
                    </p>
                    <div className="flex justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => setShowImport(true)}
                        className="px-4 py-2 rounded-lg border border-gloma-brown-light/30 bg-white text-gloma-brown-dark text-sm hover:bg-gloma-brown-light/10"
                      >
                        ⤒ Cargar desde Excel
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
        <ImportExcelModal
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
