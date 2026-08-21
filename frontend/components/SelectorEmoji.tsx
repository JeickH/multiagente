/**
 * Selector de emojis del compositor de la bandeja.
 *
 * Sin librería a propósito. Un paquete de emojis pesa cientos de KB porque trae
 * el catálogo Unicode completo con nombres, alias y búsqueda; acá lo que se
 * necesita es lo que una asesora usa de verdad respondiendo por WhatsApp, y eso
 * cabe en una lista escrita a mano. Los emojis son texto: no hay imágenes que
 * cargar ni fuente que instalar — los pinta el sistema operativo.
 *
 * El orden no es alfabético ni "por categoría Unicode": arriba están los que se
 * usan a diario en una conversación de ventas (saludo, gracias, confirmación) y
 * después el resto.
 */
import { useEffect, useRef, useState } from 'react';

type Grupo = { nombre: string; emojis: string[] };

const GRUPOS: Grupo[] = [
  {
    nombre: 'Los de siempre',
    emojis: [
      '😊', '🙌', '🤗', '😃', '😉', '🙏', '👍', '👌', '✅', '✨',
      '🎉', '💬', '📲', '🔥', '💯', '🥳', '😍', '🤩', '😅', '👏',
    ],
  },
  {
    nombre: 'Caritas',
    emojis: [
      '😀', '😁', '😂', '🤣', '🙂', '😌', '😎', '🥰', '😘', '🤔',
      '😐', '😴', '😢', '😭', '😱', '😳', '🙃', '😇', '🤭', '😬',
    ],
  },
  {
    nombre: 'Gestos',
    emojis: [
      '👋', '🤝', '💪', '🙋', '🤷', '👇', '👉', '👈', '☝️', '✌️',
      '🫶', '❤️', '🧡', '💛', '💚', '💙', '💜', '💖', '💝', '🌹',
    ],
  },
  {
    nombre: 'Viaje',
    emojis: [
      '🌴', '🏖️', '🏝️', '🌊', '☀️', '⛱️', '🐚', '🐬', '🚌', '✈️',
      '🏨', '🛏️', '🧳', '🗺️', '📍', '🌅', '🍹', '🍽️', '📸', '🎒',
    ],
  },
  {
    nombre: 'Negocio',
    emojis: [
      '💳', '💰', '💵', '🧾', '📄', '📆', '⏰', '📞', '📱', '📧',
      '📎', '📌', '⭐', '🎁', '🏷️', '🔔', '⚠️', '❌', '➡️', '🕐',
    ],
  },
];

type Props = {
  /** Se llama con el emoji elegido; el compositor decide dónde insertarlo. */
  onElegir: (emoji: string) => void;
  deshabilitado?: boolean;
};

export default function SelectorEmoji({ onElegir, deshabilitado = false }: Props) {
  const [abierto, setAbierto] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);

  // Cerrar con clic afuera o con Esc: un panel que se queda abierto tapando la
  // conversación es peor que no tenerlo.
  useEffect(() => {
    if (!abierto) return;

    function alClicAfuera(e: MouseEvent) {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false);
    }
    function alPresionar(e: KeyboardEvent) {
      if (e.key === 'Escape') setAbierto(false);
    }
    document.addEventListener('mousedown', alClicAfuera);
    document.addEventListener('keydown', alPresionar);
    return () => {
      document.removeEventListener('mousedown', alClicAfuera);
      document.removeEventListener('keydown', alPresionar);
    };
  }, [abierto]);

  return (
    <div className="relative" ref={contenedor}>
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        disabled={deshabilitado}
        title="Insertar emoji"
        aria-label="Insertar emoji"
        aria-expanded={abierto}
        className="w-10 h-10 flex-shrink-0 self-end rounded-lg border border-gray-200 text-lg leading-none flex items-center justify-center text-gloma-brown hover:bg-gloma-rose-soft hover:border-gloma-rose transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        😊
      </button>

      {abierto && (
        <div
          role="dialog"
          aria-label="Emojis"
          className="absolute bottom-12 left-0 z-40 w-72 max-h-72 overflow-y-auto rounded-xl border border-gray-200 bg-white p-3 shadow-2xl"
        >
          {GRUPOS.map((grupo) => (
            <div key={grupo.nombre} className="mb-3 last:mb-0">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                {grupo.nombre}
              </div>
              <div className="grid grid-cols-10 gap-0.5">
                {grupo.emojis.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    // El panel no se cierra al elegir: casi nunca se manda un
                    // emoji solo, y volver a abrirlo para poner el segundo es
                    // exactamente el tipo de fricción que hace que no se use.
                    onClick={() => onElegir(emoji)}
                    title={emoji}
                    className="h-7 w-7 rounded text-lg leading-none hover:bg-gloma-rose-soft"
                  >
                    {emoji}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
