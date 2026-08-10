import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout';
import { authedFetch } from '../lib/api';

/**
 * Publicaciones de Instagram — panel privado de la cuenta oficial de Gloma.
 *
 * Muestra la cola que maneja la herramienta de marketing
 * (`marketing/instagram/igpost.py`): qué piezas están programadas, cuándo sale
 * cada una y un enlace para descargar el contenido ya cargado en S3.
 *
 * Es de SOLO LECTURA. Instagram no tiene API de programación, así que la cola
 * la escribe el CLI y un cron la publica a la hora indicada; este panel es la
 * ventana para verla.
 *
 * El backend (`/instagram`) solo responde a la cuenta de Gloma y a los miembros
 * de su team; cualquier otra sesión recibe 403.
 */

type Slide = {
  index: number;
  filename: string;
  download_url: string;
};

type Publicacion = {
  id: string;
  slug: string;
  caption: string;
  status: string;
  publish_at: string | null;
  published_at: string | null;
  permalink: string | null;
  error: string | null;
  attempts: number;
  slides: Slide[];
};

type ColaResponse = {
  publicaciones: Publicacion[];
  resumen: {
    total: number;
    programadas: number;
    publicadas: number;
    fallidas: number;
    canceladas: number;
  };
};

const ESTADO_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  pending: { bg: '#FEF3C7', color: '#92400E', label: 'Programada' },
  publishing: { bg: '#DBEAFE', color: '#1E40AF', label: 'Publicando…' },
  published: { bg: '#E0F2F1', color: '#004D40', label: 'Publicada' },
  failed: { bg: '#FEE2E2', color: '#991B1B', label: 'Falló' },
  cancelled: { bg: '#F3F4F6', color: '#4B5563', label: 'Cancelada' },
};

const TZ = 'America/Bogota';

