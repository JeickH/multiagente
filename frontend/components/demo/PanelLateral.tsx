import Image from 'next/image';

import { DEMO_UI } from '../../lib/demo_copy';
import type { ProductoDemo } from '../../lib/demoApi';
import CtaAgendar, { type AccionesAgendar } from './CtaAgendar';

const U = DEMO_UI;

/** Chips de ideas: tocar una la escribe en el cuadro (no la envía). */
export function ListaIdeas({
  ideas,
  onIdea,
  deshabilitado,
}: {
  ideas: string[];
  onIdea: (idea: string) => void;
  deshabilitado: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {ideas.map((idea) => (
        <button
          key={idea}
          type="button"
          disabled={deshabilitado}
          onClick={() => onIdea(idea)}
          className="text-[12px] text-left px-3 py-1.5 min-h-[32px] rounded-full bg-gloma-mint/10 border border-gloma-mint/30 text-gloma-ink-text hover:bg-gloma-mint/20 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {idea}
        </button>
      ))}
    </div>
  );
}

/** Panel lateral de la etapa 3 (solo `md:`): productos, ideas y el CTA de Gloma. */
export default function PanelLateral({
  empresa,
  productos,
  ideas,
  onIdea,
  ideasDeshabilitadas,
  acciones,
}: {
  empresa: string;
  productos: ProductoDemo[];
  ideas: string[];
  onIdea: (idea: string) => void;
  ideasDeshabilitadas: boolean;
  acciones: AccionesAgendar;
}) {
  return (
    <aside className="hidden md:flex flex-col gap-4 min-h-0 overflow-y-auto" aria-label="Sobre esta demo">
      <a href="https://glomacx.com/" aria-label="Gloma, ir al inicio" className="self-start">
        <Image src="/gloma/logo_blancotrans.png" alt="Gloma" width={320} height={192} className="h-14 w-auto object-contain" />
      </a>
      <div>
        <p className="text-xs uppercase tracking-widest font-semibold text-gloma-mint">{U.chat.panelEyebrow}</p>
        <h2 className="font-heading font-bold text-xl text-white leading-tight mt-1 break-words">
          {U.chat.panelTitulo} <span className="text-gloma-mint">{empresa}</span>
        </h2>
      </div>
      {productos.length > 0 && (
        <div className="rounded-2xl bg-white/[0.04] border border-gloma-mint/15 p-4">
          <p className="text-sm font-semibold text-white">{U.chat.panelProductos}</p>
          <ul className="mt-2 space-y-2.5 text-[13px]">
            {productos.map((p) => (
              <li key={p.nombre}>
                <p className="font-semibold text-white">{p.nombre}</p>
                {p.resumen && <p className="text-gloma-ink-muted leading-snug mt-0.5">{p.resumen}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="rounded-2xl bg-white/[0.04] border border-gloma-mint/15 p-4">
        <p className="text-sm font-semibold text-white mb-2">{U.chat.panelIdeas}</p>
        <ListaIdeas ideas={ideas} onIdea={onIdea} deshabilitado={ideasDeshabilitadas} />
      </div>
      <div className="mt-auto rounded-2xl bg-gloma-forest p-4">
        <p className="font-heading font-bold text-white leading-snug">{U.cta.panelTitulo}</p>
        <p className="text-[13px] text-white/80 mt-1">{U.cta.panelTexto}</p>
        <CtaAgendar acciones={acciones} variante="bloque" className="mt-3" />
      </div>
    </aside>
  );
}
