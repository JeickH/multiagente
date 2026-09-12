import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout';
import Paginacion, { OPCIONES_POR_PAGINA } from '../components/Paginacion';
import { authedFetch } from '../lib/api';
import { fechaHoraCorta } from '../lib/fechas';

/**
 * Pedidos — lo que el bot cerró en el chat, y lo que quedó por llamar.
 *
 * Esta ventana reemplaza a Agendamientos en las cuentas que venden por el chat
 * (las que tienen su hoja de pedidos conectada, ver `GET /pedidos/access`). Las
 * dos listas viven juntas a propósito: son las dos mitades del mismo día de
 * quien atiende — *lo que hay que despachar* y *a quién hay que llamar porque
 * se quedó a medias*. Tenerlas en pantallas distintas obliga a revisar dos.
 *
 * Arriba los pedidos, porque son los que tienen plata adentro; abajo las
 * llamadas, que es trabajo de recuperación.
 *
 * El teléfono está a la vista en las dos tablas: es el dato por el que existe
 * la pantalla, tanto para confirmar un despacho como para marcar.
 */

type Pedido = {
  id: number;
  conversation_id: number | null;
  nombre: string;
  direccion: string;
  detalle: string;
  total: string | null;
  telefono: string | null;
  origen: string;
  estado: string;
  en_hoja: boolean;
  created_at: string;
};

type RespuestaPedidos = {
  pedidos: Pedido[];
  total: number;
  pagina: number;
  por_pagina: number;
  resumen: { total: number; pendientes: number; despachados: number; sin_hoja: number };
  estados: string[];
};

type Agendamiento = {
  id: number;
  conversation_id: number;
  contacto: string | null;
  telefono: string;
  fecha_llamada: string;
  estado: string;
  asesor: string | null;
};

type RespuestaAgendamientos = {
  agendamientos: Agendamiento[];
  resumen: { total: number; pendientes: number; cerrados: number };
};

const ESTADO_PEDIDO: Record<string, { bg: string; color: string; label: string }> = {
  pendiente: { bg: '#FEF3C7', color: '#92400E', label: 'Por despachar' },
  despachado: { bg: '#E0F2F1', color: '#004D40', label: 'Despachado' },
  cancelado: { bg: '#F3F4F6', color: '#4B5563', label: 'Cancelado' },
};

/**
 * La fecha de la llamada llega como "2026-09-14" (sin hora ni zona). Pasarla
 * por `new Date(iso)` la interpretaría como medianoche UTC y en Colombia se
 * pintaría el día ANTERIOR — el asesor llamaría un día tarde.
 */
