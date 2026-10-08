import type { RespuestaInteresados } from '../../lib/interesados';

/**
 * Las tres tarjetitas de arriba, con el mismo patrón que las de Llamadas.
 * "Contactados hoy" no está en el contrato de hoy: si el backend lo agrega se
 * pinta; mientras tanto, la tercera es cuántos ya tienen la ventana cerrada.
 */
export default function ResumenInteresados({ resumen }: { resumen: RespuestaInteresados['resumen'] }) {
  const tercera =
    typeof resumen.contactados_hoy === 'number'
      ? { n: resumen.contactados_hoy, texto: 'Contactados hoy' }
      : { n: resumen.ventana_cerrada, texto: 'Con la ventana cerrada' };

  return (
    <div
      data-tour="interesados-resumen"
      className="grid grid-cols-[repeat(auto-fit,minmax(84px,1fr))] gap-2 md:flex md:gap-4 mb-4"
    >
      <div className="bg-white rounded-xl border border-gray-200 px-3 md:px-5 py-3">
        <div className="text-2xl font-bold text-gloma-brown-darker">{resumen.por_contactar}</div>
        <div className="text-xs text-gray-500">Por contactar</div>
      </div>
      <div
        className={`rounded-xl border px-3 md:px-5 py-3 ${
          resumen.urgentes > 0 ? 'bg-red-50 border-red-200' : 'bg-white border-gray-200'
        }`}
      >
        <div
          className={`text-2xl font-bold ${
            resumen.urgentes > 0 ? 'text-red-700' : 'text-gloma-brown-darker'
          }`}
        >
          {resumen.urgentes}
        </div>
        <div className={`text-xs ${resumen.urgentes > 0 ? 'text-red-700' : 'text-gray-500'}`}>
          Se cierran en menos de 3 h
        </div>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 px-3 md:px-5 py-3">
        <div className="text-2xl font-bold text-gloma-brown-darker">{tercera.n}</div>
        <div className="text-xs text-gray-500">{tercera.texto}</div>
      </div>
    </div>
  );
}
