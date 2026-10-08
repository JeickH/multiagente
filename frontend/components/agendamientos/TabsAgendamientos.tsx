import { KeyboardEvent, useRef } from 'react';
import type { Vista } from '../../lib/interesados';

type Props = {
  vista: Vista;
  onCambiar: (v: Vista) => void;
  /** `null` mientras no se sabe (primera carga o error): no se pinta el contador. */
  porContactar: number | null;
  urgentes: number;
  pendientesLlamadas: number | null;
};

/**
 * Pestañas Interesados / Llamadas agendadas (patrón WAI-ARIA de tabs: las
 * flechas izquierda/derecha mueven el foco y activan la otra pestaña).
 *
 * El contador de Interesados va en rojo **solo si hay urgentes** (ventana de
 * WhatsApp que se cierra en menos de 3 h); si no, verde bosque. El color nunca
 * va solo: el `aria-label` del contador dice "7 por contactar, 2 urgentes".
 */
export default function TabsAgendamientos({
  vista,
  onCambiar,
  porContactar,
  urgentes,
  pendientesLlamadas,
}: Props) {
  const refs = {
    interesados: useRef<HTMLButtonElement>(null),
    llamadas: useRef<HTMLButtonElement>(null),
  };

  const alTeclear = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const otra: Vista = vista === 'interesados' ? 'llamadas' : 'interesados';
    onCambiar(otra);
    refs[otra].current?.focus();
  };

  const base =
    'flex-1 md:flex-none min-w-0 min-h-[44px] px-1.5 md:px-4 rounded-lg text-[13px] md:text-sm font-semibold ' +
    'flex items-center justify-center gap-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-gloma-mint';
  const activa = 'bg-gloma-brown text-white';
  const inactiva = 'text-gray-600 hover:bg-gloma-soft-mint';

  const enInteresados = vista === 'interesados';
  const colorContador =
    urgentes > 0
      ? 'bg-red-600 text-white'
      : enInteresados
      ? 'bg-white text-gloma-forest'
      : 'bg-gloma-forest text-white';

  const etiquetaContador =
    porContactar === null
      ? ''
      : `${porContactar} por contactar${urgentes > 0 ? `, ${urgentes} urgente${urgentes === 1 ? '' : 's'}` : ''}`;

  return (
    <div className="sticky top-0 md:static z-20 -mx-4 px-4 md:mx-0 md:px-0 bg-gloma-cream pb-3">
      <div
        role="tablist"
        aria-label="Qué lista ver"
        className="flex w-full md:w-auto md:inline-flex rounded-xl bg-white border border-gray-200 p-1 gap-1"
      >
        <button
          ref={refs.interesados}
          type="button"
          role="tab"
          id="tab-interesados"
          aria-selected={enInteresados}
          aria-controls="panel-interesados"
          tabIndex={enInteresados ? 0 : -1}
          onClick={() => onCambiar('interesados')}
          onKeyDown={alTeclear}
          className={`${base} ${enInteresados ? activa : inactiva}`}
        >
          Interesados
          {porContactar !== null && (
            <span
              className={`min-w-[22px] h-[22px] px-1 rounded-full text-xs font-bold flex items-center justify-center ${colorContador}`}
              aria-label={etiquetaContador}
            >
              {porContactar}
            </span>
          )}
        </button>
        <button
          ref={refs.llamadas}
          type="button"
          role="tab"
          id="tab-llamadas"
          aria-selected={!enInteresados}
          aria-controls="panel-llamadas"
          tabIndex={enInteresados ? -1 : 0}
          onClick={() => onCambiar('llamadas')}
          onKeyDown={alTeclear}
          className={`${base} ${!enInteresados ? activa : inactiva}`}
        >
          <span className="md:hidden">Llamadas</span>
          <span className="hidden md:inline">Llamadas agendadas</span>
          {pendientesLlamadas !== null && (
            <span
              className={`min-w-[22px] h-[22px] px-1 rounded-full text-xs font-bold flex items-center justify-center ${
                enInteresados ? 'bg-gray-100 text-gray-700' : 'bg-white text-gloma-forest'
              }`}
              aria-label={`${pendientesLlamadas} por llamar`}
            >
              {pendientesLlamadas}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