function fechaLlamada(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString('es-CO', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

function diasDesdeHoy(iso: string): number | null {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return null;
  const hoy = new Date();
  const cero = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((new Date(y, m - 1, d).getTime() - cero.getTime()) / 86400000);
}

function CuandoLlamar({ fecha, estado }: { fecha: string; estado: string }) {
  const dias = diasDesdeHoy(fecha);
  let nota = '';
  let color = '#6B7280';
  if (estado !== 'cerrado' && dias !== null) {
    if (dias < 0) {
      nota = dias === -1 ? 'ayer' : `hace ${Math.abs(dias)} días`;
      color = '#B91C1C';
    } else if (dias === 0) {
      nota = 'hoy';
      color = '#B45309';
    } else if (dias === 1) {
      nota = 'mañana';
    } else {
      nota = `en ${dias} días`;
    }
  }
  return (
    <div>
      <div className="font-medium text-gloma-brown-darker">{fechaLlamada(fecha)}</div>
      {nota && (
        <div className="text-xs" style={{ color }}>
          {nota}
        </div>
      )}
    </div>
  );
}

function Tarjeta({ valor, texto }: { valor: number | string; texto: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 px-5 py-3">
      <div className="text-2xl font-bold text-gloma-brown-darker">{valor}</div>
      <div className="text-xs text-gray-500">{texto}</div>
    </div>
  );
}

export default function PedidosPage() {
  const [datos, setDatos] = useState<RespuestaPedidos | null>(null);
  const [llamadas, setLlamadas] = useState<RespuestaAgendamientos | null>(null);
  const [hoja, setHoja] = useState<string | null>(null);
  // Si la hoja todavía no tiene su script publicado, no se avisa de filas
  // "sin escribir": no falló nada, falta terminar de conectarla.
  const [hojaConectada, setHojaConectada] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [filtro, setFiltro] = useState('');
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(OPCIONES_POR_PAGINA[0]);
  const [guardando, setGuardando] = useState<number | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError('');
    try {
      const params = new URLSearchParams({
        limite: String(porPagina),
        pagina: String(pagina),
      });
      if (filtro) params.set('estado', filtro);
      // Las dos listas en paralelo: son independientes y la pantalla no sirve
      // a medias.
      const [pedidos, agenda] = await Promise.all([
        authedFetch<RespuestaPedidos>(`/pedidos?${params}`),
        authedFetch<RespuestaAgendamientos>('/agendamientos?estado=pendiente&limite=50'),
      ]);
      setDatos(pedidos);
      setLlamadas(agenda);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar la lista.');
    } finally {
      setCargando(false);
    }
  }, [filtro, pagina, porPagina]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // El nombre de la hoja conectada, para poder nombrarla en el encabezado.
  useEffect(() => {
    authedFetch<{ allowed: boolean; hoja: string | null; conectada: boolean }>(
      '/pedidos/access',
    )
      .then((r) => {
        setHoja(r.hoja);
        setHojaConectada(Boolean(r.conectada));
      })
      .catch(() => setHoja(null));
  }, []);

  const cambiarEstado = async (p: Pedido) => {
    const nuevo = p.estado === 'despachado' ? 'pendiente' : 'despachado';
    setGuardando(p.id);
    setError('');
    try {
      await authedFetch(`/pedidos/${p.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ estado: nuevo }),
      });
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el cambio.');
    } finally {
      setGuardando(null);
    }
  };

  const filas = datos?.pedidos || [];
  const resumen = datos?.resumen;
  const porLlamar = llamadas?.agendamientos || [];

  const chips = useMemo(
    () => [
      { valor: '', texto: 'Todos' },
      { valor: 'pendiente', texto: 'Por despachar' },
      { valor: 'despachado', texto: 'Despachados' },
    ],
    [],
  );

  const aplicarFiltro = (valor: string) => {
    setFiltro(valor);
    setPagina(1);
  };

  return (
    <Layout variant="fullscreen">
      <div className="p-8">
        <header className="mb-6">
          <h1 className="text-3xl font-heading font-bold text-gloma-brown-darker">
            🧾 Pedidos
          </h1>
          <p className="text-gray-600 mt-1">
            Los pedidos que el bot cerró en el chat, con el nombre, la dirección
            y lo que pidió cada cliente.
            {hoja && hojaConectada
              ? ` Cada uno se escribe también en «${hoja}».`
              : ''}
          </p>
        </header>

        {resumen && (
          <div className="flex flex-wrap gap-4 mb-6">
            <Tarjeta valor={resumen.pendientes} texto="Por despachar" />
            <Tarjeta valor={resumen.despachados} texto="Despachados" />
            <Tarjeta valor={porLlamar.length} texto="Llamadas por hacer" />
            {hojaConectada && resumen.sin_hoja > 0 && (
              <div className="bg-red-50 rounded-xl border border-red-200 px-5 py-3">
                <div className="text-2xl font-bold text-red-700">{resumen.sin_hoja}</div>
                <div className="text-xs text-red-600">Sin escribir en la hoja</div>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center gap-2 mb-4">
          {chips.map((c) => (
            <button
              key={c.valor || 'todos'}
              type="button"
              onClick={() => aplicarFiltro(c.valor)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                filtro === c.valor
                  ? 'bg-gloma-brown text-white border-gloma-brown'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-gloma-brown'
              }`}
            >
              {c.texto}
            </button>
          ))}
          <button
            type="button"
            onClick={cargar}
            disabled={cargando}
            className="ml-auto px-3 py-1.5 rounded-full text-xs font-medium border border-gray-300 bg-white text-gray-600 hover:border-gloma-brown disabled:opacity-50"
          >
            {cargando ? 'Actualizando…' : '↻ Actualizar'}
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-800 px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-200">
                <th className="px-4 py-3 font-medium">Cliente</th>
                <th className="px-4 py-3 font-medium">Dirección</th>
                <th className="px-4 py-3 font-medium">Pedido</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Total</th>
                <th className="px-4 py-3 font-medium">Teléfono</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Entró</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filas.map((p) => {
                const s = ESTADO_PEDIDO[p.estado] || ESTADO_PEDIDO.pendiente;
                return (
                  <tr key={p.id} className="border-b border-gray-100 last:border-0 align-top">
                    <td className="px-4 py-3 font-medium text-gloma-brown-darker">
                      {p.nombre}
                      {p.origen === 'simulador' && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-gray-400">
                          prueba
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 max-w-[220px]">{p.direccion}</td>
                    <td className="px-4 py-3 text-gray-700 max-w-[260px]">{p.detalle}</td>
                    <td className="px-4 py-3 font-medium whitespace-nowrap tabular-nums">
                      {p.total || '—'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {p.telefono ? (
                        <a
                          href={`tel:+${p.telefono}`}
                          className="text-gloma-brown hover:underline"
                        >
                          +{p.telefono}
                        </a>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {fechaHoraCorta(p.created_at, '—')}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap"
                        style={{ backgroundColor: s.bg, color: s.color }}
                      >
                        {s.label}
                      </span>
                      {hojaConectada && !p.en_hoja && (
                        <div className="text-[11px] text-red-600 mt-1">no llegó a la hoja</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      {p.conversation_id && (
                        <a
                          href={`/mensajes?conversacion=${p.conversation_id}`}
                          className="text-xs text-gray-500 hover:text-gloma-brown mr-3"
                        >
                          Ver chat
                        </a>
                      )}
                      <button
                        type="button"
                        onClick={() => cambiarEstado(p)}
                        disabled={guardando === p.id}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 hover:border-gloma-brown disabled:opacity-50"
                      >
                        {guardando === p.id
                          ? '…'
                          : p.estado === 'despachado'
                          ? 'Reabrir'
                          : 'Marcar despachado'}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!cargando && filas.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-500">
                    Todavía no hay pedidos. Cuando un cliente mande su nombre,
                    dirección y pedido por el chat, aparece aquí.
                  </td>
                </tr>
              )}
              {cargando && filas.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-400">
                    Cargando…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <Paginacion
          pagina={pagina}
          porPagina={porPagina}
          total={datos?.total || 0}
          onPagina={setPagina}
          onPorPagina={(n) => {
            setPorPagina(n);
            setPagina(1);
          }}
          cargando={cargando}
          etiqueta="pedidos"
        />

        {/* ── Segunda mitad del día: a quién llamar ────────────────────── */}
        <section className="mt-12">
          <h2 className="text-xl font-heading font-bold text-gloma-brown-darker">
            📞 Llamadas por hacer
          </h2>
          <p className="text-gray-600 mt-1 mb-4 text-sm">
            Clientes que dejaron la conversación después de recibir información.
            El bot les agenda la llamada para 3 días después.
          </p>

          <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="px-4 py-3 font-medium">Cliente potencial</th>
                  <th className="px-4 py-3 font-medium">Teléfono</th>
                  <th className="px-4 py-3 font-medium whitespace-nowrap">Llamar el</th>
                  <th className="px-4 py-3 font-medium">Asesor</th>
                  <th className="px-4 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {porLlamar.map((f) => (
                  <tr key={f.id} className="border-b border-gray-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-gloma-brown-darker">
                      {f.contacto || <span className="text-gray-400">Sin nombre</span>}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <a
                        href={`tel:+${f.telefono}`}
                        className="text-gloma-brown hover:underline"
                      >
                        +{f.telefono}
                      </a>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <CuandoLlamar fecha={f.fecha_llamada} estado={f.estado} />
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {f.asesor || <span className="text-gray-400">Sin asignar</span>}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <a
                        href={`/mensajes?conversacion=${f.conversation_id}`}
                        className="text-xs text-gray-500 hover:text-gloma-brown"
                      >
                        Ver chat
                      </a>
                    </td>
                  </tr>
                ))}
                {!cargando && porLlamar.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                      No hay llamadas pendientes. 🎉
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Layout>
  );
}
