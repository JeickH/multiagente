import { useCallback, useEffect, useState } from 'react';
import Layout from '../components/Layout';
import Paginacion, {
  OPCIONES_POR_PAGINA,
  guardarPorPagina,
  leerPorPagina,
} from '../components/Paginacion';
import { authedFetch } from '../lib/api';
import { fechaHoraCorta } from '../lib/fechas';
import { formatearWhatsapp } from '../lib/formatoWhatsapp';

/**
 * Conversaciones — ventana de supervisión de la cuenta administradora.
 *
 * Desde `gloma@glomabeauty.com` se ven, en modo lectura, los chats de las
 * cuentas que el backend habilita en `SUPERVISION_CUENTAS` (hoy mascotas y
 * Arranquemos Pues). Sirve para saber cómo les está yendo a los bots de los
 * clientes sin entrar con la contraseña de cada cuenta.
 *
 * No se confunde con `/mensajes`: esa es la bandeja de la cuenta propia — las
 * conversaciones del bot de Gloma — y ahí sí se puede responder. Aquí no hay
 * caja de texto a propósito: contestar es de la cuenta dueña del WhatsApp.
 *
 * El acceso lo decide el backend (`GET /supervision/access`), no el correo del
 * token: del JWT solo se lee `exp` (regla de seguridad 7).
 */

type Cuenta = {
  slug: string;
  nombre: string;
  correo: string;
  bots: string[];
  hilos: number;
};

type Hilo = {
  hilo_id: string;
  cuenta: string;
  bot: string | null;
  contacto: string | null;
  canal: string;
  canal_label: string;
  inicio: string;
  fin: string;
  turnos: number;
  caminos: string[];
  atendido_por: string;
  preview: string | null;
};

type Turno = {
  fecha: string;
  quien: 'persona' | 'bot' | 'asesor' | 'sistema';
  autor: string | null;
  texto: string;
  camino_label: string | null;
  herramientas: string[];
  truncado: boolean;
  error: string | null;
};

type Detalle = {
  hilo_id: string;
  cuenta: string;
  contacto: string | null;
  canal: string;
  canal_label: string;
  turnos: Turno[];
  completo: boolean;
};

/** Hora de Colombia. La conversión vive en `lib/fechas.ts` (la usa toda la app). */
function fechaCorta(iso: string): string {
  return fechaHoraCorta(iso, iso);
}

/** Quién habló, y cómo se pinta cada quién en la transcripción. */
const VOZ: Record<Turno['quien'], { emoji: string; label: string; bg: string; color: string }> = {
  persona: { emoji: '👤', label: 'Contacto', bg: '#FFFFFF', color: '#111827' },
  bot: { emoji: '🤖', label: 'Bot', bg: '#E0F2F1', color: '#004D40' },
  asesor: { emoji: '🙋', label: 'Asesor', bg: '#FEF3C7', color: '#92400E' },
  sistema: { emoji: '⚙️', label: 'Sistema', bg: '#F3F4F6', color: '#4B5563' },
};

