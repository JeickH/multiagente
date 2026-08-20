import { guardarNumero, leerNumero } from '../lib/preferencias';

/**
 * Controles de paginación: cuántas filas por página y en cuál vamos.
 *
 * Lo comparten la bandeja (`/mensajes`) y la ventana de supervisión
 * (`/conversaciones`) porque el contrato del backend es el mismo en las dos:
 * `?limite=&pagina=` y una respuesta con `total`.
 *
 * El `total` que se muestra es el del FILTRO aplicado, no el de la cuenta. Es
 * deliberado: con "Pendientes" puesto, "1-20 de 87" tiene que querer decir 87
 * pendientes. Decir el total de la cuenta ahí sería mentirle al usuario sobre
 * cuánto le falta por revisar.
 */

export const OPCIONES_POR_PAGINA = [20, 50, 100, 200];

type Props = {
  pagina: number;
  porPagina: number;
  total: number;
  onPagina: (pagina: number) => void;
  onPorPagina: (porPagina: number) => void;
  cargando?: boolean;
  /** Cómo se llama lo que se está paginando, para el texto. */
  etiqueta?: string;
};

export default function Paginacion({
  pagina,
  porPagina,
  total,
  onPagina,
  onPorPagina,
  cargando = false,
  etiqueta = 'conversaciones',
}: Props) {
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  const desde = total === 0 ? 0 : (pagina - 1) * porPagina + 1;
  const hasta = Math.min(pagina * porPagina, total);
  const hayAnterior = pagina > 1;
  const haySiguiente = pagina < paginas;

  const boton =
    'px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ' +
    'disabled:opacity-40 disabled:cursor-not-allowed';

  // Dos renglones fijos en vez de un `flex-wrap`: la bandeja lo monta en una
  // columna de 384px y el ancho disponible cambia con la pantalla. Envolviendo,
  // "Siguiente" caía solo a una tercera línea y quedaba torcido; así se ve
  // igual en la columna angosta y en la página ancha.
  return (
    <div className="flex flex-col gap-2 py-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-gloma-brown-light">
          {total === 0
            ? `Sin ${etiqueta}`
            : `${desde}-${hasta} de ${total} ${etiqueta}`}
        </p>
        <label className="text-xs text-gloma-brown-light whitespace-nowrap">
          Por página:{' '}
          <select
            value={porPagina}
            onChange={(e) => onPorPagina(Number(e.target.value))}
            disabled={cargando}
            className="ml-1 border rounded-lg px-2 py-1 text-sm bg-white border-gloma-rose-soft text-gloma-brown"
          >
            {OPCIONES_POR_PAGINA.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onPagina(pagina - 1)}
          disabled={!hayAnterior || cargando}
          className={`${boton} border-gloma-rose-soft text-gloma-brown`}
        >
          ← Anterior
        </button>
        <span className="text-xs text-gloma-brown-light whitespace-nowrap">
          {pagina} / {paginas}
        </span>
        <button
          type="button"
          onClick={() => onPagina(pagina + 1)}
          disabled={!haySiguiente || cargando}
          className={`${boton} border-gloma-rose-soft text-gloma-brown`}
        >
          Siguiente →
        </button>
      </div>
    </div>
  );
}

/**
 * Recuerda el "por página" elegido, por pantalla.
 *
 * Cada pantalla lleva su propia clave: quien revisa la bandeja de a 20 puede
 * querer la supervisión de a 100, y son decisiones distintas.
 */
export function leerPorPagina(clave: string): number {
  return leerNumero(clave, OPCIONES_POR_PAGINA, OPCIONES_POR_PAGINA[0]);
}

export function guardarPorPagina(clave: string, valor: number): void {
  guardarNumero(clave, valor);
}
