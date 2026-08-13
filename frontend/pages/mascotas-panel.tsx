import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout';
import { authedFetch } from '../lib/api';

/**
 * Mascotas — panel privado de la cuenta "Recupera Tu Mascota" (sprint "Ayuda a Cali").
 *
 * Tres secciones sobre los mismos datos:
 *  - "Coincidencias": los pares que detecta el cruce diario de las 12:00
 *    (`job_coincidencias_mascotas.py`) entre lo que se busca y lo que se
 *    encontró. Es la sección que hay que revisar todos los días.
 *  - "Mascotas perdidas": familias buscando a su animal.
 *  - "Mascotas encontradas": animales hallados esperando a su familia.
 *
 * El backend (`/mascotas/panel`) solo responde a la cuenta de la iniciativa y a
 * los miembros de su team; cualquier otra sesión recibe 403. El acceso se
 * consulta una vez con `GET /mascotas/access` y decide qué se renderiza.
 */

type Foto = {
  id: number;
  url: string;
  storage_key: string;
  storage_uri: string;
  content_type: string;
  bytes_size: number | null;
};

type Reporte = {
  id: number;
  codigo: string;
  tipo_registro: string;
  especie: string;
  especie_otra: string | null;
  raza: string | null;
  color: string | null;
  nombre: string | null;
  sexo: string | null;
  edad: string | null;
  tamano: string | null;
  senas: string | null;
  ubicacion: string;
  maps_url: string | null;
  barrio: string | null;
  contacto_nombre: string | null;
  contacto_telefono: string | null;
  origen_url: string | null;
  origen_nombre: string | null;
  fecha_evento: string | null;
  estado: string;
  notas: string | null;
  source: string;
  created_at: string;
  fotos: Foto[];
};

type Coincidencia = {
  id: number;
  score: number;
  estado: string;
  detalle: Record<string, number>;
  notas: string | null;
  created_at: string;
  perdida: Reporte;
  encontrada: Reporte;
};

type Sync = {
  estado: string;
  mensaje: string | null;
  iniciada: string | null;
  terminada: string | null;
  contadores: Record<string, number>;
};

type PanelResponse = {
  resumen: {
    total: number;
    perdidas: number;
    encontradas: number;
    activas: number;
    reunidas: number;
    cerradas: number;
    fotos: number;
    por_especie: Record<string, number>;
  };
  reportes: Reporte[];
  coincidencias: Coincidencia[];
  coincidencias_nuevas: number;
};

const ESTADO_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  activo: { bg: '#FEF3C7', color: '#92400E', label: 'Activo' },
  reunida: { bg: '#DCFCE7', color: '#166534', label: 'Reunida 🎉' },
  cerrado: { bg: '#F3F4F6', color: '#4B5563', label: 'Cerrado' },
};

const MATCH_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  nueva: { bg: '#DBEAFE', color: '#1E40AF', label: 'Sin revisar' },
  revisada: { bg: '#FEF3C7', color: '#92400E', label: 'Revisada' },
  confirmada: { bg: '#DCFCE7', color: '#166534', label: '¡Es la misma! 🎉' },
  descartada: { bg: '#F3F4F6', color: '#4B5563', label: 'Descartada' },
};

const ESPECIE_EMOJI: Record<string, string> = {
  perro: '🐶',
  gato: '🐱',
  otra: '🐾',
};

// Qué significa cada campo del desglose que deja el cruce: el equipo necesita
// entender POR QUÉ se propuso un par antes de llamar a una familia.
const CAMPO_LABEL: Record<string, string> = {
  especie: 'especie',
  raza: 'raza',
  color: 'color',
  tamano: 'tamaño',
  edad: 'edad',
  sexo: 'sexo',
  zona: 'zona',
  senas: 'señas',
  nombre: 'nombre',
};

const SOURCE_LABEL: Record<string, string> = {
  web: '🌐 Chat web',
  whatsapp: '💬 WhatsApp',
  demo: '🧪 Demo',
  // Reportes traídos de plataformas hermanas: el contacto vive en su ficha.
  mascotasporcolombia: '🤝 Mascotas por Colombia',
  patitasacasa: '🤝 Patitas a Casa',
};

type Seccion = 'coincidencias' | 'perdida' | 'encontrada';

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

