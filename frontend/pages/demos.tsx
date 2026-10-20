/**
 * Demos web — panel privado de la cuenta de Gloma (Sprint 32, #630).
 *
 * Quiénes armaron su bot de prueba en glomacx.com/demo, hasta dónde llegaron y
 * si pidieron hablar con Gloma (WhatsApp o llamada por Cal.com).
 *
 * - Diseño y estados: wireframe #628 (`ventas/identidad_gloma/diseno_panel_demos.html`).
 * - API: `lib/demosAdmin.ts` (contrato final de #627).
 * - Acceso: `GET /admin/demos/access`, igual que `/citas` con su `/access`. La
 *   página NO va en `PUBLIC_PAGES`: exige sesión, y la sesión se toca solo por
 *   `lib/session.ts` (vía `authedFetch`). En los dominios de la landing el
 *   middleware le da 404.
 * - El rango y «ocultar pruebas» mandan sobre el resumen y la lista; búsqueda,
 *   tipo, estado y etapa solo filtran la lista. Refrescar no vacía la pantalla:
 *   lo anterior queda al 45 % hasta que llega lo nuevo. Sin auto-refresco.
 * - El detalle se abre con `?d=<public_id>`: «atrás» lo cierra y el enlace se
 *   puede pasar dentro del equipo (igual exige la sesión de Gloma).
 */
import { useRouter } from 'next/router';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import Layout from '../components/Layout';
import Paginacion from '../components/Paginacion';
import DetalleDemo from '../components/demos/DetalleDemo';
import Embudo from '../components/demos/Embudo';
import FiltroRango from '../components/demos/FiltroRango';
import FiltrosLista from '../components/demos/FiltrosLista';
import ListaDemos from '../components/demos/ListaDemos';
import { ApiError, authedFetch } from '../lib/api';
import {
  errorDeRango,
  queryDemos,
  rangoDe,
  diaColombia,
  type Etapa,
  type FiltroEstado,
  type ListaDemos as Lista,
  type PresetRango,
} from '../lib/demosAdmin';
import { guardarNumero, leerNumero } from '../lib/preferencias';

const POR_PAGINA = [20, 50, 100];
const CLAVE_POR_PAGINA = 'demos.porPagina';
const TEXTO_RANGO: Record<Exclude<PresetRango, 'custom'>, string> = {
  hoy: 'hoy',
  '7': 'últimos 7 días',
  '30': 'últimos 30 días',
};

type Acceso = 'loading' | 'allowed' | 'denied' | 'error';

