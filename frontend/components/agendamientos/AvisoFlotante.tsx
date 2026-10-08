import { useEffect } from 'react';

export type Aviso = {
  /** Cambia en cada aviso: reinicia el temporizador aunque el texto se repita. */
  id: number;
  texto: string;
  tipo: 'ok' | 'error';
  accion?: { texto: string; onClick: () => void };
  /** Cuánto dura. "Deshacer" dura 8 s. */
  ms: number;
};

/**
 * El aviso de abajo (a la derecha en escritorio, a lo ancho en móvil). Uno a la
 * vez: el nuevo reemplaza al anterior, y con él su "Deshacer".
 */
export default function AvisoFlotante({ aviso, onCerrar }: { aviso: Aviso | null; onCerrar: () => void }) {
  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(onCerrar, aviso.ms);
    return () => clearTimeout(t);
  }, [aviso, onCerrar]);

  if (!aviso) return null;
  const error = aviso.tipo === 'error';
  return (
    <div className="fixed z-40 bottom-4 left-4 right-4 sm:left-auto sm:max-w-md">
      <div
        role={error ? 'alert' : 'status'}
        className={`rounded-xl px-4 py-3 shadow-lg flex items-center gap-3 ${
          error ? 'bg-red-50 border border-red-200 text-red-800' : 'bg-gloma-brown-darker text-white'
        }`}
      >
        <span className="text-sm flex-1">{aviso.texto}</span>
        {aviso.accion && (
          <button
            type="button"
            onClick={() => {
              aviso.accion?.onClick();
              onCerrar();
            }}
            className={`text-sm font-semibold underline shrink-0 ${error ? 'text-red-800' : 'text-gloma-rose'}`}
          >
            {aviso.accion.texto}
          </button>
        )}
        <button
          type="button"
          onClick={onCerrar}
          aria-label="Cerrar aviso"
          className={`shrink-0 text-lg leading-none ${error ? 'text-red-700' : 'text-gloma-rose'}`}
        >
          ×
        </button>
      </div>
    </div>
  );
}
