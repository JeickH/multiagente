import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/router';
import Layout from '../components/Layout';
import TutorialOverlay from '../components/TutorialOverlay';
import { ApiError, authedFetch } from '../lib/api';
import { aInstante } from '../lib/fechas';
import { getToken } from '../lib/session';

const BOTS_TUTORIAL = [
  {
    selector: '[data-tour="bots-table"]',
    title: 'Visualiza tus bots',
    body: 'En esta tabla aparecen todos los bots configurados para tu cuenta: nombre, estado y cuántas veces se han disparado. Haz click en el nombre para abrir el diseñador y el simulador del bot.',
  },
  {
    selector: '[data-tour="trigger-column"]',
    title: 'Reglas que activan el bot',
    body: 'La columna "Activación" muestra cómo se dispara cada bot:\n⭐ por defecto · 🔑 por palabra clave · 🔗 manual. Esta es la regla que decide cuándo Gloma le pasa la conversación al bot.',
  },
  {
    selector: '[data-tour="bot-link"]',
    title: 'Probar el bot en el popup',
    body: 'Haz click en el nombre del bot para abrir el detalle. Adentro encontrarás el botón "Probar Chatbot" que abre un popup tipo WhatsApp y te deja simular la conversación sin tocar Meta real.',
  },
];

type BotListItem = {
  id: number;
  name: string;
  status: string;
  channels: string[];
  engine?: 'flow' | 'llm';
  trigger_type: 'default' | 'keyword' | 'manual';
  trigger_config: Record<string, any> | null;
  triggered_count: number;
  completed_steps_count: number;
  finished_count: number;
  created_at: string;
  updated_at: string;
  /** % de las conversaciones nuevas que recibe este bot; `null` = sin reparto. */
  reparto_pct?: number | null;
  /** Conversaciones asignadas a este bot desde que se guardó el reparto vigente. */
  conversaciones_reparto?: number;
};

/** Lo que devuelve `/teams/me`; acá solo importa el rol del miembro. */
type TeamMe = { member: { role: string } };

const MSG_SOLO_DUENO = 'Solo el dueño de la cuenta puede cambiar esto.';

/** Mensaje para el usuario a partir de un error de `authedFetch`. */
function mensajeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return MSG_SOLO_DUENO;
    return err.message || fallback;
  }
  return fallback;
}

/** Solo los bots por defecto y activos entran al reparto (regla del backend). */
const esRepartible = (b: BotListItem) => b.trigger_type === 'default' && b.status === 'active';

