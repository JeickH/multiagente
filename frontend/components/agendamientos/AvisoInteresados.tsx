type Props = {
  porContactar: number;
  urgentes: number;
  ventanaCerrada: number;
  onVer: () => void;
};

/**
 * Aviso encima de las llamadas agendadas: hay interesados con la ventana de
 * WhatsApp abierta esperando en la otra pestaña. Es lo que evita que la
 * pestaña nueva se quede sin mirar. Solo sale si alguno todavía se puede
 * escribir; en rojo si a alguno le quedan menos de 3 h.
 */
export default function AvisoInteresados({ porContactar, urgentes, ventanaCerrada, onVer }: Props) {
  const abiertos = porContactar - ventanaCerrada;
  if (porContactar <= 0 || abiertos <= 0) return null;

  const rojo = urgentes > 0;
  const n = porContactar === 1 ? '1 interesado esperando' : `${porContactar} interesados esperando`;
  return (
    <div
      role="status"
      className={`mb-4 rounded-xl border px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-2 ${
        rojo ? 'border-red-200 bg-red-50' : 'border-gloma-rose-soft bg-white'
      }`}
    >
      <p className={`text-sm flex-1 ${rojo ? 'text-red-800' : 'text-gloma-brown-darker'}`}>
        <b>Tienes {n}</b>
        {rojo
          ? ` y a ${urgentes} se les cierra la ventana de WhatsApp en menos de 3 horas. Atiéndelos primero.`
          : '. Atiéndelos antes de que se cierre la ventana de WhatsApp.'}
      </p>
      <button
        type="button"
        onClick={onVer}
        className={`shrink-0 min-h-[40px] px-4 rounded-lg bg-white border text-sm font-semibold ${
          rojo
            ? 'border-red-300 text-red-800 hover:bg-red-100'
            : 'border-gray-300 text-gloma-brown hover:border-gloma-brown'
        }`}
      >
        Ver interesados
      </button>
    </div>
  );
}
