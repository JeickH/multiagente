import {
  NivelVentana,
  nivelVentana,
  porcentajeVentana,
  textoReloj,
} from '../../lib/interesados';

/** Colores por nivel. El texto ("Quedan 1 h 50 min") siempre acompaña al color. */
export const ESTILO_NIVEL: Record<
  NivelVentana,
  { pastilla: string; barra: string; borde: string; titulo: string; encabezado: string }
> = {
  urgente: {
    pastilla: 'bg-red-50 text-red-700',
    barra: 'bg-red-600',
    borde: 'border-l-red-600',
    titulo: 'text-red-700',
    encabezado: 'Urgente · se cierra en menos de 3 h',
  },
  pronto: {
    pastilla: 'bg-amber-50 text-amber-800',
    barra: 'bg-amber-500',
    borde: 'border-l-amber-500',
    titulo: 'text-amber-800',
    encabezado: 'Pronto · de 3 a 8 h',
  },
  con_tiempo: {
    pastilla: 'bg-gloma-soft-mint text-gloma-forest',
    barra: 'bg-gloma-mint',
    borde: 'border-l-gloma-mint',
    titulo: 'text-gloma-forest',
    encabezado: 'Con tiempo · más de 8 h',
  },
  cerrada: {
    pastilla: 'bg-gray-100 text-gray-600',
    barra: 'bg-gray-300',
    borde: 'border-l-gray-300',
    titulo: 'text-gray-500',
    encabezado: 'Se cerró la ventana de WhatsApp',
  },
};

/**
 * Cuánto le queda a la ventana de 24 h para escribirle por WhatsApp.
 *
 * Sin `aria-live` a propósito: se repinta cada minuto y un lector de pantalla
 * no debe anunciar cada repintada.
 */
export default function RelojVentana({ ms }: { ms: number | null }) {
  const nivel = nivelVentana(ms);
  const estilo = ESTILO_NIVEL[nivel];
  const pct = porcentajeVentana(ms);

  if (nivel === 'cerrada') {
    return (
      <div>
        <p
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${estilo.pastilla}`}
        >
          {textoReloj(ms)}
        </p>
        <p className="text-[11px] text-gray-500 mt-2">Ya no puedes escribirle texto libre</p>
      </div>
    );
  }

  return (
    <div>
      <p
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${estilo.pastilla}`}
      >
        <span aria-hidden="true">⏱</span> {textoReloj(ms)}
      </p>
      <div
        className="mt-2 h-1.5 rounded-full bg-gray-100 overflow-hidden"
        role="img"
        aria-label={`Queda el ${pct} % de la ventana de 24 horas`}
      >
        <div className={`h-full ${estilo.barra}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-[11px] text-gray-500 mt-1">para escribirle por WhatsApp</p>
    </div>
  );
}