function relativeTime(iso: string): string {
  // El backend manda UTC sin zona: `aInstante` le pone la Z que falta.
  const then = aInstante(iso);
  if (!then) return '—';
  const diffMs = Date.now() - then.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'hace segundos';
  if (diffMin < 60) return `${diffMin} min hace`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} h hace`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 30) return `${diffD} d hace`;
  const diffMo = Math.floor(diffD / 30);
  if (diffMo < 12) return `${diffMo} mes${diffMo === 1 ? '' : 'es'} hace`;
  const diffY = Math.floor(diffMo / 12);
  return `${diffY} año${diffY === 1 ? '' : 's'} hace`;
}

function EngineBadge({ bot }: { bot: BotListItem }) {
  if (bot.engine !== 'llm') return null;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200">
      <span>🤖</span> IA
    </span>
  );
}

function TriggerBadge({ bot }: { bot: BotListItem }) {
  if (bot.trigger_type === 'default') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gloma-rose-soft/30 text-gloma-brown border border-gloma-rose-soft">
        <span>⭐</span> Default
      </span>
    );
  }
  if (bot.trigger_type === 'keyword') {
    const keywords: string[] = bot.trigger_config?.keywords || [];
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
        <span>🔑</span>
        {keywords.length > 0 ? keywords.join(', ') : 'Keyword'}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-50 text-gray-600 border border-gray-200">
      <span>🔗</span> Manual
    </span>
  );
}

function RepartoCell({ bot }: { bot: BotListItem }) {
  if (!esRepartible(bot)) {
    return <span className="text-gray-300">—</span>;
  }
  const pct = bot.reparto_pct;
  const conteo = bot.conversaciones_reparto ?? 0;
  return (
    <div>
      {pct == null ? (
        <span className="text-gray-400">—</span>
      ) : (
        <span className="font-semibold text-gloma-forest">{pct} %</span>
      )}
      {pct != null && (
        <div className="text-[11px] text-gray-400">
          {conteo} conversaci{conteo === 1 ? 'ón' : 'ones'}
        </div>
      )}
    </div>
  );
}

/** Reparte 100 en `n` enteros lo más parejos posible (33/33/34 → 34/33/33). */
function partesIguales(n: number): number[] {
  if (n <= 0) return [];
  const base = Math.floor(100 / n);
  const sobra = 100 - base * n;
  return Array.from({ length: n }, (_, i) => base + (i < sobra ? 1 : 0));
}

function RepartoPanel({
  elegibles,
  puedeEditar,
  onGuardado,
}: {
  elegibles: BotListItem[];
  puedeEditar: boolean;
  onGuardado: (bots: BotListItem[]) => void;
}) {
  // Valores del formulario como texto para permitir dejar el campo vacío
  // mientras se escribe; se interpretan como enteros al sumar y al guardar.
  const [valores, setValores] = useState<Record<number, string>>({});
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');

  const hayRepartoVigente = elegibles.some((b) => b.reparto_pct != null);

  // Cada vez que llega una lista nueva del backend, el formulario vuelve a
  // reflejar lo guardado.
  useEffect(() => {
    const inicial: Record<number, string> = {};
    for (const b of elegibles) inicial[b.id] = b.reparto_pct != null ? String(b.reparto_pct) : '0';
    setValores(inicial);
  }, [elegibles]);

  const numero = (v: string | undefined) => {
    const n = Number(v);
    return Number.isInteger(n) ? n : NaN;
  };
  const invalido = elegibles.some((b) => {
    const n = numero(valores[b.id]);
    return Number.isNaN(n) || n < 0 || n > 100;
  });
  const total = elegibles.reduce((acc, b) => acc + (numero(valores[b.id]) || 0), 0);
  const totalOk = !invalido && total === 100;
  // Sin reparto guardado y sin tocar nada, el 0 % no es un error: es el estado
  // normal ("atiende el bot más antiguo"). No pintarlo en rojo.
  const neutro = !hayRepartoVigente && !invalido && total === 0;
  const sinCambios = elegibles.every(
    (b) => String(b.reparto_pct ?? 0) === String(numero(valores[b.id])),
  );

  const repartirIgual = () => {
    const partes = partesIguales(elegibles.length);
    const nuevo: Record<number, string> = {};
    elegibles.forEach((b, i) => (nuevo[b.id] = String(partes[i])));
    setValores(nuevo);
    setAviso('');
  };

  const enviar = async (reparto: { bot_id: number; pct: number }[], ok: string) => {
    setGuardando(true);
    setError('');
    setAviso('');
    try {
      const bots = await authedFetch<BotListItem[]>('/bots/reparto', {
        method: 'PUT',
        body: JSON.stringify({ reparto }),
      });
      onGuardado(bots);
      setAviso(ok);
    } catch (err) {
      setError(mensajeError(err, 'No se pudo guardar el reparto. Intenta de nuevo.'));
    } finally {
      setGuardando(false);
    }
  };

  const guardar = () => {
    if (!totalOk) return;
    // Los bots en 0 % no se mandan: sin porcentaje es lo mismo que 0 (no
    // reciben conversaciones nuevas) y así no dependemos de que el backend
    // acepte entradas en cero.
    const reparto = elegibles
      .map((b) => ({ bot_id: b.id, pct: numero(valores[b.id]) }))
      .filter((r) => r.pct > 0);
    enviar(reparto, 'Reparto guardado. Aplica desde la próxima conversación nueva.');
  };

  const quitar = () => {
    if (
      !window.confirm(
        '¿Quitar el reparto? Las conversaciones nuevas volverán todas al bot por defecto más antiguo.',
      )
    )
      return;
    enviar([], 'Reparto quitado. Las conversaciones nuevas vuelven al bot por defecto más antiguo.');
  };

  return (
    <section className="bg-white rounded-lg border border-gray-200 p-5 mb-6">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
        <div>
          <h2 className="text-base font-semibold text-gray-800">Repartir conversaciones nuevas</h2>
          <p className="text-sm text-gray-500 mt-0.5 max-w-2xl">
            Cada conversación nueva se asigna a un bot según estos porcentajes. Un cliente que
            vuelve sigue con el mismo bot.
          </p>
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded-full border ${
            hayRepartoVigente
              ? 'bg-gloma-soft-mint text-gloma-forest border-gloma-mint/40'
              : 'bg-gray-50 text-gray-500 border-gray-200'
          }`}
        >
          {hayRepartoVigente ? 'Reparto activo' : 'Sin reparto: atiende el bot por defecto más antiguo'}
        </span>
      </div>

      <div className="mt-4 divide-y divide-gray-100 border border-gray-100 rounded-md">
        {elegibles.map((b) => (
          <div key={b.id} className="flex items-center justify-between gap-4 px-3 py-2">
            <div className="min-w-0">
              <div className="text-sm font-medium text-gray-800 truncate">{b.name}</div>
              {b.reparto_pct != null && (
                <div className="text-[11px] text-gray-400">
                  {b.conversaciones_reparto ?? 0} conversaciones con el reparto actual
                </div>
              )}
            </div>
            <label className="flex items-center gap-1.5 shrink-0">
              <span className="sr-only">Porcentaje para {b.name}</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={100}
                step={1}
                value={valores[b.id] ?? ''}
                disabled={!puedeEditar || guardando}
                onChange={(e) => {
                  setValores((prev) => ({ ...prev, [b.id]: e.target.value }));
                  setAviso('');
                }}
                className="w-20 text-right text-sm px-2 py-1 border border-gray-300 rounded-md focus:outline-none focus:border-gloma-mint focus:ring-1 focus:ring-gloma-mint disabled:bg-gray-50 disabled:text-gray-400"
              />
              <span className="text-sm text-gray-500">%</span>
            </label>
          </div>
        ))}
        <div className="flex items-center justify-between px-3 py-2 bg-gray-50">
          <span className="text-sm font-medium text-gray-600">Total</span>
          <span
            className={`text-sm font-semibold pr-6 ${
              totalOk ? 'text-gloma-forest' : neutro ? 'text-gray-500' : 'text-red-600'
            }`}
            aria-live="polite"
          >
            {invalido ? 'Revisa los valores (enteros de 0 a 100)' : `${total} %`}
            {!invalido && !neutro && total !== 100 && (
              <span className="font-normal text-xs ml-2">
                ({total < 100 ? `faltan ${100 - total}` : `sobran ${total - 100}`})
              </span>
            )}
          </span>
        </div>
      </div>

      {error && (
        <div className="mt-3 bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
          {error}
        </div>
      )}
      {aviso && !error && (
        <div className="mt-3 bg-gloma-soft-mint border border-gloma-mint/40 text-gloma-forest px-3 py-2 rounded text-sm">
          {aviso}
        </div>
      )}

      {puedeEditar ? (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={guardar}
            disabled={!totalOk || guardando || sinCambios}
            className="px-4 py-1.5 text-sm bg-gloma-brown text-white rounded-md font-semibold hover:bg-gloma-brown-dark disabled:opacity-50 disabled:cursor-not-allowed"
            title={!totalOk ? 'El total debe sumar 100 %' : undefined}
          >
            {guardando ? 'Guardando…' : 'Guardar reparto'}
          </button>
          <button
            type="button"
            onClick={repartirIgual}
            disabled={guardando}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50"
          >
            Repartir en partes iguales
          </button>
          <button
            type="button"
            onClick={quitar}
            disabled={guardando || !hayRepartoVigente}
            className="px-3 py-1.5 text-sm text-red-600 hover:text-red-700 hover:bg-red-50 rounded-md disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed"
          >
            Quitar reparto
          </button>
        </div>
      ) : (
        <p className="mt-3 text-xs text-gray-500">{MSG_SOLO_DUENO}</p>
      )}
    </section>
  );
}

