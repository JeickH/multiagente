import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { OPCIONES_POR_PAGINA } from '../Paginacion';
import { ApiError, authedFetch } from '../../lib/api';
import {
  EstadoInteresado,
  Interesado,
  RespuestaInteresados,
  desfaseServidor,
  esReintentable,
} from '../../lib/interesados';

/** Recarga silenciosa mientras la pestaña del navegador esté a la vista. */
export const REFRESCO_MS = 2 * 60_000;
/** El reloj se repinta por minuto, no por segundo (ver `RelojVentana`). */
const TIC_MS = 60_000;
/** Espera antes del único reintento (arranque en frío del SSR de Amplify). */
const ESPERA_REINTENTO_MS = 3_000;

const esperar = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * Datos de la pestaña Interesados.
 *
 * Tres decisiones que no se ven en el código de un vistazo:
 *
 * - **Un solo reintento, y luego error con botón.** La primera petición a
 *   `/api/*` del día puede dar 500 por el arranque en frío de Amplify con el
 *   backend sano; reintentar una vez lo cubre. Si vuelve a fallar se muestra el
 *   error: nunca un "Cargando…" eterno.
 * - **404 = la cuenta no tiene Interesados.** El frontend de Amplify sale antes
 *   que el backend de ECS; si el endpoint todavía no existe, la página queda
 *   como era antes de esta pestaña en vez de mostrar un error.
 * - **El reloj es el del servidor.** `desfase` se mide con `generado_at` en cada
 *   respuesta buena y se conserva si un refresco falla: los relojes siguen
 *   corriendo con la última hora confiable.
 */
export function useInteresados() {
  const [estado, setEstadoState] = useState<EstadoInteresado>('por_contactar');
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(OPCIONES_POR_PAGINA[0]);

  const [datos, setDatos] = useState<RespuestaInteresados | null>(null);
  /** Primera carga (o cambio de filtro): no hay nada que mostrar todavía. */
  const [cargando, setCargando] = useState(true);
  /** Refresco con la lista a la vista: la lista NO se cambia por esqueletos. */
  const [refrescando, setRefrescando] = useState(false);
  /** Error sin datos que mostrar. */
  const [error, setError] = useState('');
  /** Falló un refresco y lo que se ve es viejo. */
  const [errorRefresco, setErrorRefresco] = useState(false);
  /** El endpoint no existe (404): la cuenta no tiene Interesados. */
  const [noDisponible, setNoDisponible] = useState(false);

  const [desfase, setDesfase] = useState(0);
  const [ahoraLocal, setAhoraLocal] = useState(() => Date.now());
  const [ultimaOkLocal, setUltimaOkLocal] = useState<number | null>(null);

  /** Tarjetas sacadas al instante por una acción, mientras el backend confirma. */
  const [ocultos, setOcultos] = useState<Set<string>>(() => new Set());

  // Si el filtro cambia con una petición en vuelo, la respuesta vieja se descarta.
  const secuencia = useRef(0);
  const datosRef = useRef<RespuestaInteresados | null>(null);
  datosRef.current = datos;

  const pedir = useCallback(
    async (silencioso: boolean) => {
      const mia = ++secuencia.current;
      if (silencioso && datosRef.current) setRefrescando(true);
      else setCargando(true);

      const params = new URLSearchParams({
        estado,
        pagina: String(pagina),
        limite: String(porPagina),
      });
      const url = `/agendamientos/interesados?${params}`;

      let res: RespuestaInteresados | null = null;
      let fallo: unknown = null;
      for (let intento = 0; intento < 2; intento++) {
        try {
          res = await authedFetch<RespuestaInteresados>(url);
          fallo = null;
          break;
        } catch (e) {
          fallo = e;
          if (intento === 0 && esReintentable(e)) {
            await esperar(ESPERA_REINTENTO_MS);
            if (mia !== secuencia.current) return;
            continue;
          }
          break;
        }
      }
      if (mia !== secuencia.current) return;

      if (res) {
        const local = Date.now();
        setDatos(res);
        setDesfase(desfaseServidor(res.generado_at, local));
        setAhoraLocal(local);
        setUltimaOkLocal(local);
        setError('');
        setErrorRefresco(false);
        setNoDisponible(false);
      } else if (fallo instanceof ApiError && fallo.status === 404) {
        setNoDisponible(true);
      } else if (silencioso && datosRef.current) {
        setErrorRefresco(true);
      } else {
        // El mensaje del backend ya viene sanitizado (regla 6), pero para esta
        // pantalla el texto del wireframe dice más que un "Error temporal".
        setError('No pudimos cargar los interesados');
      }
      setCargando(false);
      setRefrescando(false);
    },
    [estado, pagina, porPagina],
  );

  // Las acciones (p. ej. "Deshacer" a los 8 s) refrescan con el filtro VIGENTE,
  // no con el que había cuando se creó el aviso.
  const pedirRef = useRef(pedir);
  pedirRef.current = pedir;

  // Carga al montar y cada vez que cambia el filtro o la página.
  useEffect(() => {
    pedir(false);
  }, [pedir]);

  // Refresco cada 2 min con la pestaña visible; al volver a ella, si ya pasó
  // ese tiempo, se refresca de una.
  const ultimaOkRef = useRef<number | null>(null);
  ultimaOkRef.current = ultimaOkLocal;
  useEffect(() => {
    if (noDisponible) return;
    const t = setInterval(() => {
      if (document.visibilityState === 'visible') pedir(true);
    }, REFRESCO_MS);
    const alVolver = () => {
      if (document.visibilityState !== 'visible') return;
      const ultima = ultimaOkRef.current;
      if (ultima === null || Date.now() - ultima >= REFRESCO_MS) pedir(true);
    };
    document.addEventListener('visibilitychange', alVolver);
    return () => {
      clearInterval(t);
      document.removeEventListener('visibilitychange', alVolver);
    };
  }, [pedir, noDisponible]);

  // Reloj: un tic por minuto.
  useEffect(() => {
    const t = setInterval(() => setAhoraLocal(Date.now()), TIC_MS);
    return () => clearInterval(t);
  }, []);

  const setEstado = useCallback((e: EstadoInteresado) => {
    setEstadoState(e);
    setPagina(1);
  }, []);

  const clave = (id: number, est: string) => `${est}:${id}`;

  const ocultar = useCallback(
    (id: number) => setOcultos((s) => new Set(s).add(clave(id, estado))),
    [estado],
  );
  const mostrar = useCallback(
    (id: number, est?: string) =>
      setOcultos((s) => {
        const n = new Set(s);
        n.delete(clave(id, est ?? estado));
        return n;
      }),
    [estado],
  );

  const visibles: Interesado[] = useMemo(
    () => (datos?.interesados || []).filter((it) => !ocultos.has(clave(it.id, estado))),
    [datos, ocultos, estado],
  );

  return {
    estado,
    setEstado,
    pagina,
    setPagina,
    porPagina,
    setPorPagina: (n: number) => {
      setPorPagina(n);
      setPagina(1);
    },
    datos,
    visibles,
    cargando,
    refrescando,
    error,
    errorRefresco,
    noDisponible,
    ahoraServidor: ahoraLocal + desfase,
    /** Minutos desde la última respuesta buena (para "desfasados desde hace N min"). */
    minutosDesdeOk: ultimaOkLocal === null ? 0 : Math.floor((ahoraLocal - ultimaOkLocal) / 60_000),
    refrescar: () => pedirRef.current(true),
    reintentar: () => pedirRef.current(errorRefresco),
    ocultar,
    mostrar,
  };
}

export type EstadoInteresados = ReturnType<typeof useInteresados>;
