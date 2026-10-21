/**
 * Menú de la cabecera del chat de la demo (#634): un botón «Agendar» que
 * despliega las dos salidas, «Agendar una llamada» (modal de Cal.com) y
 * «Hablar con un asesor» (wa.me de Gloma).
 *
 * Patrón de menú de botón (WAI-ARIA): `aria-haspopup="menu"` y
 * `aria-expanded` en el botón; al abrir, foco al primer ítem; ↑ ↓ Inicio Fin
 * recorren; Escape cierra y devuelve el foco al botón; Tab o un clic afuera
 * cierran. En celular el panel se ancla a la derecha y nunca pasa del ancho
 * de la pantalla.
 */
import { useEffect, useId, useRef, useState } from 'react';

import { TEXTOS_AGENDAR as T } from '../../lib/agendarLlamada';
import type { AccionesAgendar } from './CtaAgendar';
import { IconoCalendario, IconoFlecha } from './iconos';

export default function MenuContacto({ acciones }: { acciones: AccionesAgendar }) {
  const [abierto, setAbierto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLElement | null)[]>([]);
  const idMenu = useId();

  const cerrar = (devolverFoco: boolean) => {
    setAbierto(false);
    if (devolverFoco) boton.current?.focus();
  };

  // Al abrir, foco al primer ítem.
  useEffect(() => {
    if (abierto) items.current[0]?.focus();
  }, [abierto]);

  // Clic (o toque) afuera cierra.
  useEffect(() => {
    if (!abierto) return;
    const afuera = (e: PointerEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener('pointerdown', afuera);
    return () => document.removeEventListener('pointerdown', afuera);
  }, [abierto]);

  const enBoton = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setAbierto(true);
    }
  };

  const enMenu = (e: React.KeyboardEvent) => {
    const lista = items.current.filter(Boolean) as HTMLElement[];
    const i = lista.indexOf(document.activeElement as HTMLElement);
    const ir = (n: number) => lista[(n + lista.length) % lista.length]?.focus();
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        ir(i + 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        ir(i - 1);
        break;
      case 'Home':
        e.preventDefault();
        ir(0);
        break;
      case 'End':
        e.preventDefault();
        ir(lista.length - 1);
        break;
      case 'Escape':
        e.preventDefault();
        e.stopPropagation();
        cerrar(true);
        break;
      case 'Tab':
        setAbierto(false);
        break;
      default:
    }
  };

  const item =
    'w-full flex items-center gap-3 px-4 min-h-[48px] text-left text-sm text-gloma-ink-text hover:bg-white/10 focus:bg-white/10 focus:outline-none';

  return (
    <div ref={raiz} className="relative shrink-0">
      <button
        ref={boton}
        type="button"
        aria-haspopup="menu"
        aria-expanded={abierto}
        aria-controls={abierto ? idMenu : undefined}
        onClick={() => setAbierto((v) => !v)}
        onKeyDown={enBoton}
        className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full border border-white/50 text-white text-xs font-semibold hover:bg-white/10"
      >
        <IconoCalendario />
        <span className="md:hidden">{T.agendarCorto}</span>
        <span className="hidden md:inline">{T.agendar}</span>
        <span className={`transition-transform ${abierto ? 'rotate-180' : ''}`}>
          <IconoFlecha dir="abajo" size={12} />
        </span>
      </button>
      {abierto && (
        <div
          id={idMenu}
          role="menu"
          aria-label="Hablar con Gloma"
          onKeyDown={enMenu}
          className="absolute right-0 top-full mt-2 z-30 w-64 max-w-[calc(100vw-1.5rem)] py-1.5 rounded-2xl bg-gloma-ink border border-white/15 shadow-2xl shadow-black/50 demo-entra"
        >
          <button
            ref={(el) => {
              items.current[0] = el;
            }}
            type="button"
            role="menuitem"
            className={item}
            onClick={() => {
              cerrar(true);
              acciones.abrirLlamada();
            }}
          >
            <span className="w-8 h-8 rounded-full bg-gloma-mint text-gloma-ink flex items-center justify-center shrink-0" aria-hidden="true">
              <IconoCalendario size={16} />
            </span>
            <span>
              <span className="block font-semibold">{T.agendar}</span>
              <span className="block text-xs text-gloma-ink-muted">Elige día y hora · 30 min</span>
            </span>
          </button>
          <a
            ref={(el) => {
              items.current[1] = el;
            }}
            role="menuitem"
            href={acciones.enlaceWhatsapp}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={T.whatsappAria}
            className={item}
            onClick={() => {
              acciones.alClicWhatsapp();
              cerrar(true);
            }}
          >
            <span className="w-8 h-8 rounded-full border border-white/40 flex items-center justify-center shrink-0" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.6A8 8 0 1 1 21 12z" />
              </svg>
            </span>
            <span>
              <span className="block font-semibold">{T.whatsapp}</span>
              {/* Que abre otra pestaña lo dice el `aria-label`; el texto visible queda corto (#636). */}
              <span className="block text-xs text-gloma-ink-muted">Por WhatsApp</span>
            </span>
          </a>
        </div>
      )}
    </div>
  );
}