function DuplicarFila({
  bot,
  onCreado,
  onCancelar,
}: {
  bot: BotListItem;
  onCreado: (nuevoId: number, nombre: string) => Promise<void>;
  onCancelar: () => void;
}) {
  const [nombre, setNombre] = useState('');
  const [creando, setCreando] = useState(false);
  const [error, setError] = useState('');

  const crear = async () => {
    setCreando(true);
    setError('');
    try {
      const limpio = nombre.trim();
      const nuevo = await authedFetch<{ id: number; name: string }>(`/bots/${bot.id}/duplicar`, {
        method: 'POST',
        body: JSON.stringify(limpio ? { name: limpio } : {}),
      });
      await onCreado(nuevo.id, nuevo.name);
    } catch (err) {
      setError(mensajeError(err, 'No se pudo duplicar el bot. Intenta de nuevo.'));
      setCreando(false);
    }
  };

  return (
    <tr className="bg-gloma-cream border-b border-gray-100">
      <td colSpan={6} className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`dup-${bot.id}`} className="text-sm text-gray-700">
            Nombre de la variante <span className="text-gray-400">(opcional)</span>
          </label>
          <input
            id={`dup-${bot.id}`}
            type="text"
            autoFocus
            maxLength={120}
            value={nombre}
            disabled={creando}
            onChange={(e) => setNombre(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') crear();
              if (e.key === 'Escape') onCancelar();
            }}
            placeholder={`${bot.name} (variante)`}
            className="text-sm px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:border-gloma-mint focus:ring-1 focus:ring-gloma-mint w-72"
          />
          <button
            type="button"
            onClick={crear}
            disabled={creando}
            className="px-3 py-1.5 text-sm bg-gloma-brown text-white rounded-md font-semibold hover:bg-gloma-brown-dark disabled:opacity-50"
          >
            {creando ? 'Duplicando…' : 'Crear variante'}
          </button>
          <button
            type="button"
            onClick={onCancelar}
            disabled={creando}
            className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800"
          >
            Cancelar
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-1.5">
          Se copia el guion, los productos y los pasos. La variante queda activa pero sin
          conversaciones hasta que le asignes un porcentaje en el reparto.
        </p>
        {error && (
          <div className="mt-2 bg-red-50 border border-red-200 text-red-700 px-3 py-1.5 rounded text-sm">
            {error}
          </div>
        )}
      </td>
    </tr>
  );
}