function Badge({
  estado,
  styles,
}: {
  estado: string;
  styles: Record<string, { bg: string; color: string; label: string }>;
}) {
  const s = styles[estado] || { bg: '#F3F4F6', color: '#4B5563', label: estado };
  return (
    <span
      className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap"
      style={{ backgroundColor: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

function Tarjeta({ titulo, valor, tono }: { titulo: string; valor: number; tono: string }) {
  return (
    <div
      className="rounded-xl px-4 py-3 border"
      style={{ backgroundColor: '#FFFFFF', borderColor: '#E5E7EB' }}
    >
      <div className="text-2xl font-bold" style={{ color: tono }}>
        {valor}
      </div>
      <div className="text-xs text-gray-500 mt-0.5">{titulo}</div>
    </div>
  );
}

function SinFoto({ reporte, size }: { reporte: Reporte; size: number }) {
  return (
    <div
      className="rounded-lg flex items-center justify-center shrink-0 text-xl"
      style={{ width: size, height: size, backgroundColor: '#F3F4F6' }}
      title="Sin fotos"
    >
      {ESPECIE_EMOJI[reporte.especie] || '🐾'}
    </div>
  );
}

/** Miniatura de la primera foto del reporte (o un marcador si no tiene). */
function Miniatura({ reporte, size = 56 }: { reporte: Reporte; size?: number }) {
  if (reporte.fotos.length === 0) return <SinFoto reporte={reporte} size={size} />;
  return (
    <a href={reporte.fotos[0].url} target="_blank" rel="noopener noreferrer" className="shrink-0">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={reporte.fotos[0].url}
        alt={`Foto de ${reporte.codigo}`}
        className="rounded-lg object-cover"
        style={{ width: size, height: size }}
      />
    </a>
  );
}

function pesoLegible(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Visor de fotos a pantalla completa. La tabla muestra una miniatura pequeña
 * para no crecer de alto; aquí se ve la mascota en grande, se navega entre sus
 * fotos y se copia la ruta donde quedó guardado el archivo.
 */
function Visor({
  reporte,
  indice,
  onCerrar,
  onMover,
  onEliminarFoto,
}: {
  reporte: Reporte;
  indice: number;
  onCerrar: () => void;
  onMover: (delta: number) => void;
  onEliminarFoto: (fotoId: number) => void;
}) {
  const foto = reporte.fotos[indice];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCerrar();
      if (e.key === 'ArrowRight') onMover(1);
      if (e.key === 'ArrowLeft') onMover(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCerrar, onMover]);

  if (!foto) return null;

  return (
    <div
      role="dialog"
      aria-label={`Fotos de ${reporte.codigo}`}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.85)' }}
      onClick={onCerrar}
    >
      <div
        className="relative max-w-3xl w-full flex flex-col items-center gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={foto.url}
          alt={`Foto ${indice + 1} de ${reporte.codigo}`}
          className="rounded-xl object-contain"
          style={{ maxHeight: '70vh', maxWidth: '100%' }}
        />

        {reporte.fotos.length > 1 && (
          <div className="flex items-center gap-4 text-white text-sm">
            <button type="button" onClick={() => onMover(-1)} className="px-3 py-1.5 rounded-lg" style={{ backgroundColor: 'rgba(255,255,255,0.15)' }}>
              ‹ Anterior
            </button>
            <span>
              {indice + 1} de {reporte.fotos.length}
            </span>
            <button type="button" onClick={() => onMover(1)} className="px-3 py-1.5 rounded-lg" style={{ backgroundColor: 'rgba(255,255,255,0.15)' }}>
              Siguiente ›
            </button>
          </div>
        )}

        <div className="bg-white rounded-xl px-4 py-3 w-full text-xs">
          <div className="font-semibold text-gray-800 mb-1">
            {ESPECIE_EMOJI[reporte.especie] || '🐾'} {reporte.codigo}
            {reporte.nombre ? ` · ${reporte.nombre}` : ''} — {descripcion(reporte)}
          </div>
          {reporte.senas && <div className="text-gray-600 mb-1">{reporte.senas}</div>}
          <div className="text-gray-600">📍 {reporte.ubicacion}</div>
          {reporte.contacto_telefono ? (
            <div className="text-gray-800 font-medium">
              📞 {reporte.contacto_telefono}
              {reporte.contacto_nombre ? ` · ${reporte.contacto_nombre}` : ''}
            </div>
          ) : reporte.origen_url ? (
            <a
              href={reporte.origen_url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline font-medium"
              style={{ color: '#008069' }}
            >
              🤝 Ficha en {reporte.origen_nombre} ↗
            </a>
          ) : null}
          <div className="mt-2 pt-2 border-t border-gray-100">
            <div className="text-gray-400 mb-0.5">Recurso guardado en:</div>
            <a
              href={foto.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono break-all underline"
              style={{ color: '#008069' }}
            >
              {foto.storage_key}
            </a>
            <div className="text-gray-400 font-mono break-all">
              {foto.storage_uri}
              {foto.bytes_size ? ` · ${pesoLegible(foto.bytes_size)}` : ''}
            </div>
          </div>
          <button
            type="button"
            onClick={() => onEliminarFoto(foto.id)}
            className="mt-2 px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{ backgroundColor: '#FEE2E2', color: '#991B1B' }}
          >
            🗑 Eliminar esta foto
          </button>
        </div>

        <button
          type="button"
          onClick={onCerrar}
          className="absolute -top-2 -right-2 rounded-full w-9 h-9 flex items-center justify-center text-lg font-bold"
          style={{ backgroundColor: '#FFFFFF', color: '#374151' }}
          aria-label="Cerrar"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

/**
 * Celda compacta de fotos: una miniatura con el contador encima. Ampliar abre
 * el visor — así la tabla se mantiene legible aunque un reporte traiga 6 fotos.
 */
function CeldaFotos({
  reporte,
  onAmpliar,
}: {
  reporte: Reporte;
  onAmpliar: () => void;
}) {
  if (reporte.fotos.length === 0) return <SinFoto reporte={reporte} size={52} />;
  return (
    <button
      type="button"
      onClick={onAmpliar}
      className="relative block rounded-lg overflow-hidden transition-transform hover:scale-105"
      style={{ width: 52, height: 52 }}
      title={`Ver ${reporte.fotos.length} foto(s) de ${reporte.codigo}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={reporte.fotos[0].url}
        alt={`Foto de ${reporte.codigo}`}
        className="object-cover w-full h-full"
      />
      {reporte.fotos.length > 1 && (
        <span
          className="absolute bottom-0 right-0 text-[10px] font-bold px-1 rounded-tl"
          style={{ backgroundColor: 'rgba(0,0,0,0.65)', color: '#FFFFFF' }}
        >
          +{reporte.fotos.length - 1}
        </span>
      )}
    </button>
  );
}

/** Descripción compacta de una mascota, con lo que se sepa de ella. */
function descripcion(r: Reporte): string {
  const especie = r.especie === 'otra' && r.especie_otra ? r.especie_otra : r.especie;
  return [especie, r.raza, r.color, r.tamano, r.sexo, r.edad]
    .filter(Boolean)
    .join(' · ');
}

/** Campos editables del formulario, en el orden en que se muestran. */
type CampoForm = {
  campo: keyof Reporte;
  label: string;
  tipo?: 'texto' | 'area' | 'select' | 'fecha';
  opciones?: [string, string][];
  ancho?: 'full' | 'medio';
  obligatorio?: boolean;
  ayuda?: string;
};

const CAMPOS_FORM: CampoForm[] = [
  { campo: 'tipo_registro', label: 'Tipo de reporte', tipo: 'select', ancho: 'medio',
    opciones: [['perdida', 'La están buscando (perdida)'], ['encontrada', 'La encontraron']] },
  { campo: 'estado', label: 'Estado', tipo: 'select', ancho: 'medio',
    opciones: [['activo', 'Activo'], ['reunida', 'Reunida 🎉'], ['cerrado', 'Cerrado']] },
  { campo: 'especie', label: 'Especie', tipo: 'select', ancho: 'medio', obligatorio: true,
    opciones: [['perro', '🐶 Perro'], ['gato', '🐱 Gato'], ['otra', '🐾 Otra']] },
  { campo: 'especie_otra', label: 'Qué animal es', ancho: 'medio',
    ayuda: 'Solo si la especie es "otra": conejo, loro…' },
  { campo: 'nombre', label: 'Nombre', ancho: 'medio' },
  { campo: 'raza', label: 'Raza', ancho: 'medio' },
  { campo: 'color', label: 'Color', ancho: 'medio' },
  { campo: 'tamano', label: 'Tamaño', tipo: 'select', ancho: 'medio',
    opciones: [['', 'Sin dato'], ['pequeño', 'Pequeño'], ['mediano', 'Mediano'], ['grande', 'Grande']] },
  { campo: 'sexo', label: 'Sexo', tipo: 'select', ancho: 'medio',
    opciones: [['', 'Sin dato'], ['macho', 'Macho'], ['hembra', 'Hembra'], ['desconocido', 'Desconocido']] },
  { campo: 'edad', label: 'Edad', ancho: 'medio', ayuda: '"2 años", "cachorro"…' },
  { campo: 'senas', label: 'Señas particulares y comentarios', tipo: 'area', ancho: 'full',
    ayuda: 'Collar y su color, manchas y dónde, cicatrices, si cojea…' },
  { campo: 'ubicacion', label: 'Ubicación', ancho: 'full', obligatorio: true,
    ayuda: 'Dónde se perdió, dónde se encontró o dónde está ahora la mascota' },
  { campo: 'barrio', label: 'Barrio o zona', ancho: 'medio' },
  { campo: 'fecha_evento', label: 'Fecha del hecho', tipo: 'fecha', ancho: 'medio' },
  { campo: 'maps_url', label: 'Enlace de Google Maps', ancho: 'full' },
  { campo: 'contacto_telefono', label: 'Teléfono de contacto', ancho: 'medio', obligatorio: true,
    ayuda: 'A quién llamar por esta mascota' },
  { campo: 'contacto_nombre', label: 'Nombre de contacto', ancho: 'medio' },
  { campo: 'notas', label: 'Notas internas', tipo: 'area', ancho: 'full' },
];

/**
 * Formulario de edición de un reporte. El equipo corrige lo que el bot
 * entendió mal y completa lo que faltó — y de paso deja limpiar los datos de
 * prueba antes de abrir al público.
 */
function FormularioEdicion({
  reporte,
  onGuardar,
  onCerrar,
  onEliminar,
}: {
  reporte: Reporte;
  onGuardar: (cambios: Record<string, string>) => Promise<void>;
  onCerrar: () => void;
  onEliminar: () => void;
}) {
  const [valores, setValores] = useState<Record<string, string>>(() => {
    const inicial: Record<string, string> = {};
    CAMPOS_FORM.forEach(({ campo }) => {
      const v = reporte[campo];
      inicial[campo] = v === null || v === undefined ? '' : String(v);
    });
    return inicial;
  });
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState<string | null>(null);

  // En los reportes importados de otra plataforma el teléfono no existe: el
  // contacto se resuelve con el enlace a su ficha original.
  const esImportado = Boolean(reporte.origen_url);
  const faltantes = CAMPOS_FORM.filter(
    (c) =>
      c.obligatorio &&
      !(esImportado && c.campo === 'contacto_telefono') &&
      !valores[c.campo]?.trim()
  );

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (faltantes.length > 0) {
      setErrorForm(`Falta ${faltantes.map((c) => c.label.toLowerCase()).join(' y ')}.`);
      return;
    }
    setGuardando(true);
    setErrorForm(null);
    try {
      await onGuardar(valores);
    } catch (err) {
      setErrorForm(err instanceof Error ? err.message : 'No se pudo guardar');
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-label={`Editar ${reporte.codigo}`}
      className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto"
      style={{ backgroundColor: 'rgba(0,0,0,0.5)' }}
      onClick={onCerrar}
    >
      <form
        onSubmit={enviar}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl w-full max-w-2xl my-8 p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-gray-800">
              Editar {reporte.codigo}{' '}
              <span className="text-sm font-normal text-gray-400">
                · {reporte.fotos.length} foto{reporte.fotos.length === 1 ? '' : 's'}
              </span>
            </h2>
            {esImportado && (
              <p className="text-xs text-gray-500 mt-0.5">
                Importado de{' '}
                <a
                  href={reporte.origen_url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                  style={{ color: '#008069' }}
                >
                  {reporte.origen_nombre} ↗
                </a>{' '}
                · el contacto vive en su ficha original
              </p>
            )}
          </div>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="text-xl text-gray-400">
            ✕
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {CAMPOS_FORM.map((c) => (
            <div key={c.campo} className={c.ancho === 'full' ? 'col-span-2' : 'col-span-2 sm:col-span-1'}>
              <label className="block text-xs font-semibold text-gray-600 mb-1">
                {c.label}
                {c.obligatorio && !(esImportado && c.campo === 'contacto_telefono') && (
                  <span style={{ color: '#B91C1C' }}> *</span>
                )}
              </label>
              {c.tipo === 'select' ? (
                <select
                  value={valores[c.campo]}
                  onChange={(e) => setValores((v) => ({ ...v, [c.campo]: e.target.value }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border bg-white"
                  style={{ borderColor: '#D1D5DB' }}
                >
                  {c.opciones?.map(([valor, label]) => (
                    <option key={valor} value={valor}>
                      {label}
                    </option>
                  ))}
                </select>
              ) : c.tipo === 'area' ? (
                <textarea
                  value={valores[c.campo]}
                  onChange={(e) => setValores((v) => ({ ...v, [c.campo]: e.target.value }))}
                  rows={2}
                  className="w-full px-3 py-2 text-sm rounded-lg border"
                  style={{ borderColor: '#D1D5DB' }}
                />
              ) : (
                <input
                  type={c.tipo === 'fecha' ? 'date' : 'text'}
                  value={valores[c.campo]}
                  onChange={(e) => setValores((v) => ({ ...v, [c.campo]: e.target.value }))}
                  className="w-full px-3 py-2 text-sm rounded-lg border"
                  style={{ borderColor: '#D1D5DB' }}
                />
              )}
              {c.ayuda && <p className="text-[11px] text-gray-400 mt-0.5">{c.ayuda}</p>}
            </div>
          ))}
        </div>

        {errorForm && (
          <p className="mt-3 text-sm px-3 py-2 rounded-lg" style={{ backgroundColor: '#FDECEA', color: '#8A1C12' }}>
            {errorForm}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2 mt-5 pt-4 border-t border-gray-100">
          <button
            type="submit"
            disabled={guardando}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-50"
            style={{ backgroundColor: '#008069' }}
          >
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
          <button
            type="button"
            onClick={onCerrar}
            className="px-4 py-2 rounded-lg text-sm font-semibold border"
            style={{ borderColor: '#D1D5DB', color: '#374151' }}
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onEliminar}
            className="px-4 py-2 rounded-lg text-sm font-semibold ml-auto"
            style={{ backgroundColor: '#FEE2E2', color: '#991B1B' }}
          >
            🗑 Eliminar reporte
          </button>
        </div>
      </form>
    </div>
  );
}

export default function MascotasPanel() {
  const [permitido, setPermitido] = useState<boolean | null>(null);
  const [data, setData] = useState<PanelResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [seccion, setSeccion] = useState<Seccion>('coincidencias');
  const [filtroEstado, setFiltroEstado] = useState<string>('');
  const [cruzando, setCruzando] = useState(false);
  // Las coincidencias descartadas se archivan: siguen guardadas (el cruce las
  // respeta y no las vuelve a proponer), pero no estorban la revisión diaria.
  const [verDescartadas, setVerDescartadas] = useState(false);
  const [sync, setSync] = useState<Sync | null>(null);
  // Filtros por campo: el equipo busca "los perros negros de Meléndez", no una
  // fila puntual, así que se combinan entre sí y con el filtro de estado.
  const [busqueda, setBusqueda] = useState('');
  const [filtroEspecie, setFiltroEspecie] = useState('');
  const [filtroBarrio, setFiltroBarrio] = useState('');
  const [filtroConFoto, setFiltroConFoto] = useState(false);
  const [visor, setVisor] = useState<{ reporte: Reporte; indice: number } | null>(null);
  const [editando, setEditando] = useState<Reporte | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const res = await authedFetch<PanelResponse>('/mascotas/panel');
      setData(res);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No pudimos cargar el panel');
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    let cancelado = false;
    authedFetch<{ allowed: boolean }>('/mascotas/access')
      .then((r) => {
        if (cancelado) return;
        setPermitido(Boolean(r?.allowed));
        if (r?.allowed) void cargar();
        else setCargando(false);
      })
      .catch(() => {
        if (!cancelado) {
          setPermitido(false);
          setCargando(false);
        }
      });
    return () => {
      cancelado = true;
    };
  }, [cargar]);

  const actualizarReporte = async (codigo: string, cambios: Record<string, unknown>) => {
    try {
      await authedFetch(`/mascotas/panel/${codigo}`, {
        method: 'PATCH',
        body: JSON.stringify(cambios),
      });
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el cambio');
    }
  };

  const guardarEdicion = async (codigo: string, cambios: Record<string, string>) => {
    await authedFetch(`/mascotas/panel/${codigo}`, {
      method: 'PATCH',
      body: JSON.stringify(cambios),
    });
    setEditando(null);
    await cargar();
  };

  const eliminarReporte = async (r: Reporte) => {
    const etiqueta = r.nombre ? `${r.nombre} (${r.codigo})` : r.codigo;
    if (!window.confirm(`¿Eliminar el reporte de ${etiqueta}? Se borran también sus fotos. Esto no se puede deshacer.`)) {
      return;
    }
    try {
      await authedFetch(`/mascotas/panel/${r.codigo}`, { method: 'DELETE' });
      setEditando(null);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el reporte');
    }
  };

  const eliminarFoto = async (r: Reporte, fotoId: number) => {
    if (!window.confirm('¿Eliminar esta foto? No se puede deshacer.')) return;
    try {
      await authedFetch(`/mascotas/panel/${r.codigo}/fotos/${fotoId}`, { method: 'DELETE' });
      setVisor(null);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar la foto');
    }
  };

  /** Deja la base sin datos de prueba, sin tocar los reportes reales. */
  const purgarDemo = async () => {
    if (!window.confirm(
      'Se borrarán TODOS los reportes de prueba (los marcados como 🧪 Demo) con sus fotos.\n\n' +
      'Los reportes que entraron por el chat NO se tocan. ¿Continuar?'
    )) {
      return;
    }
    try {
      const res = await authedFetch<{ eliminados: number }>('/mascotas/panel/purgar/demo', {
        method: 'DELETE',
      });
      setError(null);
      await cargar();
      window.alert(`Listo: ${res.eliminados} reporte(s) de prueba eliminados.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron borrar los datos de prueba');
    }
  };

  const actualizarCoincidencia = async (id: number, estado: string) => {
    try {
      await authedFetch(`/mascotas/panel/coincidencias/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ estado }),
      });
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el cambio');
    }
  };

  /**
   * Trae los reportes nuevos de las plataformas hermanas. Corre en el servidor
   * en segundo plano (recorrer cientos de fichas toma minutos), así que aquí
   * solo se dispara y se consulta el avance hasta que termina.
   */
  const sincronizar = async () => {
    try {
      const inicial = await authedFetch<Sync>('/mascotas/panel/sincronizar', {
        method: 'POST',
      });
      setSync(inicial);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo iniciar la sincronización');
    }
  };

  // Consulta el avance mientras la importación esté corriendo.
  useEffect(() => {
    if (sync?.estado !== 'corriendo') return;
    const id = setInterval(async () => {
      try {
        const estado = await authedFetch<Sync>('/mascotas/panel/sincronizacion');
        setSync(estado);
        if (estado.estado !== 'corriendo') {
          clearInterval(id);
          await cargar();
        }
      } catch {
        clearInterval(id);
      }
    }, 3000);
    return () => clearInterval(id);
  }, [sync?.estado, cargar]);

  const cruzarAhora = async () => {
    setCruzando(true);
    try {
      await authedFetch('/mascotas/panel/cruzar', { method: 'POST' });
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo ejecutar el cruce');
    } finally {
      setCruzando(false);
    }
  };

  /** Coincidencias a la vista: las descartadas quedan archivadas por defecto. */
  const coincidencias = useMemo(
    () =>
      (data?.coincidencias || []).filter(
        (c) => verDescartadas || c.estado !== 'descartada'
      ),
    [data, verDescartadas]
  );

  const descartadas = useMemo(
    () => (data?.coincidencias || []).filter((c) => c.estado === 'descartada').length,
    [data]
  );

  /** ¿Queda algún reporte de prueba? El botón de purga solo aparece si sí. */
  const hayDemo = useMemo(
    () => (data?.reportes || []).some((r) => r.source === 'demo'),
    [data]
  );

  /** Zonas presentes en los datos, para ofrecerlas como filtro. */
  const barrios = useMemo(() => {
    const set = new Set<string>();
    (data?.reportes || []).forEach((r) => {
      if (r.barrio) set.add(r.barrio);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'es'));
  }, [data]);

  const reportes = useMemo(() => {
    if (!data || seccion === 'coincidencias') return [];
    const texto = busqueda.trim().toLowerCase();
    return data.reportes.filter((r) => {
      if (r.tipo_registro !== seccion) return false;
      if (filtroEstado && r.estado !== filtroEstado) return false;
      if (filtroEspecie && r.especie !== filtroEspecie) return false;
      if (filtroBarrio && r.barrio !== filtroBarrio) return false;
      if (filtroConFoto && r.fotos.length === 0) return false;
      if (texto) {
        // Búsqueda libre sobre todo lo que alguien podría recordar de un caso.
        const blob = [
          r.codigo, r.nombre, r.raza, r.color, r.senas, r.notas, r.ubicacion,
          r.barrio, r.contacto_nombre, r.contacto_telefono, r.especie,
          r.especie_otra, r.tamano, r.sexo, r.edad,
        ]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!blob.includes(texto)) return false;
      }
      return true;
    });
  }, [data, seccion, filtroEstado, filtroEspecie, filtroBarrio, filtroConFoto, busqueda]);

  const filtrosActivos =
    Boolean(busqueda || filtroEspecie || filtroBarrio || filtroConFoto || filtroEstado);

  const limpiarFiltros = () => {
    setBusqueda('');
    setFiltroEspecie('');
    setFiltroBarrio('');
    setFiltroConFoto(false);
    setFiltroEstado('');
  };

  if (cargando && permitido === null) {
    return (
      <Layout variant="fullscreen">
        <div className="flex-1 flex items-center justify-center text-gray-500">
          Cargando…
        </div>
      </Layout>
    );
  }

  if (permitido === false) {
    return (
      <Layout variant="fullscreen">
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-600">
          <span className="text-4xl">🐾</span>
          <p className="font-semibold">Este módulo no está disponible en tu cuenta</p>
        </div>
      </Layout>
    );
  }

  const resumen = data?.resumen;

  return (
    <Layout variant="fullscreen">
      <div className="flex-1 overflow-y-auto p-6 lg:p-8" style={{ backgroundColor: '#FAFAF8' }}>
        {/* ===== Encabezado ===== */}
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">
              🐾 Recupera Tu Mascota
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Reportes del bot de{' '}
              <a
                href="https://mascotasperdidascali.glomabeauty.com"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
                style={{ color: '#008069' }}
              >
                mascotasperdidascali.glomabeauty.com
              </a>{' '}
              · iniciativa por los afectados del terremoto en Colombia
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={sincronizar}
              disabled={sync?.estado === 'corriendo'}
              className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-50"
              style={{ backgroundColor: '#008069' }}
              title="Trae los reportes nuevos de Mascotas por Colombia"
            >
              {sync?.estado === 'corriendo' ? 'Sincronizando…' : '🔄 Sincronizar lista'}
            </button>
            <button
              type="button"
              onClick={cruzarAhora}
              disabled={cruzando}
              className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-50"
              style={{ backgroundColor: '#004D40' }}
              title="El cruce corre solo todos los días a las 12:00"
            >
              {cruzando ? 'Cruzando…' : '🔗 Cruzar ahora'}
            </button>
            <a
              href="/api/mascotas/panel/export.xlsx"
              className="px-4 py-2 rounded-lg text-sm font-semibold border transition-colors hover:bg-gray-50"
              style={{ borderColor: '#D1D5DB', color: '#374151' }}
            >
              📊 Excel
            </a>
            {/* Paquete para compartir con otra plataforma: casos + fotos. Sin
                teléfonos — son datos de ciudadanos, no material de reparto. */}
            <a
              href="/api/mascotas/panel/export.zip"
              className="px-4 py-2 rounded-lg text-sm font-semibold border transition-colors hover:bg-gray-50"
              style={{ borderColor: '#D1D5DB', color: '#374151' }}
              title="casos.json + fotos, para enviarle a una app amiga (sin teléfonos)"
            >
              📦 ZIP para app amiga
            </a>
            <a
              href="/api/mascotas/panel/export.json"
              className="px-4 py-2 rounded-lg text-sm font-semibold border transition-colors hover:bg-gray-50"
              style={{ borderColor: '#D1D5DB', color: '#374151' }}
              title="Solo los datos, sin fotos ni teléfonos"
            >
              🧾 JSON
            </a>
            {hayDemo && (
              <button
                type="button"
                onClick={purgarDemo}
                className="px-4 py-2 rounded-lg text-sm font-semibold transition-opacity hover:opacity-80"
                style={{ backgroundColor: '#FEE2E2', color: '#991B1B' }}
                title="Borra los reportes de prueba sin tocar los reales"
              >
                🧪 Borrar datos de prueba
              </button>
            )}
          </div>
        </div>

        {error && (
          <p className="my-3 text-sm px-4 py-2 rounded-lg" style={{ backgroundColor: '#FDECEA', color: '#8A1C12' }}>
            {error}
          </p>
        )}

        {sync && sync.estado !== 'idle' && (
          <p
            className="my-3 text-sm px-4 py-2 rounded-lg"
            style={
              sync.estado === 'error'
                ? { backgroundColor: '#FDECEA', color: '#8A1C12' }
                : { backgroundColor: '#E0F2F1', color: '#004D40' }
            }
          >
            {sync.estado === 'corriendo' && (
              <>
                🔄 Trayendo reportes de Mascotas por Colombia…{' '}
                {sync.contadores.vistas
                  ? `${sync.contadores.vistas} fichas revisadas, ${sync.contadores.creadas ?? 0} nuevas`
                  : 'leyendo el listado del sitio'}
              </>
            )}
            {sync.estado === 'ok' && (
              <>
                ✅ Sincronización lista: {sync.contadores.creadas ?? 0} reportes nuevos,{' '}
                {sync.contadores.actualizadas ?? 0} actualizados
                {sync.contadores.fallidas ? `, ${sync.contadores.fallidas} con error` : ''}.
              </>
            )}
            {sync.estado === 'error' && <>⚠️ {sync.mensaje}</>}
          </p>
        )}

        {/* ===== Contadores ===== */}
        {resumen && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 my-5">
            <Tarjeta titulo="Reportes totales" valor={resumen.total} tono="#111827" />
            <Tarjeta titulo="Se están buscando" valor={resumen.perdidas} tono="#92400E" />
            <Tarjeta titulo="Fueron encontradas" valor={resumen.encontradas} tono="#1E40AF" />
            <Tarjeta titulo="Reunidas 🎉" valor={resumen.reunidas} tono="#166534" />
            <Tarjeta
              titulo="Coincidencias sin revisar"
              valor={data?.coincidencias_nuevas ?? 0}
              tono="#B45309"
            />
            <Tarjeta titulo="Fotos guardadas" valor={resumen.fotos} tono="#6B21A8" />
          </div>
        )}

        {/* ===== Pestañas ===== */}
        <div className="flex flex-wrap gap-2 mb-4 border-b border-gray-200 pb-3">
          {([
            ['coincidencias', `🔗 Coincidencias (${coincidencias.length})`],
            ['perdida', `🔎 Se buscan (${resumen?.perdidas ?? 0})`],
            ['encontrada', `🐾 Encontradas (${resumen?.encontradas ?? 0})`],
          ] as [Seccion, string][]).map(([valor, label]) => (
            <button
              key={valor}
              type="button"
              onClick={() => setSeccion(valor)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                seccion === valor ? 'text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
              style={seccion === valor ? { backgroundColor: '#008069' } : undefined}
            >
              {label}
            </button>
          ))}
        </div>

        {/* ===== Coincidencias ===== */}
        {seccion === 'coincidencias' && (
          <>
            <p className="text-sm text-gray-500 mb-3">
              El sistema compara todos los días a las 12:00 cada mascota que se busca
              contra cada mascota encontrada. Estos son los pares que más se parecen:
              revísalos y llama a las dos personas si cuadran.
            </p>

            {descartadas > 0 && (
              <div className="flex items-center gap-2 mb-4">
                <button
                  type="button"
                  onClick={() => setVerDescartadas((v) => !v)}
                  className="px-3 py-1.5 rounded-full text-xs font-medium border transition-colors hover:bg-gray-50"
                  style={{ borderColor: '#D1D5DB', color: '#6B7280' }}
                >
                  {verDescartadas
                    ? '🙈 Ocultar descartadas'
                    : `📁 Ver ${descartadas} descartada${descartadas > 1 ? 's' : ''}`}
                </button>
                <span className="text-xs text-gray-400">
                  Las que marcas como “no es” quedan archivadas y el cruce diario no
                  las vuelve a proponer.
                </span>
              </div>
            )}

            {coincidencias.length === 0 && (
              <p className="text-sm text-gray-400 py-8 text-center">
                {descartadas > 0
                  ? 'No quedan coincidencias por revisar. 🎉'
                  : 'Todavía no hay coincidencias. Aparecerán aquí en cuanto un reporte nuevo se parezca a uno existente.'}
              </p>
            )}
            <div className="flex flex-col gap-3">
              {coincidencias.map((c) => (
                <div
                  key={c.id}
                  className="rounded-xl border bg-white p-4"
                  style={{ borderColor: c.estado === 'nueva' ? '#93C5FD' : '#E5E7EB' }}
                >
                  <div className="flex flex-wrap items-center gap-2 mb-3">
                    <Badge estado={c.estado} styles={MATCH_STYLE} />
                    <span
                      className="text-xs font-semibold px-2 py-1 rounded-full"
                      style={{ backgroundColor: '#F3F4F6', color: '#374151' }}
                      title="Puntaje de parecido calculado por el sistema"
                    >
                      {c.score} puntos de parecido
                    </span>
                    <span className="text-xs text-gray-500">
                      coinciden:{' '}
                      {Object.keys(c.detalle)
                        .map((k) => CAMPO_LABEL[k] || k)
                        .join(', ')}
                    </span>
                    <span className="text-xs text-gray-400 ml-auto">
                      detectada el {fechaCorta(c.created_at)}
                    </span>
                  </div>

                  <div className="grid md:grid-cols-2 gap-4">
                    {([
                      ['La están buscando', c.perdida, '#92400E'],
                      ['La encontraron', c.encontrada, '#1E40AF'],
                    ] as [string, Reporte, string][]).map(([titulo, r, tono]) => (
                      <div key={r.codigo} className="flex gap-3">
                        <button
                          type="button"
                          onClick={() => r.fotos.length && setVisor({ reporte: r, indice: 0 })}
                          className="shrink-0"
                          title={r.fotos.length ? 'Ampliar foto' : 'Sin fotos'}
                        >
                          <Miniatura reporte={r} size={72} />
                        </button>
                        <div className="min-w-0 text-sm">
                          <div className="text-xs font-bold uppercase tracking-wide" style={{ color: tono }}>
                            {titulo}
                          </div>
                          <div className="font-semibold text-gray-800">
                            {r.nombre || descripcion(r)}{' '}
                            <span className="text-gray-400 font-normal">{r.codigo}</span>
                          </div>
                          {r.nombre && <div className="text-gray-600">{descripcion(r)}</div>}
                          {r.senas && <div className="text-gray-500 text-xs mt-0.5">{r.senas}</div>}
                          <div className="text-gray-600 mt-1">📍 {r.ubicacion}</div>
                          {r.contacto_telefono ? (
                            <div className="text-gray-800 font-medium mt-0.5">
                              📞 {r.contacto_telefono}
                              {r.contacto_nombre ? ` · ${r.contacto_nombre}` : ''}
                            </div>
                          ) : r.origen_url ? (
                            <a
                              href={r.origen_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block mt-0.5 underline font-medium"
                              style={{ color: '#008069' }}
                            >
                              🤝 Ficha en {r.origen_nombre} ↗
                            </a>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-gray-100">
                    {([
                      ['confirmada', '🎉 Es la misma'],
                      ['revisada', '👀 Ya la revisé'],
                      ['descartada', '✕ No es'],
                    ] as [string, string][]).map(([estado, label]) => (
                      <button
                        key={estado}
                        type="button"
                        onClick={() => void actualizarCoincidencia(c.id, estado)}
                        disabled={c.estado === estado}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors hover:bg-gray-50 disabled:opacity-40"
                        style={{ borderColor: '#D1D5DB', color: '#374151' }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ===== Tablas de reportes ===== */}
        {seccion !== 'coincidencias' && (
          <>
            {/* ===== Filtros ===== */}
            <div className="rounded-xl border bg-white p-3 mb-4" style={{ borderColor: '#E5E7EB' }}>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                  placeholder="Buscar por código, nombre, raza, color, señas, teléfono…"
                  aria-label="Buscar en los reportes"
                  className="flex-1 min-w-[240px] px-3 py-2 text-sm rounded-lg border focus:outline-none"
                  style={{ borderColor: '#D1D5DB' }}
                />
                <select
                  value={filtroEspecie}
                  onChange={(e) => setFiltroEspecie(e.target.value)}
                  aria-label="Filtrar por especie"
                  className="px-3 py-2 text-sm rounded-lg border bg-white"
                  style={{ borderColor: '#D1D5DB' }}
                >
                  <option value="">Todas las especies</option>
                  <option value="perro">🐶 Perros</option>
                  <option value="gato">🐱 Gatos</option>
                  <option value="otra">🐾 Otras</option>
                </select>
                <select
                  value={filtroBarrio}
                  onChange={(e) => setFiltroBarrio(e.target.value)}
                  aria-label="Filtrar por zona"
                  className="px-3 py-2 text-sm rounded-lg border bg-white"
                  style={{ borderColor: '#D1D5DB' }}
                >
                  <option value="">Todas las zonas</option>
                  {barrios.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
                <select
                  value={filtroEstado}
                  onChange={(e) => setFiltroEstado(e.target.value)}
                  aria-label="Filtrar por estado"
                  className="px-3 py-2 text-sm rounded-lg border bg-white"
                  style={{ borderColor: '#D1D5DB' }}
                >
                  <option value="">Todos los estados</option>
                  <option value="activo">Activos</option>
                  <option value="reunida">Reunidas 🎉</option>
                  <option value="cerrado">Cerrados</option>
                </select>
                <label className="flex items-center gap-1.5 text-sm text-gray-600 px-2">
                  <input
                    type="checkbox"
                    checked={filtroConFoto}
                    onChange={(e) => setFiltroConFoto(e.target.checked)}
                  />
                  Solo con foto
                </label>
                {filtrosActivos && (
                  <button
                    type="button"
                    onClick={limpiarFiltros}
                    className="text-xs underline text-gray-500 px-2"
                  >
                    Limpiar filtros
                  </button>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-2">
                {reportes.length}{' '}
                {reportes.length === 1 ? 'reporte' : 'reportes'}
                {filtrosActivos ? ' con los filtros aplicados' : ' en total'}
              </p>
            </div>

            <div className="overflow-x-auto rounded-xl border bg-white" style={{ borderColor: '#E5E7EB' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-gray-500 border-b" style={{ borderColor: '#E5E7EB' }}>
                    <th className="px-4 py-3">Fotos</th>
                    <th className="px-4 py-3">Código</th>
                    <th className="px-4 py-3">Mascota</th>
                    <th className="px-4 py-3">Señas y comentarios</th>
                    <th className="px-4 py-3">Ubicación</th>
                    <th className="px-4 py-3">Contacto</th>
                    <th className="px-4 py-3">Origen</th>
                    <th className="px-4 py-3">Estado</th>
                    <th className="px-4 py-3">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {reportes.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-10 text-center text-gray-400">
                        {filtrosActivos
                          ? 'Ningún reporte coincide con los filtros.'
                          : 'No hay reportes en esta vista.'}
                      </td>
                    </tr>
                  )}
                  {reportes.map((r) => (
                    <tr key={r.id} className="border-b last:border-0" style={{ borderColor: '#F3F4F6' }}>
                      <td className="px-4 py-3">
                        <CeldaFotos
                          reporte={r}
                          onAmpliar={() => setVisor({ reporte: r, indice: 0 })}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-mono text-xs font-semibold text-gray-700">{r.codigo}</div>
                        <div className="text-xs text-gray-400 mt-0.5">{fechaCorta(r.created_at)}</div>
                        <div className="text-xs text-gray-400">
                          {r.fotos.length === 0
                            ? 'sin fotos'
                            : `${r.fotos.length} foto${r.fotos.length > 1 ? 's' : ''}`}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-semibold text-gray-800">
                          {ESPECIE_EMOJI[r.especie] || '🐾'} {r.nombre || 'Sin nombre'}
                        </div>
                        <div className="text-gray-600 text-xs">{descripcion(r)}</div>
                        {r.fecha_evento && (
                          <div className="text-gray-400 text-xs mt-0.5">
                            {r.tipo_registro === 'perdida' ? 'perdida' : 'hallada'} el {r.fecha_evento}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-600 text-xs max-w-xs">
                        {r.senas || <span className="text-gray-300">—</span>}
                        {r.notas && <div className="text-gray-400 mt-1">{r.notas}</div>}
                      </td>
                      <td className="px-4 py-3 text-gray-600 text-xs max-w-xs">
                        {r.ubicacion}
                        {r.barrio && <div className="text-gray-400">{r.barrio}</div>}
                        {r.maps_url && (
                          <a
                            href={r.maps_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline"
                            style={{ color: '#008069' }}
                          >
                            Ver en Maps
                          </a>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs">
                        {r.contacto_telefono ? (
                          <>
                            <div className="font-semibold text-gray-800">{r.contacto_telefono}</div>
                            {r.contacto_nombre && <div className="text-gray-500">{r.contacto_nombre}</div>}
                          </>
                        ) : r.origen_url ? (
                          <>
                            <a
                              href={r.origen_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-semibold underline"
                              style={{ color: '#008069' }}
                            >
                              Ver ficha original ↗
                            </a>
                            <div className="text-gray-400">{r.origen_nombre}</div>
                          </>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                        {SOURCE_LABEL[r.source] || r.source}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={r.estado}
                          onChange={(e) => void actualizarReporte(r.codigo, { estado: e.target.value })}
                          className="text-xs rounded-lg border px-2 py-1.5 bg-white"
                          style={{ borderColor: '#D1D5DB' }}
                          aria-label={`Estado de ${r.codigo}`}
                        >
                          <option value="activo">Activo</option>
                          <option value="reunida">Reunida 🎉</option>
                          <option value="cerrado">Cerrado</option>
                        </select>
                        <div className="mt-1">
                          <Badge estado={r.estado} styles={ESTADO_STYLE} />
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <button
                            type="button"
                            onClick={() => setEditando(r)}
                            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors hover:bg-gray-50 whitespace-nowrap"
                            style={{ borderColor: '#D1D5DB', color: '#374151' }}
                          >
                            ✏️ Editar
                          </button>
                          <button
                            type="button"
                            onClick={() => void eliminarReporte(r)}
                            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-opacity hover:opacity-80 whitespace-nowrap"
                            style={{ backgroundColor: '#FEE2E2', color: '#991B1B' }}
                          >
                            🗑 Eliminar
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {editando && (
          <FormularioEdicion
            reporte={editando}
            onGuardar={(cambios) => guardarEdicion(editando.codigo, cambios)}
            onCerrar={() => setEditando(null)}
            onEliminar={() => void eliminarReporte(editando)}
          />
        )}

        {visor && (
          <Visor
            reporte={visor.reporte}
            indice={visor.indice}
            onCerrar={() => setVisor(null)}
            onMover={(delta) =>
              setVisor((v) => {
                if (!v) return v;
                const total = v.reporte.fotos.length;
                return { ...v, indice: (v.indice + delta + total) % total };
              })
            }
            onEliminarFoto={(fotoId) => void eliminarFoto(visor.reporte, fotoId)}
          />
        )}
      </div>
    </Layout>
  );
}