/** Fecha larga en hora de Bogotá, que es donde opera el equipo. */
function formatoFecha(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('es-CO', {
    timeZone: TZ,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(d);
}

/** "en 3 días", "en 2 h", "hace 5 min" — para ubicarse sin hacer la cuenta. */
function cuandoRelativo(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diffMs = d.getTime() - Date.now();
  const rtf = new Intl.RelativeTimeFormat('es-CO', { numeric: 'auto' });
  const abs = Math.abs(diffMs);
  const min = 60_000;
  const hora = 60 * min;
  const dia = 24 * hora;

  if (abs < hora) return rtf.format(Math.round(diffMs / min), 'minute');
  if (abs < dia) return rtf.format(Math.round(diffMs / hora), 'hour');
  return rtf.format(Math.round(diffMs / dia), 'day');
}

function Badge({ estado }: { estado: string }) {
  const s = ESTADO_STYLE[estado] ?? {
    bg: '#F3F4F6',
    color: '#4B5563',
    label: estado,
  };
  return (
    <span
      className="px-2.5 py-1 rounded-full text-xs font-medium whitespace-nowrap"
      style={{ backgroundColor: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

function Resumen({ resumen }: { resumen: ColaResponse['resumen'] }) {
  const tarjetas = [
    { label: 'Programadas', valor: resumen.programadas, color: '#92400E', bg: '#FEF3C7' },
    { label: 'Publicadas', valor: resumen.publicadas, color: '#004D40', bg: '#E0F2F1' },
    { label: 'Fallidas', valor: resumen.fallidas, color: '#991B1B', bg: '#FEE2E2' },
    { label: 'Total', valor: resumen.total, color: '#4B5563', bg: '#F3F4F6' },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      {tarjetas.map((t) => (
        <div
          key={t.label}
          className="rounded-xl p-4 border border-gloma-rose"
          style={{ backgroundColor: t.bg }}
        >
          <p className="text-2xl font-heading font-bold" style={{ color: t.color }}>
            {t.valor}
          </p>
          <p className="text-xs mt-0.5" style={{ color: t.color }}>
            {t.label}
          </p>
        </div>
      ))}
    </div>
  );
}

function TarjetaPublicacion({
  pub,
  onRefresh,
}: {
  pub: Publicacion;
  onRefresh: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [publicando, setPublicando] = useState(false);
  const [errorPub, setErrorPub] = useState<string | null>(null);
  const esFutura = pub.status === 'pending';
  const fecha = esFutura ? pub.publish_at : pub.published_at ?? pub.publish_at;

  const publicarAhora = async () => {
    const ok = window.confirm(
      `¿Publicar "${pub.slug}" en Instagram AHORA?\n\nEsto la sube de inmediato, sin esperar su hora programada. No se puede deshacer.`
    );
    if (!ok) return;
    setPublicando(true);
    setErrorPub(null);
    try {
      await authedFetch(`/instagram/${pub.id}/publish`, { method: 'POST' });
      onRefresh();
    } catch (e) {
      setErrorPub(e instanceof Error ? e.message : 'No se pudo publicar.');
      // El estado real (p.ej. la tomó el cron a la vez) lo trae el refresh.
      onRefresh();
    } finally {
      setPublicando(false);
    }
  };

  return (
    <article className="bg-white border border-gloma-rose rounded-xl p-5">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-heading font-bold text-gloma-brown truncate">{pub.slug}</h3>
            <Badge estado={pub.status} />
            <span className="text-xs text-gloma-brown-light">
              {pub.slides.length} {pub.slides.length === 1 ? 'imagen' : 'slides'}
              {pub.slides.length > 1 ? ' · carrusel' : ''}
            </span>
          </div>
          <p className="text-sm text-gloma-brown mt-1.5">
            {esFutura ? 'Se publica ' : 'Publicada '}
            <strong>{formatoFecha(fecha)}</strong>{' '}
            <span className="text-gloma-brown-light">({cuandoRelativo(fecha)})</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {(pub.status === 'pending' || pub.status === 'failed') && (
            <button
              type="button"
              onClick={() => void publicarAhora()}
              disabled={publicando}
              className="text-sm px-3 py-1.5 rounded-lg bg-gloma-brown text-white hover:bg-gloma-brown-dark transition-colors whitespace-nowrap disabled:opacity-50"
            >
              {publicando ? 'Publicando…' : '🚀 Publicar ahora'}
            </button>
          )}
          {pub.permalink && (
            <a
              href={pub.permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm px-3 py-1.5 rounded-lg border border-gloma-brown text-gloma-brown hover:bg-gloma-brown hover:text-white transition-colors whitespace-nowrap"
            >
              Ver en Instagram ↗
            </a>
          )}
        </div>
      </div>

      {errorPub && (
        <p className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {errorPub}
        </p>
      )}

      {pub.error && (
        <p className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {pub.error}
          {pub.attempts > 0 && ` (intento ${pub.attempts})`}
        </p>
      )}

      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="mt-3 text-sm text-gloma-brown-light hover:text-gloma-brown transition-colors"
        aria-expanded={abierto}
      >
        {abierto ? '▾ Ocultar' : '▸ Ver'} texto y descargas
      </button>

      {abierto && (
        <div className="mt-3 space-y-4">
          <div>
            <p className="text-xs font-medium text-gloma-brown-light mb-1">Texto</p>
            <p className="text-sm text-gloma-brown whitespace-pre-wrap bg-gloma-cream rounded-lg p-3">
              {pub.caption || '(sin texto)'}
            </p>
          </div>

          <div>
            <p className="text-xs font-medium text-gloma-brown-light mb-2">
              Contenido en AWS — los enlaces caducan en 1 hora
            </p>
            <div className="flex flex-wrap gap-2">
              {pub.slides.map((s) => (
                <a
                  key={s.index}
                  href={s.download_url}
                  className="text-sm px-3 py-1.5 rounded-lg bg-gloma-cream border border-gloma-rose text-gloma-brown hover:border-gloma-brown transition-colors"
                  title={s.filename}
                >
                  ⬇ Slide {s.index}
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

type Filtro = 'todas' | 'pending' | 'published' | 'failed';

export default function InstagramPage() {
  const [access, setAccess] = useState<'loading' | 'allowed' | 'denied' | 'error'>(
    'loading'
  );
  const [datos, setDatos] = useState<ColaResponse | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<Filtro>('todas');

  useEffect(() => {
    let vivo = true;
    void (async () => {
      try {
        const res = await authedFetch<{ allowed: boolean }>('/instagram/access');
        if (vivo) setAccess(res.allowed ? 'allowed' : 'denied');
      } catch {
        if (vivo) setAccess('error');
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setDatos(await authedFetch<ColaResponse>('/instagram'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No pudimos cargar la cola.');
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    if (access === 'allowed') void cargar();
  }, [access, cargar]);

  const visibles = useMemo(() => {
    if (!datos) return [];
    if (filtro === 'todas') return datos.publicaciones;
    return datos.publicaciones.filter((p) => p.status === filtro);
  }, [datos, filtro]);

  const filtroBtn = (activo: boolean) =>
    `px-3 py-1.5 text-sm rounded-lg border transition-colors ${
      activo
        ? 'bg-gloma-brown text-white border-gloma-brown'
        : 'border-gloma-rose text-gloma-brown-light hover:text-gloma-brown'
    }`;

  return (
    <Layout variant="fullscreen">
      <div className="flex-1 overflow-auto p-8 font-body">
        <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-3xl font-heading font-bold text-gloma-brown">
              Publicaciones de Instagram
            </h1>
            <p className="text-sm text-gloma-brown-light mt-1">
              Las piezas en cola, cuándo sale cada una y el contenido listo para descargar.
            </p>
          </div>
          {access === 'allowed' && (
            <button
              type="button"
              onClick={() => void cargar()}
              disabled={cargando}
              className="text-sm px-4 py-2 rounded-lg border border-gloma-brown text-gloma-brown hover:bg-gloma-brown hover:text-white transition-colors disabled:opacity-50"
            >
              {cargando ? 'Actualizando…' : '↻ Actualizar'}
            </button>
          )}
        </header>

        {access === 'loading' && <p className="text-sm text-gloma-brown-light">Cargando…</p>}

        {access === 'denied' && (
          <div className="bg-white border border-gloma-rose rounded-xl p-8 text-center">
            <p className="text-4xl mb-3">🔒</p>
            <h2 className="font-heading text-xl text-gloma-brown mb-2">Módulo privado</h2>
            <p className="text-sm text-gloma-brown-light">
              Las publicaciones de Instagram solo son visibles para la cuenta de Gloma.
            </p>
          </div>
        )}

        {access === 'error' && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
            No pudimos verificar tu acceso al módulo. Recarga la página e intenta de nuevo.
          </p>
        )}

        {access === 'allowed' && (
          <>
            {error && (
              <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2 mb-4">
                {error}
              </p>
            )}

            {datos && <Resumen resumen={datos.resumen} />}

            <nav className="flex items-center gap-2 mb-5 flex-wrap" aria-label="Filtrar por estado">
              {(
                [
                  ['todas', 'Todas'],
                  ['pending', 'Programadas'],
                  ['published', 'Publicadas'],
                  ['failed', 'Fallidas'],
                ] as [Filtro, string][]
              ).map(([valor, etiqueta]) => (
                <button
                  key={valor}
                  type="button"
                  onClick={() => setFiltro(valor)}
                  className={filtroBtn(filtro === valor)}
                  aria-current={filtro === valor ? 'true' : undefined}
                >
                  {etiqueta}
                </button>
              ))}
            </nav>

            {cargando && !datos && (
              <p className="text-sm text-gloma-brown-light">Cargando la cola…</p>
            )}

            {datos && visibles.length === 0 && (
              <div className="bg-white border border-gloma-rose rounded-xl p-8 text-center">
                <p className="text-4xl mb-3">📭</p>
                <h2 className="font-heading text-xl text-gloma-brown mb-2">
                  {datos.resumen.total === 0
                    ? 'Todavía no hay nada en cola'
                    : 'Nada con ese estado'}
                </h2>
                <p className="text-sm text-gloma-brown-light">
                  {datos.resumen.total === 0
                    ? 'Las publicaciones se programan con la herramienta de marketing (igpost.py schedule).'
                    : 'Prueba con otro filtro.'}
                </p>
              </div>
            )}

            <div className="space-y-4">
              {visibles.map((pub) => (
                <TarjetaPublicacion key={pub.id} pub={pub} onRefresh={() => void cargar()} />
              ))}
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
