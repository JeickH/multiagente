/**
 * Lista de demos: tabla desde `lg` (siete columnas, con el menú de 96 px no
 * caben antes) y tarjetas debajo. Orden fijo, la más reciente primero. El
 * nombre, la empresa y el «otro» son texto del visitante: se pintan como texto
 * de React (sin HTML ni autolinks). El teléfono y el correo llegan
 * enmascarados del backend; completos solo en el detalle.
 */
import { cuando, tipoTexto, type ItemDemo } from '../../lib/demosAdmin';
import { BadgeEstado, ChipsRecorrido, Esq, EtiquetaInterna } from './piezas';

export default function ListaDemos({
  items,
  cargandoPrimeraVez,
  abierta,
  vacio,
  onAbrir,
}: {
  items: ItemDemo[];
  cargandoPrimeraVez: boolean;
  abierta: string | null;
  /** Qué decir si no hay filas (lo arma la página según la causa). */
  vacio: React.ReactNode;
  onAbrir: (publicId: string, origen: HTMLElement) => void;
}) {
  if (cargandoPrimeraVez) {
    return (
      <div className="p-4 space-y-4" aria-hidden="true">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex gap-3 items-center">
            <Esq className="h-3 w-24" />
            <Esq className="h-3 flex-1" />
            <Esq className="h-3 w-1/4" />
          </div>
        ))}
      </div>
    );
  }
  if (items.length === 0) return <div className="px-4 py-12 text-center text-gloma-brown-light">{vacio}</div>;

  const nombre = (d: ItemDemo) =>
    d.lead_borrado || !d.nombre ? <span className="text-gloma-brown-light italic">Datos borrados</span> : d.nombre;

  return (
    <>
      <div className="hidden lg:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gloma-rose-soft text-gloma-brown text-left">
              <th className="px-4 py-3 font-semibold whitespace-nowrap">Creada</th>
              <th className="px-4 py-3 font-semibold">Prospecto</th>
              <th className="px-4 py-3 font-semibold">Contacto</th>
              <th className="px-4 py-3 font-semibold whitespace-nowrap" title="Aceptó recibir promociones">
                Promos
              </th>
              <th className="px-4 py-3 font-semibold text-right whitespace-nowrap" title="Mensajes que escribió el prospecto">
                Mensajes
              </th>
              <th className="px-4 py-3 font-semibold">Recorrido</th>
              <th className="px-4 py-3 font-semibold">Estado</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr
                key={d.public_id}
                onClick={(e) => onAbrir(d.public_id, e.currentTarget.querySelector('button') ?? e.currentTarget)}
                className={`border-t border-gloma-rose-soft hover:bg-gloma-cream/60 cursor-pointer ${
                  abierta === d.public_id ? 'bg-gloma-rose-soft/50' : ''
                }`}
              >
                <td className="px-4 py-3 whitespace-nowrap text-gloma-brown-light align-top">{cuando(d.created_at)}</td>
                <td className="px-4 py-3 align-top max-w-[16rem]">
                  <button
                    type="button"
                    className="font-medium text-gloma-brown text-left hover:underline break-words"
                    onClick={(e) => {
                      e.stopPropagation();
                      onAbrir(d.public_id, e.currentTarget);
                    }}
                  >
                    {nombre(d)}
                  </button>{' '}
                  {d.interna && <EtiquetaInterna />}
                  <div className="text-xs text-gloma-brown break-words">{d.empresa}</div>
                  <div className="text-xs text-gloma-brown-light break-words">{tipoTexto(d)}</div>
                </td>
                <td className="px-4 py-3 align-top">
                  {d.lead_borrado ? (
                    <span className="text-xs text-gloma-brown-light">—</span>
                  ) : (
                    <>
                      <div className="text-gloma-brown">{d.correo}</div>
                      <div className="text-xs text-gloma-brown-light tabular-nums">{d.telefono}</div>
                    </>
                  )}
                </td>
                <td className="px-4 py-3 align-top">
                  {d.acepta_promociones ? (
                    <span className="text-gloma-brown font-medium">Sí</span>
                  ) : (
                    <span className="text-gloma-brown-light">No</span>
                  )}
                </td>
                <td className="px-4 py-3 align-top text-right text-gloma-brown tabular-nums">
                  {d.estado === 'lista' ? d.turnos : '—'}
                </td>
                <td className="px-4 py-3 align-top">
                  <ChipsRecorrido item={d} />
                </td>
                <td className="px-4 py-3 align-top">
                  <BadgeEstado item={d} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="lg:hidden divide-y divide-gloma-rose-soft">
        {items.map((d) => (
          <li key={d.public_id}>
            <button
              type="button"
              onClick={(e) => onAbrir(d.public_id, e.currentTarget)}
              className={`w-full text-left p-4 hover:bg-gloma-cream/60 ${abierta === d.public_id ? 'bg-gloma-rose-soft/50' : ''}`}
            >
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span className="block font-semibold text-gloma-brown truncate">{d.empresa}</span>
                  <span className="block text-xs text-gloma-brown-light truncate">
                    {d.lead_borrado || !d.nombre ? 'Datos borrados' : d.nombre} · {tipoTexto(d)}
                  </span>
                </span>
                <BadgeEstado item={d} />
              </span>
              <span className="block mt-2">
                <ChipsRecorrido item={d} />
              </span>
              <span className="flex flex-wrap items-center gap-x-3 mt-2 text-[11px] text-gloma-brown-light">
                <span>{cuando(d.created_at)}</span>
                <span>
                  <span aria-hidden="true">💬 </span>
                  <span className="sr-only">Mensajes: </span>
                  {d.estado === 'lista' ? d.turnos : '—'}
                </span>
                <span>Promos: {d.acepta_promociones ? 'Sí' : 'No'}</span>
                {d.interna && <span>Prueba interna</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