export default function BotsPage() {
  const router = useRouter();
  const [bots, setBots] = useState<BotListItem[] | null>(null);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [downloading, setDownloading] = useState(false);
  // `null` = no se pudo saber (p. ej. /teams/me falló): en ese caso se muestran
  // los controles y el backend decide con su 403. Nunca se lee el rol del JWT.
  const [esDueno, setEsDueno] = useState<boolean | null>(null);
  const [duplicandoId, setDuplicandoId] = useState<number | null>(null);
  const [resaltadoId, setResaltadoId] = useState<number | null>(null);
  const [avisoDuplicado, setAvisoDuplicado] = useState('');

  const cargarBots = useCallback(async () => {
    const data = await authedFetch<BotListItem[]>('/bots');
    setBots(data);
    return data;
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.push('/login');
      return;
    }
    cargarBots().catch((err) => {
      if (err instanceof ApiError && err.status === 401) return; // authedFetch ya cerró sesión
      setError(err?.message || 'Error cargando bots');
    });
    authedFetch<TeamMe>('/teams/me')
      .then((me) => setEsDueno(me?.member?.role === 'owner'))
      .catch(() => setEsDueno(null));
  }, [router, cargarBots]);

  // El resaltado de la variante recién creada se apaga solo.
  useEffect(() => {
    if (resaltadoId === null) return;
    const t = setTimeout(() => setResaltadoId(null), 8000);
    return () => clearTimeout(t);
  }, [resaltadoId]);

  const puedeEditar = esDueno !== false;

  const filtered = (bots || []).filter((b) =>
    search.trim() === '' ? true : b.name.toLowerCase().includes(search.toLowerCase())
  );

  const elegibles = useMemo(() => (bots || []).filter(esRepartible), [bots]);

  const handleCreado = async (nuevoId: number, nombre: string) => {
    setDuplicandoId(null);
    setSearch(''); // que la variante no quede escondida por el buscador
    try {
      await cargarBots();
    } catch (err: any) {
      setError(err?.message || 'Error recargando bots');
    }
    setResaltadoId(nuevoId);
    setAvisoDuplicado(
      `Se creó «${nombre}». Está activa pero no recibe conversaciones hasta que le asignes un porcentaje en el reparto.`,
    );
  };

  const handleDownload = async () => {
    const token = getToken();
    if (!token) return;
    setDownloading(true);
    try {
      const res = await fetch('/api/bots/export', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const cd = res.headers.get('content-disposition') || '';
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : `bots-export-${Date.now()}.json`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setError(err.message || 'Error descargando');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Layout variant="fullscreen">
      <div className="p-8 w-full">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Chatbot</h1>
            <p className="text-gray-500 text-sm mt-1">
              Listado de los bots configurados para tu cuenta.
            </p>
          </div>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading || !bots || bots.length === 0}
            className="px-3 py-2 border border-gray-300 rounded-md text-gray-700 text-sm bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            title="Descargar todos los bots en formato JSON"
          >
            <span>⤓</span>
            {downloading ? 'Descargando…' : 'Descargar JSON'}
          </button>
        </div>

        {bots !== null && bots.some((b) => b.trigger_type === 'default') && (
          elegibles.length >= 2 ? (
            <RepartoPanel
              elegibles={elegibles}
              puedeEditar={puedeEditar}
              onGuardado={setBots}
            />
          ) : puedeEditar && (
            <div className="mb-6 bg-gloma-cream border border-gloma-rose-soft rounded-lg px-4 py-3 text-sm text-gray-600">
              <span className="font-semibold text-gloma-forest">¿Quieres probar otro guion?</span>{' '}
              Duplica tu bot por defecto con <span className="font-medium">«Duplicar como variante»</span>, ajusta
              su guion y reparte las conversaciones nuevas entre los dos para ver cuál vende más.
            </div>
          )
        )}

        <div className="flex items-center justify-between border-b border-gray-200 mb-4">
          <div className="flex gap-6">
            <button
              type="button"
              className="py-2 px-1 border-b-[3px] border-gloma-rose text-gray-800 font-semibold text-sm flex items-center gap-2"
            >
              Tus bots
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-gloma-rose-soft/300 text-white text-[10px] font-bold">
                {bots?.length ?? 0}
              </span>
            </button>
          </div>
          <input
            type="text"
            placeholder="Buscar tus bots..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="text-sm px-3 py-1.5 border border-gray-200 rounded-md focus:outline-none focus:border-gloma-rose w-56"
          />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        {avisoDuplicado && (
          <div className="bg-gloma-soft-mint border border-gloma-mint/40 text-gloma-forest px-4 py-2 rounded mb-4 text-sm flex items-start justify-between gap-3">
            <span>{avisoDuplicado}</span>
            <button
              type="button"
              onClick={() => setAvisoDuplicado('')}
              className="text-gloma-forest/70 hover:text-gloma-forest leading-none"
              aria-label="Cerrar aviso"
            >
              ×
            </button>
          </div>
        )}

        {bots === null && !error && (
          <p className="text-gray-400 text-sm">Cargando bots…</p>
        )}

        {bots !== null && filtered.length === 0 && (
          <p className="text-gray-400 text-sm py-8 text-center">
            No tienes bots configurados. Contáctanos para que te armemos el primero.
          </p>
        )}

        {filtered.length > 0 && (
          <div data-tour="bots-table" className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr className="text-sm text-gray-600">
                  <th className="text-left py-3 px-4 font-semibold">Nombre</th>
                  <th data-tour="trigger-column" className="text-left py-3 px-4 font-semibold">Activación</th>
                  <th className="text-left py-3 px-4 font-semibold">Reparto</th>
                  <th className="text-center py-3 px-4 font-semibold">Disparado</th>
                  <th className="text-left py-3 px-4 font-semibold">Modificado el</th>
                  <th className="py-3 px-4"><span className="sr-only">Acciones</span></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((bot, botIdx) => (
                  <BotFila
                    key={bot.id}
                    bot={bot}
                    tour={botIdx === 0}
                    resaltado={bot.id === resaltadoId}
                    puedeEditar={puedeEditar}
                    duplicando={duplicandoId === bot.id}
                    onDuplicar={() => {
                      setDuplicandoId(bot.id);
                      setAvisoDuplicado('');
                    }}
                    onCancelar={() => setDuplicandoId(null)}
                    onCreado={handleCreado}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {bots !== null && <TutorialOverlay moduleKey="bots" steps={BOTS_TUTORIAL} />}
    </Layout>
  );
}

function BotFila({
  bot,
  tour,
  resaltado,
  puedeEditar,
  duplicando,
  onDuplicar,
  onCancelar,
  onCreado,
}: {
  bot: BotListItem;
  tour: boolean;
  resaltado: boolean;
  puedeEditar: boolean;
  duplicando: boolean;
  onDuplicar: () => void;
  onCancelar: () => void;
  onCreado: (nuevoId: number, nombre: string) => Promise<void>;
}) {
  const filaRef = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    if (resaltado) filaRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [resaltado]);

  return (
    <>
      <tr
        ref={filaRef}
        className={`border-b border-gray-100 transition-colors ${
          resaltado ? 'bg-gloma-soft-mint' : 'hover:bg-gray-50'
        }`}
      >
        <td className="py-4 px-4">
          <a
            href={`/bots/${bot.id}`}
            target="_blank"
            rel="noopener noreferrer"
            {...(tour ? { 'data-tour': 'bot-link' } : {})}
            className="text-blue-600 hover:text-blue-800 hover:underline font-medium"
          >
            {bot.name}
          </a>
          {resaltado && (
            <span className="ml-2 text-[11px] font-semibold text-gloma-forest bg-white border border-gloma-mint/50 rounded-full px-2 py-0.5">
              Nueva
            </span>
          )}
          {bot.status !== 'active' && (
            <span className="ml-2 text-[11px] text-gray-500 bg-gray-100 rounded-full px-2 py-0.5">
              {bot.status === 'paused' ? 'Pausado' : bot.status === 'draft' ? 'Borrador' : bot.status}
            </span>
          )}
        </td>
        <td className="py-4 px-4">
          <EngineBadge bot={bot} />
          <TriggerBadge bot={bot} />
        </td>
        <td className="py-4 px-4 text-sm">
          <RepartoCell bot={bot} />
        </td>
        <td className={`text-center py-4 px-4 font-mono ${bot.triggered_count === 0 ? 'text-gray-300' : 'text-gray-800'}`}>
          {bot.triggered_count}
        </td>
        <td className="py-4 px-4 text-sm text-gray-600">
          <div>Creado {relativeTime(bot.created_at)}</div>
          <div className="text-xs text-gray-400">
            Actualizado {relativeTime(bot.updated_at)}
          </div>
        </td>
        <td className="py-4 px-4 text-right whitespace-nowrap">
          {/* Solo los bots por defecto se duplican (el backend da 400 con los demás):
              la variante existe para repartirle conversaciones nuevas. */}
          {puedeEditar && bot.trigger_type === 'default' && (
            <button
              type="button"
              onClick={duplicando ? onCancelar : onDuplicar}
              className="text-sm px-3 py-1.5 border border-gray-300 rounded-md text-gray-700 bg-white hover:bg-gray-50"
              title="Crea una copia con el mismo guion y productos para probar otra versión"
            >
              ⧉ Duplicar como variante
            </button>
          )}
        </td>
      </tr>
      {duplicando && <DuplicarFila bot={bot} onCreado={onCreado} onCancelar={onCancelar} />}
    </>
  );
}
