import { KeyboardEvent, useEffect, useRef } from 'react';

type Props = {
  nombre: string;
  /** "1 h 50 min", o `null` si la ventana ya no está abierta. */
  tiempo: string | null;
  tomando: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
};

/**
 * Confirmación de "Tomar conversación": es la única acción que cambia quién
 * responde (el bot deja de contestar en ese chat), por eso es la única que se
 * confirma. Foco atrapado, Esc cierra y, al cerrar, el foco vuelve al botón que
 * lo abrió. Mientras guarda, el botón dice "Tomando…" y queda deshabilitado:
 * un doble click no puede asignar dos veces.
 */
export default function ModalTomar({ nombre, tiempo, tomando, onConfirmar, onCancelar }: Props) {
  const caja = useRef<HTMLDivElement>(null);
  const confirmar = useRef<HTMLButtonElement>(null);
  const previo = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previo.current = document.activeElement as HTMLElement | null;
    confirmar.current?.focus();
    return () => {
      previo.current?.focus?.();
    };
  }, []);

  const alTeclear = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      if (!tomando) onCancelar();
      return;
    }
    if (e.key !== 'Tab' || !caja.current) return;
    const focos = Array.from(
      caja.current.querySelectorAll<HTMLElement>('button:not([disabled])'),
    );
    if (focos.length === 0) return;
    const primero = focos[0];
    const ultimo = focos[focos.length - 1];
    if (e.shiftKey && document.activeElement === primero) {
      e.preventDefault();
      ultimo.focus();
    } else if (!e.shiftKey && document.activeElement === ultimo) {
      e.preventDefault();
      primero.focus();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !tomando) onCancelar();
      }}
    >
      <div
        ref={caja}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-tomar-titulo"
        onKeyDown={alTeclear}
        className="bg-white rounded-2xl shadow-xl p-5 w-full max-w-sm"
      >
        <h3 id="modal-tomar-titulo" className="font-heading font-bold text-lg text-gloma-brown-darker">
          ¿Tomas esta conversación?
        </h3>
        <p className="text-sm text-gray-600 mt-2">
          Desde ahora le respondes tú a <b>{nombre}</b> y el bot deja de contestar en este chat.
        </p>
        {tiempo && (
          <p className="text-xs text-gray-500 mt-2">
            Te quedan {tiempo} para escribirle por WhatsApp.
          </p>
        )}
        <div className="mt-5 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button
            type="button"
            onClick={onCancelar}
            disabled={tomando}
            className="min-h-[44px] px-4 rounded-lg border border-gray-300 text-sm font-medium hover:border-gloma-brown disabled:opacity-50"
          >
            Cancelar
          </button>
          <button
            ref={confirmar}
            type="button"
            onClick={onConfirmar}
            disabled={tomando}
            className="min-h-[44px] px-4 rounded-lg bg-gloma-brown hover:bg-gloma-brown-dark text-white text-sm font-semibold disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-gloma-mint"
          >
            {tomando ? 'Tomando…' : 'Sí, tomarla y abrir el chat'}
          </button>
        </div>
      </div>
    </div>
  );
}