function Turnos({ detalle }: { detalle: Detalle }) {
  if (detalle.turnos.length === 0) {
    return <p className="text-xs text-gray-400 pt-3">Este hilo no tiene mensajes guardados.</p>;
  }
  return (
    <div className="pt-3 flex flex-col gap-2">
      {!detalle.completo && (
        <p className="text-[11px] text-gray-400">
          Del chat web solo se guarda un adelanto de lo que respondió el bot: los
          mensajes largos aparecen recortados.
        </p>
      )}
      {detalle.turnos.map((t, i) => {
        const voz = VOZ[t.quien] || VOZ.sistema;
        return (
          <div
            key={`${t.fecha}-${i}`}
            className="rounded-lg px-3 py-2 border"
            style={{ backgroundColor: voz.bg, borderColor: '#E5E7EB' }}
          >
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="text-xs font-semibold" style={{ color: voz.color }}>
                {voz.emoji} {t.autor || voz.label}
              </span>
              {t.camino_label && (
                <span
                  className="text-[11px] px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: '#F3F4F6', color: '#374151' }}
                >
                  {t.camino_label}
                </span>
              )}
              {t.herramientas.map((h) => (
                <span key={h} className="text-[10px] font-mono text-gray-400">
                  {h}
                </span>
              ))}
              <span className="ml-auto text-[11px] text-gray-300">{fechaCorta(t.fecha)}</span>
            </div>
            {/* Son los mismos mensajes que se leen en /mensajes: se pintan con
                el formato de WhatsApp (`*negrilla*`) por la misma razón, y
                porque tener las dos ventanas distintas confundiría a quien
                supervisa. Nodos de React, nunca HTML: el texto lo escribió un
                cliente (ver `lib/formatoWhatsapp.ts`). */}
            <p className="text-sm text-gray-700 whitespace-pre-wrap break-words">
              {formatearWhatsapp(t.texto)}
              {t.truncado && <span className="text-gray-400"> […]</span>}
            </p>
            {t.error && (
              <p className="text-[11px] mt-1 px-2 py-1 rounded" style={{ backgroundColor: '#FDECEA', color: '#8A1C12' }}>
                ⚠️ {t.error}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function Conversaciones() {
  const [permitido, setPermitido] = useState<boolean | null>(null);
  const [cuentas, setCuentas] = useState<Cuenta[]>([]);
  const [cuenta, setCuenta] = useState<string | null>(null);
  const [hilos, setHilos] = useState<Hilo[]>([]);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [detalles, setDetalles] = useState<Record<string, Detalle>>({});
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(OPCIONES_POR_PAGINA[0]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelado = false;
    authedFetch<{ allowed: boolean }>('/supervision/access')
      .then(async (r) => {
        if (cancelado) return;
        const ok = Boolean(r?.allowed);
        setPermitido(ok);
        if (!ok) {
          setCargando(false);
          return;
        }
        const res = await authedFetch<{ cuentas: Cuenta[] }>('/supervision/cuentas');
        if (cancelado) return;
        setCuentas(res.cuentas || []);
        setCuenta(res.cuentas?.[0]?.slug ?? null);
        setCargando(false);
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
  }, []);

  // El "por página" elegido se recuerda entre visitas. Va en un efecto porque
  // `localStorage` no existe en el render del servidor.
  useEffect(() => {
    setPorPagina(leerPorPagina('conversaciones.porPagina'));
  }, []);

  const cargarHilos = useCallback(
    async (slug: string, pag: number, tamano: number) => {
      setCargando(true);
      try {
        const res = await authedFetch<{ conversaciones: Hilo[]; total: number }>(
          `/supervision/conversaciones?cuenta=${encodeURIComponent(slug)}` +
            `&pagina=${pag}&limite=${tamano}`
        );
        setHilos(res.conversaciones || []);
        setTotal(res.total || 0);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No pudimos cargar las conversaciones');
      } finally {
        setCargando(false);
      }
    },
    []
  );

  // Cambiar de cuenta o de tamaño de página vuelve a la primera: quedarse en
  // la página 7 de una cuenta que tiene 2 muestra una pantalla vacía sin
  // explicar por qué.
  useEffect(() => {
    setPagina(1);
  }, [cuenta, porPagina]);

  useEffect(() => {
    if (!cuenta) return;
    // Cambiar de página o de cuenta cierra el hilo abierto: el id de un hilo
    // solo tiene sentido dentro de su cuenta, y el que estaba desplegado ya no
    // está en pantalla.
    setAbierto(null);
    void cargarHilos(cuenta, pagina, porPagina);
  }, [cuenta, pagina, porPagina, cargarHilos]);

  /** Abre o cierra un hilo; la primera vez trae sus mensajes. */
  const alternar = async (hilo: Hilo) => {
    if (abierto === hilo.hilo_id) {
      setAbierto(null);
      return;
    }
    setAbierto(hilo.hilo_id);
    if (detalles[hilo.hilo_id]) return;
    try {
      const res = await authedFetch<Detalle>(
        `/supervision/conversaciones/${encodeURIComponent(hilo.hilo_id)}` +
          `?cuenta=${encodeURIComponent(hilo.cuenta)}`
      );
      setDetalles((prev) => ({ ...prev, [hilo.hilo_id]: res }));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No pudimos cargar la conversación');
    }
  };

  if (cargando && permitido === null) {
    return (
      <Layout variant="fullscreen">
        <div className="flex-1 flex items-center justify-center text-gray-500">Cargando…</div>
      </Layout>
    );
  }

  if (permitido === false) {
    return (
      <Layout variant="fullscreen">
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-600">
          <span className="text-4xl">👁️</span>
          <p className="font-semibold">Este módulo no está disponible en tu cuenta</p>
        </div>
      </Layout>
    );
  }

  const actual = cuentas.find((c) => c.slug === cuenta) || null;

  return (
    <Layout variant="fullscreen">
      <div className="flex-1 p-6 lg:p-8" style={{ backgroundColor: '#FAFAF8' }}>
        {/* ===== Encabezado ===== */}
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">👁️ Conversaciones</h1>
            <p className="text-sm text-gray-500 mt-1">
              Los chats de los bots de las cuentas que administramos, en modo lectura.
              Las conversaciones del bot de Gloma siguen en{' '}
              <a href="/mensajes" className="underline" style={{ color: '#008069' }}>
                Mensajes
              </a>
              .
            </p>
          </div>
          <button
            type="button"
            onClick={() => cuenta && void cargarHilos(cuenta, pagina, porPagina)}
            disabled={cargando || !cuenta}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-opacity disabled:opacity-50"
            style={{ backgroundColor: '#008069' }}
          >
            {cargando ? 'Actualizando…' : '🔄 Actualizar'}
          </button>
        </div>

        {error && (
          <p className="my-3 text-sm px-4 py-2 rounded-lg" style={{ backgroundColor: '#FDECEA', color: '#8A1C12' }}>
            {error}
          </p>
        )}

        {/* ===== Pestañas de cuenta ===== */}
        <div className="flex flex-wrap gap-2 my-5 border-b border-gray-200 pb-3">
          {cuentas.length === 0 && (
            <p className="text-sm text-gray-400">
              No hay cuentas habilitadas para supervisar.
            </p>
          )}
          {cuentas.map((c) => (
            <button
              key={c.slug}
              type="button"
              onClick={() => setCuenta(c.slug)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors ${
                cuenta === c.slug ? 'text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
              style={cuenta === c.slug ? { backgroundColor: '#008069' } : undefined}
            >
              {c.nombre} ({c.hilos})
            </button>
          ))}
        </div>

        {actual && (
          <p className="text-sm text-gray-500 mb-4">
            {actual.bots.length > 0
              ? `Bot: ${actual.bots.join(' · ')}`
              : 'Esta cuenta todavía no tiene bots.'}{' '}
            Toca una fila para leer los mensajes.
          </p>
        )}

        {/* ===== Lista de hilos ===== */}
        {!cargando && hilos.length === 0 && actual && (
          <p className="text-sm text-gray-400 py-8 text-center">
            Todavía no hay conversaciones en esta cuenta.
          </p>
        )}

        {actual && total > 0 && (
          <Paginacion
            pagina={pagina}
            porPagina={porPagina}
            total={total}
            onPagina={setPagina}
            onPorPagina={(n) => {
              setPorPagina(n);
              guardarPorPagina('conversaciones.porPagina', n);
            }}
            cargando={cargando}
          />
        )}

        <div className="flex flex-col gap-2">
          {hilos.map((h) => (
            <div key={h.hilo_id} className="rounded-xl border bg-white" style={{ borderColor: '#E5E7EB' }}>
              <button
                type="button"
                onClick={() => void alternar(h)}
                className="w-full flex flex-wrap items-center gap-3 px-4 py-3 text-left"
              >
                <span className="text-gray-400 text-xs">{abierto === h.hilo_id ? '▾' : '▸'}</span>
                <span className="font-semibold text-gray-800 text-sm">
                  {h.contacto || 'Visitante anónimo'}
                </span>
                <span className="text-[11px] text-gray-400">{h.canal_label}</span>
                <span className="flex flex-wrap gap-1.5">
                  {h.caminos.length > 0 ? (
                    h.caminos.map((camino) => (
                      <span
                        key={camino}
                        className="text-[11px] px-2 py-0.5 rounded-full"
                        style={{ backgroundColor: '#E0F2F1', color: '#004D40' }}
                      >
                        {camino}
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] text-gray-400">sin acciones · solo conversó</span>
                  )}
                  {h.atendido_por !== 'bot' && (
                    <span
                      className="text-[11px] px-2 py-0.5 rounded-full"
                      style={{ backgroundColor: '#FEF3C7', color: '#92400E' }}
                    >
                      🙋 {h.atendido_por}
                    </span>
                  )}
                </span>
                <span className="ml-auto text-xs text-gray-400 whitespace-nowrap">
                  {h.turnos} mensaje{h.turnos === 1 ? '' : 's'} · {fechaCorta(h.fin)}
                </span>
              </button>

              {h.preview && abierto !== h.hilo_id && (
                <p className="px-4 pb-3 -mt-1 text-xs text-gray-400 truncate">
                  {formatearWhatsapp(h.preview)}
                </p>
              )}

              {abierto === h.hilo_id && (
                <div className="px-4 pb-4 border-t" style={{ borderColor: '#F3F4F6' }}>
                  {detalles[h.hilo_id] ? (
                    <Turnos detalle={detalles[h.hilo_id]} />
                  ) : (
                    <p className="text-xs text-gray-400 pt-3">Cargando mensajes…</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Repetida al pie: con 100 por página, volver arriba para pasar a la
            siguiente es un viaje largo. */}
        {actual && total > porPagina && (
          <Paginacion
            pagina={pagina}
            porPagina={porPagina}
            total={total}
            onPagina={(n) => {
              setPagina(n);
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            onPorPagina={(n) => {
              setPorPagina(n);
              guardarPorPagina('conversaciones.porPagina', n);
            }}
            cargando={cargando}
          />
        )}
      </div>
    </Layout>
  );
}
