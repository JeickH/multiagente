import { useCallback, useEffect, useMemo, useState } from 'react';
import Layout from '../components/Layout';
import Paginacion, { OPCIONES_POR_PAGINA } from '../components/Paginacion';
import TutorialOverlay from '../components/TutorialOverlay';
import { authedFetch } from '../lib/api';
import { fechaHoraCorta } from '../lib/fechas';

/**
 * Agendamientos — las llamadas por hacer a quien dejó la conversación a medias.
 *
 * De dónde salen: cuando el bot da una conversación por abandonada y esa
 * persona **alcanzó a recibir información** (preguntó y le contestaron), queda
 * agendada una llamada para 3 días después. Los que sólo recibieron el saludo y
 * nunca volvieron a escribir no entran: no son clientes potenciales, son
 * números.
 *
 * La llamada NO se hace desde acá (decisión del CEO). Esta pantalla es la lista
 * de a quién marcar, con su teléfono a la vista, y el botón para dar la gestión
 * por cerrada.
 *
 * La ven todas las cuentas del team — administrador y asesor —, por eso vive en
 * el menú de siempre y no detrás de un `/access` como los módulos internos.
 */

type Agendamiento = {
  id: number;
  conversation_id: number;
  contacto: string | null;
  telefono: string;
  nivel_interes: string;
  fecha_llamada: string;
  estado: string;
  asesor: string | null;
  abandonada_at: string;
  cerrado_at: string | null;
};

type Respuesta = {
  agendamientos: Agendamiento[];
  total: number;
  pagina: number;
  por_pagina: number;
  resumen: { total: number; pendientes: number; cerrados: number };
  estados: string[];
};

const ESTADO_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  pendiente: { bg: '#FEF3C7', color: '#92400E', label: 'Pendiente' },
  cerrado: { bg: '#E0F2F1', color: '#004D40', label: 'Cerrado' },
};

/**
 * El recorrido que ve el asesor la primera vez que entra (Sprint 15).
 *
 * Está escrito para alguien que nunca vio esta pantalla y cuyo trabajo es
 * llamar: por eso el orden es el de su día —a quién llamo, con qué número,
 * cuándo tocaba— y no el orden de las columnas. El paso del teléfono y el de
 * cerrar son los dos que de verdad cambian lo que hace: el resto es contexto.
 */
const AGENDAMIENTOS_TUTORIAL = [
  {
    selector: '[data-tour="agendamientos-resumen"]',
    title: 'Tus llamadas pendientes',
    body: 'Aquí llegan los clientes que le escribieron al bot, recibieron información y después dejaron de responder. No son contactos fríos: ya preguntaron por el plan. El contador te dice cuántas llamadas te faltan.',
  },
  {
    selector: '[data-tour="agendamientos-telefono"]',
    title: 'El teléfono, listo para marcar',
    body: 'Este es el número que dejó la persona en WhatsApp. Haz click y se abre el marcador de tu equipo o celular. La llamada se hace por fuera de la plataforma: aquí solo llevas el registro.',
  },
  {
    selector: '[data-tour="agendamientos-fecha"]',
    title: 'Cuándo hay que llamar',
    body: 'El bot agenda la llamada para 3 días después de que la conversación se enfrió. Debajo de la fecha te avisa si es hoy, mañana o si ya se pasó (en rojo). La lista viene ordenada por eso: lo más urgente, arriba.',
  },
  {
    selector: '[data-tour="agendamientos-chat"]',
    title: 'Mira qué le dijo el bot',
    body: '"Ver chat" te lleva a la conversación completa antes de marcar. Sirve para no repetirle lo que ya le explicaron y para retomar justo donde quedó.',
  },
  {
    selector: '[data-tour="agendamientos-cerrar"]',
    title: 'Cierra la gestión',
    body: 'Cuando ya llamaste, marca "Cerrado" y sale de tus pendientes. Si te equivocaste o hay que volver a intentarlo, con el filtro "Cerrados" la encuentras y la puedes reabrir.',
  },
];

const NIVEL_LABEL: Record<string, string> = {
  con_informacion: 'Recibió información',
  solo_bienvenida: 'Solo bienvenida',
};

