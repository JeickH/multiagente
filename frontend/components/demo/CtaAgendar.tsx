/**
 * Las dos salidas de la demo (#625): «Agendar una llamada» (principal, abre
 * el modal de Cal.com) y «Escribir por WhatsApp» (secundaria, wa.me con el
 * texto prellenado). Los clics se cuentan con `registrarEvento` desde
 * `DemoPage`, que arma `AccionesAgendar`.
 */
import { TEXTOS_AGENDAR as T } from '../../lib/agendarLlamada';

export interface AccionesAgendar {
  abrirLlamada: () => void;
  enlaceWhatsapp: string;
  alClicWhatsapp: () => void;
}

/**
 * - `bloque`: dos botones apilados a lo ancho (tarjetas y avisos).
 * - `barra`: lado a lado y compactos (barra de fin del chat).
 * - `enlaces`: dos enlaces de texto, cuando la acción principal es otra
 *   («Intentar de nuevo», «Hacer una demo nueva»).
 */
export default function CtaAgendar({
  acciones,
  variante,
  className = '',
}: {
  acciones: AccionesAgendar;
  variante: 'bloque' | 'barra' | 'enlaces';
  className?: string;
}) {
  const whatsapp = (clase: string, texto: string) => (
    <a
      href={acciones.enlaceWhatsapp}
      target="_blank"
      rel="noopener noreferrer"
      onClick={acciones.alClicWhatsapp}
      className={clase}
    >
      {texto}
      <span className="sr-only">{T.nuevaPestana}</span>
    </a>
  );

  if (variante === 'enlaces') {
    return (
      <p className={`flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm ${className}`}>
        <button
          type="button"
          onClick={acciones.abrirLlamada}
          className="underline text-gloma-mint hover:text-gloma-rose min-h-[44px] px-1"
        >
          {T.agendar}
        </button>
        <span className="text-gloma-ink-muted" aria-hidden="true">
          ·
        </span>
        {whatsapp('underline text-gloma-mint hover:text-gloma-rose min-h-[44px] px-1 inline-flex items-center', T.whatsapp)}
      </p>
    );
  }

  if (variante === 'barra') {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <button type="button" onClick={acciones.abrirLlamada} className="demo-btn-primario !min-h-[44px] !px-4 !text-sm">
          <span className="sm:hidden">{T.agendarCorto}</span>
          <span className="hidden sm:inline">{T.agendar}</span>
        </button>
        {whatsapp(
          'inline-flex items-center justify-center min-h-[44px] px-4 rounded-full border border-white/50 text-white text-sm font-semibold hover:bg-white/10',
          T.whatsappCorto,
        )}
      </div>
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <button type="button" onClick={acciones.abrirLlamada} className="demo-btn-primario w-full !min-h-[44px] !text-sm">
        {T.agendar}
      </button>
      {whatsapp(
        'inline-flex items-center justify-center w-full min-h-[44px] px-4 rounded-full border border-white/50 text-white text-sm font-semibold hover:bg-white/10',
        T.whatsapp,
      )}
    </div>
  );
}
