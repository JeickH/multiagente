import { KeyboardEvent, useEffect, useId, useRef, useState } from 'react';
import { MOTIVOS_DESCARTE } from '../../lib/interesados';

type Props = {
  onElegir: (motivo: string) => void;
  disabled?: boolean;
  className: string;
};

/**
 * "Descartar" con el menú de motivos. Se cierra con Esc (el foco vuelve al
 * botón), con un click afuera o al elegir. Las flechas recorren los motivos.
 */
export default function MenuDescartar({ onElegir, disabled, className }: Props) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const idMenu = useId();

  useEffect(() => {
    if (!abierto) return;
    items.current[0]?.focus();
    const fuera = (e: MouseEvent) => {
      if (caja.current && !caja.current.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener('mousedown', fuera);
    return () => document.removeEventListener('mousedown', fuera);
  }, [abierto]);

  const alTeclear = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      setAbierto(false);
      boton.current?.focus();
      return;
    }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const lista = items.current.filter(Boolean) as HTMLButtonElement[];
    const i = lista.indexOf(document.activeElement as HTMLButtonElement);
    const sig = (i + (e.key === 'ArrowDown' ? 1 : lista.length - 1)) % lista.length;
    lista[sig]?.focus();
  };

  return (
    <div className="relative" ref={caja} onKeyDown={alTeclear}>
      <button
        ref={boton}
        type="button"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? idMenu : undefined}
        onClick={() => setAbierto((v) => !v)}
        className={`${className} w-full text-gray-600`}
      >
        Descartar
      </button>
      {abierto && (
        <div
          id={idMenu}
          role="menu"
          aria-label="Motivo para descartar"
          className="absolute right-0 z-30 mt-1 w-56 max-w-[80vw] bg-white rounded-xl border border-gray-200 shadow-lg p-2 text-sm"
        >
          <p className="px-2 py-1 text-xs text-gray-500">¿Por qué lo descartas?</p>
          {MOTIVOS_DESCARTE.map((m, i) => (
            <button
              key={m.valor}
              ref={(el) => {
                items.current[i] = el;
              }}
              type="button"
              role="menuitem"
              onClick={() => {
                setAbierto(false);
                onElegir(m.valor);
              }}
              className="w-full text-left px-2 py-2 rounded-lg hover:bg-gloma-soft-mint focus:bg-gloma-soft-mint focus:outline-none"
            >
              {m.texto}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