/**
 * La fecha de la llamada llega como "2026-09-08" (sin hora ni zona). Pasarla
 * por `new Date(iso)` la interpretaría como medianoche UTC y en Colombia se
 * pintaría el día ANTERIOR — el asesor llamaría un día tarde. Por eso se parte
 * el texto y se arma la fecha en local, igual que en `citas.tsx`.
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

/** "2026-09-08" comparado contra hoy, sin que la zona meta la cuchara. */
function diasDesdeHoy(iso: string): number | null {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return null;
  const hoy = new Date();
  const cero = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
  return Math.round((new Date(y, m - 1, d).getTime() - cero.getTime()) / 86400000);
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

/** Cuándo toca llamar, en palabras. Es lo que ordena el día del asesor. */
function CuandoLlamar({ fecha, estado }: { fecha: string; estado: string }) {
  const dias = diasDesdeHoy(fecha);
  const cerrado = estado === 'cerrado';
  let nota = '';
  let color = '#6B7280';
  if (!cerrado && dias !== null) {
    if (dias < 0) {
      nota = dias === -1 ? 'ayer' : `hace ${Math.abs(dias)} días`;
      color = '#B91C1C';
    } else if (dias === 0) {
      nota = 'hoy';
      color = '#B45309';
    } else if (dias === 1) {
      nota = 'mañana';
      color = '#374151';
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

export default function AgendamientosPage() {
  const [datos, setDatos] = useState<Respuesta | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [filtro, setFiltro] = useState('pendiente');
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
      const res = await authedFetch<Respuesta>(`/agendamientos?${params}`);
      setDatos(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar la lista.');
    } finally {
      setCargando(false);
    }
  }, [filtro, pagina, porPagina]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const cambiarEstado = async (fila: Agendamiento) => {
    const nuevo = fila.estado === 'cerrado' ? 'pendiente' : 'cerrado';
    setGuardando(fila.id);
    setError('');
    try {
      await authedFetch(`/agendamientos/${fila.id}`, {
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

  const filas = datos?.agendamientos || [];
  const resumen = datos?.resumen;

  // Al cambiar de filtro se vuelve a la primera página: quedarse en la 3 de un
  // filtro que ahora tiene una sola página deja la pantalla en blanco.
  const aplicarFiltro = (valor: string) => {
    setFiltro(valor);
    setPagina(1);
  };

  const chips = useMemo(
    () => [
      { valor: 'pendiente', texto: 'Pendientes' },
      { valor: 'cerrado', texto: 'Cerrados' },
      { valor: '', texto: 'Todos' },
    ],
    [],
  );

  return (
    // `fullscreen` como el resto de los listados: el default (`centered`)
    // mete el contenido en una tarjeta angosta y la tabla se sale por los
    // lados.
    <Layout variant="fullscreen">
      <div className="p-8">
        <header className="mb-6">
          <h1 className="text-3xl font-heading font-bold text-gloma-brown-darker">
            📞 Agendamientos
          </h1>
          <p className="text-gray-600 mt-1">
            Clientes potenciales que dejaron la conversación después de recibir
            información. El bot agenda la llamada para 3 días después.
          </p>
        </header>

        {resumen && (
          <div data-tour="agendamientos-resumen" className="flex gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 px-5 py-3">
              <div className="text-2xl font-bold text-gloma-brown-darker">
                {resumen.pendientes}
              </div>
              <div className="text-xs text-gray-500">Por llamar</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 px-5 py-3">
              <div className="text-2xl font-bold text-gloma-brown-darker">
                {resumen.cerrados}
              </div>
              <div className="text-xs text-gray-500">Cerrados</div>
            </div>
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
                <th className="px-4 py-3 font-medium">Cliente potencial</th>
                <th className="px-4 py-3 font-medium">Teléfono</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Llamar el</th>
                <th className="px-4 py-3 font-medium">Interés</th>
                <th className="px-4 py-3 font-medium">Asesor</th>
                <th className="px-4 py-3 font-medium">Se enfrió</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f, idx) => (
                <tr key={f.id} className="border-b border-gray-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-gloma-brown-darker">
                    {f.contacto || <span className="text-gray-400">Sin nombre</span>}
                  </td>
                  {/* Los `data-tour` van solo en la primera fila: el tutorial
                      resalta un elemento, no la columna entera. */}
                  <td
                    className="px-4 py-3"
                    {...(idx === 0 ? { 'data-tour': 'agendamientos-telefono' } : {})}
                  >
                    {/* `tel:` para que el asesor marque desde el equipo sin
                        copiar el número a mano. */}
                    <a
                      href={`tel:+${f.telefono}`}
                      className="text-gloma-brown hover:underline whitespace-nowrap"
                    >
                      +{f.telefono}
                    </a>
                  </td>
                  <td
                    className="px-4 py-3 whitespace-nowrap"
                    {...(idx === 0 ? { 'data-tour': 'agendamientos-fecha' } : {})}
                  >
                    <CuandoLlamar fecha={f.fecha_llamada} estado={f.estado} />
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {NIVEL_LABEL[f.nivel_interes] || f.nivel_interes}
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {f.asesor || <span className="text-gray-400">Sin asignar</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                    {fechaHoraCorta(f.abandonada_at, '—')}
                  </td>
                  <td className="px-4 py-3">
                    <EstadoBadge estado={f.estado} />
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <a
                      href={`/mensajes?conversacion=${f.conversation_id}`}
                      className="text-xs text-gray-500 hover:text-gloma-brown mr-3"
                      {...(idx === 0 ? { 'data-tour': 'agendamientos-chat' } : {})}
                    >
                      Ver chat
                    </a>
                    <button
                      type="button"
                      onClick={() => cambiarEstado(f)}
                      disabled={guardando === f.id}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 hover:border-gloma-brown disabled:opacity-50"
                      {...(idx === 0 ? { 'data-tour': 'agendamientos-cerrar' } : {})}
                    >
                      {guardando === f.id
                        ? '…'
                        : f.estado === 'cerrado'
                        ? 'Reabrir'
                        : 'Marcar cerrado'}
                    </button>
                  </td>
                </tr>
              ))}
              {!cargando && filas.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-gray-500">
                    {filtro === 'pendiente'
                      ? 'No hay llamadas pendientes. 🎉'
                      : 'No hay agendamientos para este filtro.'}
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
          etiqueta="agendamientos"
        />
      </div>

      {/* Después de la primera carga: el overlay mide el elemento que resalta,
          y si la tabla todavía no existe todos los pasos saldrían centrados. */}
      {datos !== null && (
        <TutorialOverlay moduleKey="agendamientos" steps={AGENDAMIENTOS_TUTORIAL} />
      )}
    </Layout>
  );
}