export default function DemosPage() {
  const router = useRouter();
  const [acceso, setAcceso] = useState<Acceso>('loading');

  // Filtros
  const [preset, setPreset] = useState<PresetRango>('7');
  const hoy = diaColombia(new Date());
  const [custom, setCustom] = useState(() => rangoDe('30', new Date()));
  const [ocultarInternas, setOcultarInternas] = useState(true);
  const [q, setQ] = useState('');
  const [tipo, setTipo] = useState('');
  const [estado, setEstado] = useState<FiltroEstado>('');
  const [etapa, setEtapa] = useState<Etapa>('');
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(20);

  // Datos
  const [datos, setDatos] = useState<Lista | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(false);
  const [actualizadoMs, setActualizadoMs] = useState<number | null>(null);
  const [recarga, setRecarga] = useState(0);
  const [reloj, setReloj] = useState(0);

  // Detalle y avisos
  const abierta = typeof router.query.d === 'string' ? router.query.d : null;
  const origenRef = useRef<HTMLElement | null>(null);
  const listaRef = useRef<HTMLElement>(null);
  const [aviso, setAviso] = useState('');

  const rango = preset === 'custom' ? custom : rangoDe(preset, new Date());
  const errorRango = preset === 'custom' ? errorDeRango(custom.desde, custom.hasta) : null;

  // ---------------------------------------------------------------- acceso
  useEffect(() => {
    let vivo = true;
    setPorPagina(leerNumero(CLAVE_POR_PAGINA, POR_PAGINA, 20));
    void (async () => {
      try {
        const res = await authedFetch<{ allowed: boolean }>('/admin/demos/access');
        if (vivo) setAcceso(res.allowed ? 'allowed' : 'denied');
      } catch {
        // Responde 200 siempre que haya sesión: si falla es la sesión o la red.
        if (vivo) setAcceso('error');
      }
    })();
    return () => {
      vivo = false;
    };
  }, []);

  // ---------------------------------------------------------------- datos
  const query = queryDemos({
    desde: rango.desde,
    hasta: rango.hasta,
    incluirInternas: !ocultarInternas,
    q,
    tipo,
    estado,
    etapa,
    pagina,
    porPagina,
  });

  useEffect(() => {
    if (acceso !== 'allowed' || errorRango) return;
    let vivo = true;
    let reintento: number | undefined;
    setCargando(true);
    const pedir = async (intento: number) => {
      try {
        const res = await authedFetch<Lista>(`/admin/demos?${query}`);
        if (!vivo) return;
        setDatos(res);
        setError(false);
        setActualizadoMs(Date.now());
        setCargando(false);
      } catch (e) {
        if (!vivo) return;
        // El primer 500 puede ser el arranque en frío de Amplify: un reintento
        // a los 2 s antes del aviso. Un 4xx no se reintenta.
        const status = e instanceof ApiError ? e.status : 0;
        if (intento === 0 && (status === 0 || status >= 500)) {
          reintento = window.setTimeout(() => void pedir(1), 2000);
          return;
        }
        setError(true);
        setCargando(false);
      }
    };
    void pedir(0);
    return () => {
      vivo = false;
      window.clearTimeout(reintento);
    };
  }, [acceso, query, errorRango, recarga]);

  // «Actualizado hace N min»
  useEffect(() => {
    const t = window.setInterval(() => setReloj((n) => n + 1), 30000);
    return () => window.clearInterval(t);
  }, []);
  const actualizado = useMemo(() => {
    if (!actualizadoMs) return '';
    const min = Math.floor((Date.now() - actualizadoMs) / 60000);
    return min < 1 ? 'Actualizado hace un momento' : `Actualizado hace ${min} min`;
  }, [actualizadoMs, reloj]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------- acciones
  const conPagina1 = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPagina(1);
  };
  const irALista = () => listaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const hayFiltros = Boolean(q || tipo || estado || etapa);
  const limpiar = () => {
    setQ('');
    setTipo('');
    setEstado('');
    setEtapa('');
    setPagina(1);
  };

  const abrir = useCallback(
    (id: string, origen: HTMLElement | null) => {
      origenRef.current = origen;
      const yaAbierta = typeof router.query.d === 'string';
      const destino = { pathname: '/demos', query: { ...router.query, d: id } };
      // Abrir agrega una entrada al historial («atrás» cierra); moverse entre
      // demos con ← → la reemplaza, para no llenar el historial.
      if (yaAbierta) void router.replace(destino, undefined, { shallow: true });
      else void router.push(destino, undefined, { shallow: true });
    },
    [router],
  );

  const cerrar = useCallback(() => {
    const { d: _d, ...resto } = router.query;
    void router.replace({ pathname: '/demos', query: resto }, undefined, { shallow: true });
    const origen = origenRef.current;
    window.setTimeout(() => {
      if (origen && document.contains(origen)) origen.focus({ preventScroll: true });
    }, 0);
  }, [router]);

  const items = datos?.items ?? [];
  const indice = abierta ? items.findIndex((i) => i.public_id === abierta) : -1;
  const mover = (delta: -1 | 1) => {
    const sig = items[indice + delta];
    if (indice >= 0 && sig) abrir(sig.public_id, origenRef.current);
  };

  useEffect(() => {
    if (!aviso) return;
    const t = window.setTimeout(() => setAviso(''), 2400);
    return () => window.clearTimeout(t);
  }, [aviso]);

  // ---------------------------------------------------------------- render
  const rangoTexto = preset === 'custom' ? `${custom.desde} a ${custom.hasta}` : TEXTO_RANGO[preset];
  const primeraCarga = !datos && cargando;
  const refrescando = Boolean(datos) && cargando;

  const vacio = hayFiltros ? (
    <>
      <p className="text-sm font-medium text-gloma-brown">Ninguna demo coincide con estos filtros</p>
      <button
        type="button"
        onClick={limpiar}
        className="mt-3 px-4 py-2 rounded-full text-xs font-semibold border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft"
      >
        Limpiar filtros
      </button>
    </>
  ) : (
    <>
      <p className="text-3xl mb-2" aria-hidden="true">
        🧪
      </p>
      <p className="text-sm font-medium text-gloma-brown">Ninguna demo en este rango</p>
      <p className="text-xs mt-1">Cuando alguien la arme en glomacx.com/demo, aparece aquí.</p>
      {preset !== '30' && (
        <button
          type="button"
          onClick={() => conPagina1(setPreset)('30')}
          className="mt-3 px-4 py-2 rounded-full text-xs font-semibold border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft"
        >
          Ver los últimos 30 días
        </button>
      )}
    </>
  );

  return (
    <Layout variant="fullscreen">
      <div className="flex-1 overflow-auto p-4 md:p-8 font-body">
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl md:text-3xl font-heading font-bold text-gloma-brown">Demos web</h1>
            <p className="text-sm text-gloma-brown-light mt-1 max-w-xl">
              Quiénes armaron su bot de prueba en glomacx.com/demo y si pidieron hablar con nosotros.
            </p>
          </div>
          {acceso === 'allowed' && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gloma-brown-light hidden sm:inline">{actualizado}</span>
              <button
                type="button"
                onClick={() => setRecarga((n) => n + 1)}
                disabled={cargando}
                className="px-3 py-1.5 rounded-full text-xs font-medium bg-white border border-gloma-rose text-gloma-brown hover:bg-gloma-rose-soft disabled:opacity-60"
              >
                <span aria-hidden="true">↻ </span>Actualizar
              </button>
            </div>
          )}
        </header>

        {acceso === 'loading' && <p className="text-sm text-gloma-brown-light">Cargando…</p>}

        {acceso === 'denied' && (
          <div className="bg-white border border-gloma-rose rounded-xl p-8 text-center">
            <p className="text-4xl mb-3" aria-hidden="true">
              🔒
            </p>
            <h2 className="font-heading text-xl text-gloma-brown mb-2">Módulo privado</h2>
            <p className="text-sm text-gloma-brown-light">Las demos web solo son visibles para la cuenta de Gloma.</p>
          </div>
        )}

        {acceso === 'error' && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
            No pudimos verificar tu acceso al módulo. Recarga la página e intenta de nuevo.
          </p>
        )}

        {acceso === 'allowed' && (
          <>
            <FiltroRango
              preset={preset}
              desde={custom.desde}
              hasta={custom.hasta}
              hoy={hoy}
              ocultarInternas={ocultarInternas}
              errorRango={errorRango}
              onPreset={conPagina1(setPreset)}
              onDesde={(v) => conPagina1(setCustom)({ ...custom, desde: v })}
              onHasta={(v) => conPagina1(setCustom)({ ...custom, hasta: v })}
              onOcultarInternas={conPagina1(setOcultarInternas)}
            />

            {error && (
              <div className="mb-6 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex flex-wrap items-center gap-3" role="alert">
                <span>⚠ No pudimos cargar las demos. Ya quedó registrado; intenta de nuevo en un momento.</span>
                <button
                  type="button"
                  onClick={() => setRecarga((n) => n + 1)}
                  className="ml-auto px-3 py-1.5 rounded-full text-xs font-semibold bg-gloma-brown text-white"
                >
                  Reintentar
                </button>
              </div>
            )}

            {(datos || cargando) && (
              <>
                <div className={`mb-8 transition-opacity ${refrescando ? 'opacity-[.45] pointer-events-none' : ''}`} aria-busy={cargando}>
                  <Embudo
                    resumen={datos?.resumen ?? null}
                    cargando={cargando}
                    rangoTexto={rangoTexto}
                    etapa={etapa}
                    onEtapa={(e) => {
                      conPagina1(setEtapa)(e);
                      irALista();
                    }}
                    onEstado={(e) => {
                      conPagina1(setEstado)(e);
                      irALista();
                    }}
                    onVer30={() => conPagina1(setPreset)('30')}
                  />
                </div>

                <section aria-labelledby="t-lista" ref={listaRef} className="scroll-mt-4">
                  <div className="flex items-baseline justify-between gap-2 mb-3">
                    <h2 id="t-lista" className="font-heading font-bold text-gloma-brown text-lg">
                      Demos
                    </h2>
                    {hayFiltros && (
                      <button type="button" onClick={limpiar} className="text-xs text-gloma-brown underline decoration-gloma-rose">
                        Limpiar filtros
                      </button>
                    )}
                  </div>
                  <FiltrosLista
                    q={q}
                    tipo={tipo}
                    estado={estado}
                    etapa={etapa}
                    onQ={conPagina1(setQ)}
                    onTipo={conPagina1(setTipo)}
                    onEstado={conPagina1(setEstado)}
                    onEtapa={conPagina1(setEtapa)}
                  />
                  <div
                    className={`bg-white rounded-xl border border-gloma-rose overflow-hidden transition-opacity ${
                      refrescando ? 'opacity-[.45] pointer-events-none' : ''
                    }`}
                    aria-busy={cargando}
                  >
                    <ListaDemos
                      items={items}
                      cargandoPrimeraVez={primeraCarga}
                      abierta={abierta}
                      vacio={vacio}
                      onAbrir={abrir}
                    />
                  </div>
                  {datos && (
                    <Paginacion
                      pagina={pagina}
                      porPagina={porPagina}
                      total={datos.total}
                      etiqueta="demos"
                      opciones={POR_PAGINA}
                      cargando={cargando}
                      onPagina={setPagina}
                      onPorPagina={(n) => {
                        guardarNumero(CLAVE_POR_PAGINA, n);
                        setPorPagina(n);
                        setPagina(1);
                      }}
                    />
                  )}
                </section>
              </>
            )}
          </>
        )}
      </div>

      {acceso === 'allowed' && abierta && (
        <DetalleDemo
          publicId={abierta}
          posicion={indice >= 0 ? `${indice + 1} de ${items.length} en esta página` : ''}
          hayAnterior={indice > 0}
          haySiguiente={indice >= 0 && indice < items.length - 1}
          onMover={mover}
          onCerrar={cerrar}
          onAviso={setAviso}
        />
      )}

      <div
        role="status"
        aria-live="polite"
        className={`pointer-events-none fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] bg-gloma-brown-darker text-white text-sm px-4 py-2.5 rounded-full shadow-lg transition-opacity ${
          aviso ? 'opacity-100' : 'opacity-0'
        }`}
      >
        {aviso}
      </div>
    </Layout>
  );
}
