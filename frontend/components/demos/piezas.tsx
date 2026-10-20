/**
 * Piezas chicas del panel «Demos web» (#630): etiqueta de estado, chips del
 * recorrido, etiqueta de prueba interna y esqueleto de carga. El estado nunca
 * se dice solo con color: siempre texto e ícono.
 */
import {
  estadoVisible,
  recorridoDe,
  recorridoVacio,
  type ItemDemo,
} from '../../lib/demosAdmin';

export function Spin() {
  return (
    <span
      className="inline-block w-3 h-3 rounded-full border-2 border-current border-r-transparent animate-spin motion-reduce:animate-none"
      aria-hidden="true"
    />
  );
}

export function BadgeEstado({ item }: { item: Pick<ItemDemo, 'estado' | 'origen_productos'> }) {
  const e = estadoVisible(item);
  const base = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap';
  if (e.clave === 'generando')
    return (
      <span className={`${base} bg-gray-100 text-gray-700`}>
        <Spin />
        {e.texto}
      </span>
    );
  if (e.clave === 'error')
    return (
      <span className={`${base} bg-red-50 text-red-700`}>
        <span aria-hidden="true">⚠</span>
        {e.texto}
      </span>
    );
  if (e.clave === 'respaldo')
    return (
      <span className={`${base} bg-amber-50 text-amber-800`} title="El modelo falló y se usaron productos genéricos">
        <span aria-hidden="true">◐</span>
        {e.texto}
      </span>
    );
  return (
    <span className={`${base} bg-gloma-rose-soft text-gloma-brown`}>
      <span aria-hidden="true">✓</span>
      {e.texto}
    </span>
  );
}

export function ChipsRecorrido({ item }: { item: ItemDemo }) {
  const pasos = recorridoDe(item);
  if (pasos.length === 0) {
    return <span className="text-[11px] text-gloma-brown-light">{recorridoVacio(item)}</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {pasos.map((p) => (
        <span
          key={p.clave}
          className={`text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap ${
            p.fuerte ? 'bg-gloma-brown text-white' : 'bg-gloma-rose-soft text-gloma-brown'
          }`}
          title={p.clave === 'llamada_agendada' ? 'Reportada por el navegador' : undefined}
        >
          {p.texto}
          {p.fuerte && <span aria-hidden="true"> ✓</span>}
        </span>
      ))}
    </span>
  );
}

export function EtiquetaInterna() {
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 align-middle whitespace-nowrap">
      Prueba interna
    </span>
  );
}

export function Esq({ className = '' }: { className?: string }) {
  return <span className={`block rounded-md bg-gloma-rose-soft animate-pulse motion-reduce:animate-none ${className}`} />;
}
