import { useEffect, useRef } from 'react';

import { DEMO_UI } from '../../lib/demo_copy';
import CtaAgendar, { type AccionesAgendar } from './CtaAgendar';
import { IconoChatCerrado } from './iconos';

/**
 * 404 en `/estado` o `/chat` (token inválido o demo vencida). En la etapa de
 * chat cubre la ventana (`cubrir`); en las demás etapas va sola en la página.
 */
export default function DemoNoDisponible({
  onNuevaDemo,
  acciones,
  cubrir = false,
}: {
  onNuevaDemo: () => void;
  acciones: AccionesAgendar;
  cubrir?: boolean;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  const t = DEMO_UI.noDisponible;

  useEffect(() => {
    titulo.current?.focus({ preventScroll: true });
  }, []);

  return (
    <div
      className={`${cubrir ? 'absolute inset-0 z-20 bg-gloma-ink' : 'min-h-[60vh]'} flex flex-col items-center justify-center text-center px-8`}
    >
      <IconoChatCerrado />
      <h3 ref={titulo} tabIndex={-1} className="font-heading font-bold text-xl text-white mt-4 focus:outline-none">
        {t.titulo}
      </h3>
      <p className="text-sm text-gloma-ink-muted mt-2 max-w-xs">{t.texto}</p>
      <button type="button" onClick={onNuevaDemo} className="demo-btn-primario mt-5">
        {t.boton}
      </button>
      <CtaAgendar acciones={acciones} variante="enlaces" className="mt-3" />
    </div>
  );
}
